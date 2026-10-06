"""设计机会、愿景、概念方向及意向图结果。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DesignOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    opportunity: str
    basis: str
    priority: str


class Vision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    theme: str
    positioning: str
    core_goal: str
    spatial_idea: str


class Concept(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    core_concept: str
    design_opportunities: list[str]
    spatial_strategy: str
    key_actions: list[str]
    case_references: list[str]


class GeneratedImage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    concept_name: str
    image_url: str
    prompt: str
    mode: Literal["text2img", "img2img"]
    reference_images: list[str]
