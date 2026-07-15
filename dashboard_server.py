import json
import os
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
            "max_tokens": 900,
            "system": (
                "You are Claude helping Lumina Solar's marketing team interpret an internal "
                "performance dashboard. Be concise, practical, and explicit about whether a "
                "recommendation is supported by the supplied dashboard context or is a follow-up "
                "question for the data team. Return a plain-text answer only; do not use tool "
                "calls, JSON, markdown tables, or hidden/non-text response blocks."
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
            content_types = [
                block.get("type", type(block).__name__) if isinstance(block, dict) else type(block).__name__
                for block in result.get("content", [])
            ]
            return HTTPStatus.BAD_GATEWAY, {
                "detail": "Claude returned no text content.",
                "stop_reason": result.get("stop_reason"),
                "content_types": content_types,
            }
        return HTTPStatus.OK, {
            "answer": answer,
            "model": result.get("model", ANTHROPIC_MODEL),
        }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler).serve_forever()
