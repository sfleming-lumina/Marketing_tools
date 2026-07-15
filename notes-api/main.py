import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from auth import VerifiedUser, require_google_user
from bigquery_store import BigQueryNotesStore
from models import Note, NoteIn
from storage import NotesStore

ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
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

app = FastAPI(title="Lumina Marketing Dashboard Notes API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_store_instance: Optional[NotesStore] = None


def get_store() -> NotesStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = BigQueryNotesStore(
            project_id=os.environ.get("BQ_PROJECT_ID", "lumina-lakehouse"),
            dataset=os.environ.get("BQ_DATASET", "marketing_tool_ops"),
            table=os.environ.get("BQ_TABLE", "dashboard_notes"),
        )
    return _store_instance


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/freshness")
def freshness(store: NotesStore = Depends(get_store)) -> dict:
    return store.source_freshness(SOURCE_OBJECTS)


@app.post("/freshness/refresh")
def refresh_freshness(store: NotesStore = Depends(get_store)) -> dict:
    result = store.source_freshness(SOURCE_OBJECTS)
    result["refresh_mode"] = "metadata_check"
    return result


@app.get("/notes", response_model=list[Note])
def list_notes(view: Optional[str] = None, _user: VerifiedUser = Depends(require_google_user), store: NotesStore = Depends(get_store)) -> list[Note]:
    return store.list_notes(view)


@app.post("/notes", response_model=Note, status_code=201)
def create_note(note: NoteIn, user: VerifiedUser = Depends(require_google_user), store: NotesStore = Depends(get_store)) -> Note:
    try:
        return store.create_note(note, author_name=user.name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
