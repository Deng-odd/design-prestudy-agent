"""案例筛选结果与案例关联分析。"""

from pydantic import BaseModel, ConfigDict


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    location: str
    project_type: str
    source: str
    relevance: str


class CaseAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case: str
    relevance_reason: str
    spatial_strategy: list[str]
    applicable_reference: list[str]
    limitations: list[str]
