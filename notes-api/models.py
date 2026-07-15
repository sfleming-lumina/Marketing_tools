from typing import Literal

from pydantic import BaseModel, Field

DashboardView = Literal["overview", "cohorts", "campaigns", "scenario", "objects"]
FeedbackType = Literal["helpful", "tweak", "not_helpful"]
TargetType = Literal["section", "tile", "chart", "table", "metric", "recommendation", "object", "control"]


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
