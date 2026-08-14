from typing import Literal, Optional

from pydantic import BaseModel, Field

DashboardView = Literal[
    "overview", "cohorts", "campaigns", "objects",
    "command", "trends", "monitoring", "funnel", "geo", "scenario", "quality", "workbook",
]
FeedbackType = Literal["helpful", "tweak", "not_helpful", "question", "data", "idea", "decision"]
TargetType = Literal["section", "tile", "chart", "table", "metric", "recommendation", "object", "control", "view"]
ActionStatus = Literal["Open", "Actioned"]


class NoteIn(BaseModel):
    view: DashboardView
    element_key: str = Field(min_length=1, max_length=200)
    element_label: str = Field(min_length=1, max_length=300)
    target_type: TargetType = "tile"
    feedback_type: FeedbackType = "tweak"
    note_text: str = Field(min_length=1, max_length=4000)
    context: dict = Field(default_factory=dict)


class Note(NoteIn):
    note_id: str
    created_at: str
    author_name: str
    action_status: ActionStatus = "Open"
    action_taken: Optional[str] = None
    actioned_at: Optional[str] = None
    actioned_by: Optional[str] = None


class NoteActionIn(BaseModel):
    action_status: ActionStatus
    action_taken: str = Field(min_length=1, max_length=4000)
