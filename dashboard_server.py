import json
import os
import re
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib import error as urlerror
from urllib import request as urlrequest

from google.cloud import bigquery


ROOT = Path(__file__).parent / "outputs"
PROJECT_ID = os.environ.get("BQ_PROJECT_ID", "lumina-lakehouse")
DATASET = os.environ.get("BQ_DATASET", "marketing_tool_ops")
TABLE = os.environ.get("BQ_TABLE", "dashboard_notes")
TABLE_REF = f"{PROJECT_ID}.{DATASET}.{TABLE}"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5").strip()
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

SOURCE_OBJECTS = [
    "analytics_rpt.rpt_marketing_lead_cohort_performance",
    "analytics_rpt.rpt_marketing_cohort_expected_yield",
    "analytics_rpt.rpt_marketing_period_projection",
    "analytics_rpt.rpt_marketing_campaign_ahj_performance",
    "analytics_rpt.rpt_campaign_ahj_performance",
    "analytics_rpt.rpt_pipeline_funnel",
    "analytics_rpt.rpt_sales_growth_summary",
    "analytics_rpt.rpt_project_product_mix_summary",
    "analytics_rpt.rpt_opportunity_product_mix_summary",
    "analytics_rpt.rpt_current_performance_bq_columns_v1",
    "analytics_rpt.rpt_residential_cost_project_detail",
    "analytics_rpt.rpt_sales_to_survey_capacity",
    "analytics_rpt.rpt_survey_performance_by_surveyor",
    "analytics_rpt.rpt_survey_return_reason_trend",
    "analytics_rpt.rpt_forecast_capacity_plan_v1",
    "analytics_rpt.rpt_forecast_leadership_simulation_v1",
    "analytics_rpt.rpt_forecast_priority_queue_v1",
    "analytics_rpt.rpt_forecast_model_decision_recommendation_v1",
]


class DashboardHandler(SimpleHTTPRequestHandler):
    _client = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    @property
    def client(self):
        if DashboardHandler._client is None:
            DashboardHandler._client = bigquery.Client(project=PROJECT_ID)
        return DashboardHandler._client

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 120_000:
            raise ValueError("Request body is too large.")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _iap_user(self):
        raw = self.headers.get("X-Goog-Authenticated-User-Email", "")
        if raw.startswith("accounts.google.com:"):
            raw = raw.split(":", 1)[1]
        return raw or "iap-user@luminasolar.com"

    def _author_name(self):
        email = self._iap_user()
        return email.split("@", 1)[0].replace(".", " ").title() if "@" in email else email

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/api/notes":
            params = parse_qs(parsed.query)
            self._send_json(HTTPStatus.OK, self._list_notes(params.get("view", [None])[0]))
            return
        if parsed.path == "/api/freshness":
            self._send_json(HTTPStatus.OK, self._source_freshness())
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/notes":
            payload = self._read_json_body()
            self._send_json(HTTPStatus.CREATED, self._create_note(payload))
            return
        if parsed.path == "/api/freshness/refresh":
            result = self._source_freshness()
            result["refresh_mode"] = "metadata_check"
            self._send_json(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/ask-claude":
            try:
                status, result = self._ask_claude(self._read_json_body())
            except ValueError as exc:
                status, result = HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
            self._send_json(status, result)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def _list_notes(self, view):
        query = f"""
            SELECT
                note_id,
                created_at,
                author_name,
                view,
                element_key,
                element_label,
                COALESCE(target_type, 'tile') AS target_type,
                COALESCE(feedback_type, 'tweak') AS feedback_type,
                note_text,
                context
            FROM `{TABLE_REF}`
            {"WHERE view = @view" if view else ""}
            ORDER BY created_at DESC
        """
        job_config = bigquery.QueryJobConfig()
        if view:
            job_config.query_parameters = [bigquery.ScalarQueryParameter("view", "STRING", view)]
        rows = self.client.query(query, job_config=job_config).result()
        return [
            {
                "note_id": row["note_id"],
                "created_at": row["created_at"].isoformat(),
                "author_name": row["author_name"],
                "view": row["view"],
                "element_key": row["element_key"],
                "element_label": row["element_label"],
                "target_type": row["target_type"],
                "feedback_type": row["feedback_type"],
                "note_text": row["note_text"],
                "context": json.loads(row["context"]) if row["context"] else {},
            }
            for row in rows
        ]

    def _create_note(self, payload):
        created = {
            "note_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "author_name": self._author_name(),
            "view": payload["view"],
            "element_key": payload["element_key"],
            "element_label": payload["element_label"],
            "target_type": payload.get("target_type", "tile"),
            "feedback_type": payload.get("feedback_type", "tweak"),
            "note_text": payload["note_text"],
            "context": payload.get("context", {}),
        }
        row = dict(created)
        row["context"] = json.dumps(row["context"])
        errors = self.client.insert_rows_json(TABLE_REF, [row])
        if errors:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"detail": f"BigQuery insert failed: {errors}"})
            return
        return created

    def _source_freshness(self):
        checked_at = datetime.now(timezone.utc).isoformat()
        objects = []
        missing = []
        for object_id in SOURCE_OBJECTS:
            try:
                table = self.client.get_table(f"{PROJECT_ID}.{object_id}")
            except Exception:
                missing.append(object_id)
                continue
            objects.append({
                "object_id": object_id,
                "type": table.table_type,
                "modified_at": table.modified.isoformat() if table.modified else None,
            })
        latest = max((item["modified_at"] for item in objects if item["modified_at"]), default=None)
        return {
            "checked_at": checked_at,
            "latest_modified_at": latest,
            "objects_checked": len(SOURCE_OBJECTS),
            "objects_found": len(objects),
            "missing_objects": missing,
            "objects": objects,
        }

    def _extract_claude_answer(self, result):
        parts = []

        def collect(value):
            if isinstance(value, str):
                if value.strip():
                    parts.append(value.strip())
                return
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if not isinstance(value, dict):
                return
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            nested = value.get("content")
            if nested is not None:
                collect(nested)

        collect(result.get("content", []))
        legacy_completion = result.get("completion")
        if isinstance(legacy_completion, str) and legacy_completion.strip():
            parts.append(legacy_completion.strip())
        return "\n".join(parts).strip()

    def _parse_claude_insights(self, answer):
        try:
            return json.loads(answer)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", answer)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    def _fallback_insights(self, question, context, reason):
        planner = context.get("campaign_planner", {}) if isinstance(context, dict) else {}
        diagnostics = planner.get("cost_spend_diagnostics", {}) if isinstance(planner, dict) else {}
        summary = context.get("summary_metrics", {}) if isinstance(context, dict) else {}
        filters = context.get("filters", {}) if isinstance(context, dict) else {}
        blended_cpw = self._num(diagnostics.get("blended_planned_cpw")) or self._num(summary.get("cost_per_win")) or 0
        total_spend = self._num(diagnostics.get("total_planned_spend")) or self._num(summary.get("spend")) or 0
        highest_cpw = self._first(diagnostics.get("highest_capacity_adjusted_cpw"))
        highest_spend = self._first(diagnostics.get("highest_spend"))
        weakest_roi = self._first(diagnostics.get("weakest_revenue_per_spend"))
        full_table = diagnostics.get("full_campaign_table") or planner.get("campaigns") or []
        best_efficiency = max(
            (row for row in full_table if isinstance(row, dict)),
            key=lambda row: self._num(row.get("revenue_per_spend")),
            default={},
        )

        weak_spots = []
        if highest_cpw:
            weak_spots.append({
                "name": self._label(highest_cpw),
                "metric": "Highest capacity-adjusted CPW",
                "evidence": (
                    f"{self._label(highest_cpw)} shows capacity-adjusted CPW of "
                    f"{self._currency(highest_cpw.get('capacity_adjusted_cpw'))} versus blended planned CPW of "
                    f"{self._currency(blended_cpw)}."
                ),
                "why_it_matters": (
                    f"Stress is {self._percent(highest_cpw.get('stress'))}; spend here can look efficient before "
                    "downstream capacity friction is included."
                ),
                "severity": "high" if self._num(highest_cpw.get("capacity_adjusted_cpw")) > blended_cpw * 1.25 else "medium",
            })
        if highest_spend:
            weak_spots.append({
                "name": self._label(highest_spend),
                "metric": "Largest spend concentration",
                "evidence": (
                    f"{self._label(highest_spend)} carries planned spend of "
                    f"{self._currency(highest_spend.get('planned_spend'))}, "
                    f"{self._percent(highest_spend.get('spend_share'))} of the selected budget."
                ),
                "why_it_matters": "Large budget share deserves extra scrutiny when CPW or revenue-per-spend is not also best in class.",
                "severity": "medium",
            })
        if weakest_roi:
            weak_spots.append({
                "name": self._label(weakest_roi),
                "metric": "Weakest revenue per spend",
                "evidence": (
                    f"{self._label(weakest_roi)} has revenue per spend of "
                    f"{self._num(weakest_roi.get('revenue_per_spend')):.1f}x."
                ),
                "why_it_matters": "This is the first place to question marginal dollars if cost per win is also elevated.",
                "severity": "medium",
            })

        recommendations = []
        if highest_cpw:
            recommendations.append({
                "action": f"Pressure-test spend on {self._label(highest_cpw)}",
                "rationale": "It is the clearest cost-per-win weak spot after capacity adjustment.",
                "expected_impact": "Reduces the chance that paid growth creates expensive downstream bottlenecks.",
                "confidence": "medium",
            })
        if best_efficiency:
            recommendations.append({
                "action": f"Move marginal dollars toward {self._label(best_efficiency)} if capacity holds",
                "rationale": (
                    f"It has stronger revenue per spend at {self._num(best_efficiency.get('revenue_per_spend')):.1f}x "
                    "inside the selected context."
                ),
                "expected_impact": "Improves budget quality without requiring a full-plan reset.",
                "confidence": "medium",
            })
        recommendations.append({
            "action": "Review CPW and spend together in the next planning meeting",
            "rationale": "High spend alone is not a problem; high spend plus weak CPW or weak revenue-per-spend is the decision trigger.",
            "expected_impact": "Creates a cleaner scale, test, hold, or cut decision for each campaign.",
            "confidence": "high",
        })

        return {
            "headline": "Cost and spend weak spots need budget guardrails",
            "executive_summary": (
                f"For {filters.get('market', 'the selected market')} / {filters.get('source', 'the selected source')}, "
                f"the selected context shows {self._currency(total_spend)} in planned spend and blended CPW of "
                f"{self._currency(blended_cpw)}. The weak spots are the campaigns where CPW, capacity-adjusted CPW, "
                "or spend concentration are out of line with that blended benchmark."
            ),
            "weak_spots": weak_spots,
            "recommendations": recommendations,
            "watchouts": [
                "These recommendations use the dashboard context supplied to the assistant, not an open-ended BigQuery query.",
                f"Fallback insight mode was used because Claude returned no usable structured text: {reason}.",
            ],
            "next_actions": [
                "Open the Campaign Planner and compare the weak spot against the best revenue-per-spend campaign.",
                "Add a note on any campaign whose CPW looks directionally wrong so the data team can validate source data.",
                "Use the next budget review to decide whether the weak spot should be capped, re-tested, or shifted.",
            ],
        }

    def _num(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _first(self, value):
        if isinstance(value, list) and value:
            return value[0] if isinstance(value[0], dict) else {}
        return {}

    def _label(self, row):
        return str(row.get("campaign") or row.get("source") or row.get("name") or "Selected campaign")

    def _currency(self, value):
        amount = self._num(value)
        if abs(amount) >= 1_000_000:
            return f"${amount / 1_000_000:.1f}M"
        if abs(amount) >= 1_000:
            return f"${amount / 1_000:.0f}K"
        return f"${amount:,.0f}"

    def _percent(self, value):
        return f"{self._num(value) * 100:.1f}%"

    def _ask_claude(self, payload):
        if not ANTHROPIC_API_KEY:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "Claude is not configured for this environment."}

        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("Question is required.")

        context = payload.get("context", {})
        context_json = json.dumps(context, indent=2, default=str)[:20_000]
        body = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1600,
            "system": (
                "You are Claude helping Lumina Solar's marketing team interpret an internal "
                "performance dashboard. Give executives and marketing operators decision-grade "
                "insights, not generic commentary. Use the supplied dashboard context only, call "
                "out exact evidence, compare against blended benchmarks, and convert findings "
                "into actions. Return JSON only with this shape: "
                '{"headline": string, "executive_summary": string, '
                '"weak_spots": [{"name": string, "metric": string, "evidence": string, '
                '"why_it_matters": string, "severity": "high"|"medium"|"low"}], '
                '"recommendations": [{"action": string, "rationale": string, '
                '"expected_impact": string, "confidence": "high"|"medium"|"low"}], '
                '"watchouts": [string], "next_actions": [string]}. '
                "Keep each string concise. If the evidence is directional/demo-mode, say so."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Dashboard context:\n{context_json}\n\n"
                        f"Marketing user's question:\n{question}"
                    ),
                }
            ],
        }
        request = urlrequest.Request(
            ANTHROPIC_MESSAGES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            detail = "Claude request failed. Check the configured Anthropic key and model."
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                detail = error_payload.get("error", {}).get("message", detail)
            except Exception:
                pass
            return HTTPStatus.BAD_GATEWAY, {"detail": detail, "status": exc.code}
        except Exception:
            return HTTPStatus.BAD_GATEWAY, {"detail": "Claude request failed. Check the configured Anthropic key and service logs."}

        answer = self._extract_claude_answer(result)
        if not answer:
            reason = f"stop_reason={result.get('stop_reason')}; content_types={','.join([
                block.get("type", type(block).__name__) if isinstance(block, dict) else type(block).__name__
                for block in result.get("content", [])
            ]) or 'none'}"
            insights = self._fallback_insights(question, context, reason)
            return HTTPStatus.OK, {
                "answer": insights["executive_summary"],
                "insights": insights,
                "model": result.get("model", ANTHROPIC_MODEL),
                "fallback": True,
            }
        insights = self._parse_claude_insights(answer)
        if insights is None:
            insights = self._fallback_insights(question, context, "unstructured Claude response")
            insights["watchouts"].insert(0, "Claude returned text, but not in the structured format needed for the insight panel.")
        return HTTPStatus.OK, {
            "answer": answer,
            "insights": insights,
            "model": result.get("model", ANTHROPIC_MODEL),
        }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler).serve_forever()
