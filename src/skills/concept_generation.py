"""结构化概念生成与 Skill 内部的一次质量判定、最多一次重新生成。"""

from pydantic import BaseModel, ConfigDict, Field

from src import config
from src.llm import LLMError, call_llm, call_llm_structured, load_prompt
from src.schemas import CaseAnalysis, Concept, DesignOpportunity, GeneratedImage, SiteAnalysis, Vision
from src.tools import generate_image
from src.tools.image_generation import ImageGenerationError


class _OpportunitiesVision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    opportunities: list[DesignOpportunity]
    vision: Vision


class _Concepts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    concepts: list[Concept] = Field(min_length=2, max_length=3)


def generate_concepts(project_background: str, site_analysis: dict,
                      client_requirements: str | None = None,
                      case_analysis: list[dict] | None = None,
                      site_images: list[str] | None = None) -> dict:
    inputs = {"project_background": project_background,
              "site_analysis": SiteAnalysis.model_validate(site_analysis).model_dump(),
              "client_requirements": client_requirements,
              "case_analysis": [CaseAnalysis.model_validate(item).model_dump() for item in case_analysis or []]}
    directions = call_llm_structured(
        load_prompt("identify_opportunities.md", "opportunities_and_vision", inputs), _OpportunitiesVision,
        temperature=config.LLM_TEMPERATURE_GENERATION,
    )
    inputs.update(directions.model_dump())
    concepts = call_llm_structured(load_prompt("generate_concepts.md", "generate_concepts", inputs), _Concepts,
                                   temperature=config.LLM_TEMPERATURE_GENERATION)
    inputs.update(concepts.model_dump())
    quality = call_llm(load_prompt("generate_concepts.md", "quality_check", inputs),
                       temperature=config.LLM_TEMPERATURE_DECISION).strip()
    if quality != "PASS" and not quality.startswith("FAIL"):
        raise LLMError("概念质量判定未返回有效判定")
    if quality != "PASS" and config.MAX_CONCEPT_REGENERATIONS > 0:
        inputs["feedback"] = quality
        concepts = call_llm_structured(load_prompt("generate_concepts.md", "regenerate_concepts", inputs),
                                       _Concepts, temperature=config.LLM_TEMPERATURE_GENERATION)
    # 只为质量流程结束后的最终概念生成图片。
    inputs.update(concepts.model_dump())
    references = []
    limit = config.image_reference_limit()
    if config.USE_IMG2IMG and site_images and limit:
        candidates = list(site_images[:limit])
        try:
            suitable = call_llm(load_prompt("generate_concepts.md", "image_reference_check", inputs),
                                images=candidates, temperature=config.LLM_TEMPERATURE_DECISION).strip()
            if suitable == "PASS":
                references = candidates
        except LLMError:
            # 缺失、不可读或无法理解的参考图由 Skill 决定回退为纯文本。
            pass
    images = []
    for concept in concepts.concepts:
        image_inputs = {"project_background": project_background, "site_analysis": inputs["site_analysis"],
                        "vision": directions.vision.model_dump(), "concept": concept.model_dump(),
                        "mode": "img2img" if references else "text2img"}
        try:
            prompt = call_llm(load_prompt("generate_concepts.md", "image_prompt", image_inputs),
                              temperature=config.LLM_TEMPERATURE_GENERATION).strip()
            result = generate_image(prompt, reference_images=references or None)
            images.append(GeneratedImage(concept_name=concept.name, image_url=result["image_url"],
                                         prompt=prompt, mode=result["mode"], reference_images=references).model_dump())
        except (ImageGenerationError, LLMError):
            # 保留所有 Concept，部分或全部图片失败都不阻断报告。
            continue
    return {**directions.model_dump(), **concepts.model_dump(), "images": images}
