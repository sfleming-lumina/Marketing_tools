from typing import Literal

from pydantic import BaseModel, Field

DashboardView = Literal["overview", "cohorts", "campaigns", "scenario", "objects"]


class NoteIn(BaseModel):
    view: DashboardView
    element_key: str = Field(min_length=1, max_length=200)
    element_label: str = Field(min_length=1, max_length=300)
    note_text: str = Field(min_length=1, max_length=4000)
    author_name: str = Field(min_length=1, max_length=120)
    context: dict = Field(default_factory=dict)


class Note(NoteIn):
    note_id: str
    created_at: str
