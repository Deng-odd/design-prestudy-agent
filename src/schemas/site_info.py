"""场地分析的唯一 V1 结构。"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class SWOT(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]


class SiteAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    project_positioning: str
    location_conditions: dict[str, Any]
    functional_conditions: dict[str, Any]
    landscape_resources: dict[str, Any]
    public_space: dict[str, Any]
    transportation: dict[str, Any]
    spatial_conditions: dict[str, Any]
    swot: SWOT
    analysis_summary: str
