"""Frozen evaluation input contract; independent of AgentState."""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]


class Focus(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dataset_version: Literal["1.0"]
    case_id: str = Field(pattern=r"^case_\d{2}$")
    project_type: str
    test_role: str
    user_input: str = Field(min_length=1)
    site_images: list[str]
    image_generation_mode: Literal["required", "optional", "disabled"]
    expected_info_sufficient: bool | None
    expected_need_case_research: bool | None
    expected_research_behavior: list[str] = Field(default_factory=list)
    expected_points: list[str] = Field(default_factory=list)
    expected_case_direction: list[str] = Field(default_factory=list)
    expected_missing_critical: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    forbidden_behavior: list[str] = Field(default_factory=list)
    evaluation_focus: Focus
    notes: str = ""

    @field_validator("site_images")
    @classmethod
    def relative_images(cls, paths):
        for value in paths:
            path = Path(value)
            if path.is_absolute() or ".." in path.parts or ":" in value or "\\" in value or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                raise ValueError("site_images must use repository-relative image paths")
        return paths


def load_dataset(path: Path | None = None) -> list[EvalCase]:
    cases = [EvalCase.model_validate(json.loads(line)) for line in
             (path or ROOT / "data/eval/dataset.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cases) != 10 or {c.case_id for c in cases} != {f"case_{i:02}" for i in range(1, 11)}:
        raise ValueError("Frozen V1 requires ten unique case IDs")
    return cases
