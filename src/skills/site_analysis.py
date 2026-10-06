"""基于既有项目资料和可选图片的结构化场地分析。"""

from src import config
from src.llm import call_llm_structured, load_prompt
from src.schemas import SiteAnalysis


def analyze_site(
    project_background: str,
    location: str,
    planning_conditions: dict | None = None,
    client_requirements: str | None = None,
    site_image_description: str | None = None,
    site_images: list[str] | None = None,
) -> dict:
    inputs = {"project_background": project_background, "location": location,
              "planning_conditions": planning_conditions or {}, "client_requirements": client_requirements,
              "site_image_description": site_image_description}
    result = call_llm_structured(load_prompt("analyze_site.md", "site_analysis", inputs), SiteAnalysis,
                                 images=site_images, temperature=config.LLM_TEMPERATURE_ANALYSIS)
    return {"site_analysis": result.model_dump()}
