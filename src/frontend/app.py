"""Streamlit 输入、Graph 调用与成果展示；不承担 Agent 专业任务。"""

from pathlib import Path
from http.client import HTTPException
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

import streamlit as st

# 同时支持 Streamlit 脚本入口与包导入，保持既有 src 包结构。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
OUTPUTS_ROOT = PROJECT_ROOT / "outputs"
SAMPLE_PATH = PROJECT_ROOT / "data" / "samples" / "waterfront.md"


def create_run_directory(root: Path | None = None) -> Path:
    directory = (root or OUTPUTS_ROOT).resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "inputs").mkdir()
    (directory / "images").mkdir()
    return directory


def _image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise ValueError("图片内容不是 PNG/JPEG")


def save_uploads(uploads, directory: Path) -> list[str]:
    """生成文件名，不使用上传名称构造路径；Agent 接收绝对本地路径。"""
    paths = []
    for index, upload in enumerate(uploads or [], 1):
        if Path(upload.name).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("仅支持 PNG/JPG/JPEG 场地图片")
        data = upload.getvalue()
        if not data or len(data) > 10 * 1024 * 1024:
            raise ValueError("每张场地图片须非空且不超过 10MB")
        suffix = _image_suffix(data)
        path = directory / "inputs" / f"site_{index:02d}{suffix}"
        path.write_bytes(data)
        paths.append(str(path.resolve()))
    return paths


def merge_input(original: str, supplemental: str = "") -> str:
    if not original.strip():
        raise ValueError("请填写项目描述")
    return original.strip() + ("\n\n用户补充信息：\n" + supplemental.strip() if supplemental.strip() else "")


def invoke_agent(original: str, image_paths: list[str], supplemental: str = "") -> dict:
    """每次均从原始输入创建新的初始 State，包括追问后的重新调用。"""
    from src.agent.graph import graph
    from src.agent.state import create_initial_state
    initial = create_initial_state(merge_input(original, supplemental), image_paths)
    return graph.invoke(initial)


def download_image(url: str, directory: Path, index: int) -> Path | None:
    """下载单个应用输出；失败只返回 None，不修改 Agent 图片结果。"""
    temporary = directory / "images" / f"concept_{index:02d}.tmp"
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        size = 0
        with urlopen(url, timeout=30) as response, temporary.open("wb") as output:
            while chunk := response.read(64 * 1024):
                size += len(chunk)
                if size > 20 * 1024 * 1024:
                    raise ValueError("图片下载超过大小限制")
                output.write(chunk)
        with temporary.open("rb") as saved:
            suffix = _image_suffix(saved.read(8))
        target = temporary.with_suffix(suffix)
        temporary.replace(target)
        return target.resolve()
    except (OSError, ValueError, HTTPException):
        return None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def persist_outputs(state: dict, directory: Path) -> tuple[dict[str, str], Path | None]:
    """保存图片并修复导出报告图片链接；保留原 State 与原始 URL。"""
    local_images = {}
    for index, image in enumerate(state.get("images", []), 1):
        url = image["image_url"]
        path = download_image(url, directory, index)
        if path:
            local_images[url] = str(path)
    report = state.get("final_report")
    if not isinstance(report, str) or not report.strip():
        return local_images, None
    for url, path in local_images.items():
        report = report.replace(url, Path(path).relative_to(directory).as_posix())
    path = directory / "report.md"
    path.write_text(report, encoding="utf-8")
    return local_images, path


def configuration_messages() -> tuple[list[str], list[str]]:
    try:
        from src import config
        missing = [name for name in ("LLM_MODEL", "DASHSCOPE_API_KEY") if not getattr(config, name).strip()]
        errors = ["请在本地 .env 配置 " + "、".join(missing) + "，然后重启应用。"] if missing else []
        if not missing:
            config.validate_llm_config()
        warnings = []
        if not config.TAVILY_API_KEY.strip():
            warnings.append("未配置 TAVILY_API_KEY；需要案例检索时将按现有流程降级，仍可继续生成报告。")
        if not config.IMAGE_MODEL.strip():
            warnings.append("未配置 IMAGE_MODEL；图片生成会降级，概念与报告仍可输出。")
        return errors, warnings
    except ValueError:
        return ["本地配置格式或 endpoint 无效，请检查 .env 并重启应用。"], []


def _render_results(state: dict, local_images: dict[str, str]) -> None:
    st.subheader("研究成果")
    with st.expander("项目理解", expanded=True):
        st.write(state.get("project_background", ""))
        st.write("区位：", state.get("location", ""))
        st.write("规划条件：", state.get("planning_conditions", {}))
        if state.get("client_requirements"):
            st.write("客户与设计要求：", state["client_requirements"])
    with st.expander("场地分析 / SWOT"):
        site = state.get("site_analysis", {})
        st.write(site.get("project_positioning", ""))
        st.write(site.get("analysis_summary", ""))
        labels = {"location_conditions": "区位条件", "functional_conditions": "功能条件",
                  "landscape_resources": "景观资源", "public_space": "公共空间",
                  "transportation": "交通联系", "spatial_conditions": "空间条件"}
        for key, label in labels.items():
            st.write(label, site.get(key, {}))
        for key, label in {"strengths": "优势", "weaknesses": "劣势", "opportunities": "机会", "threats": "风险"}.items():
            st.write(label, site.get("swot", {}).get(key, []))
    with st.expander("案例研究"):
        if state.get("need_case_research") is False:
            st.write("本次研究无需案例检索。")
        st.write("研究方向：", state.get("research_direction", []))
        for case in state.get("filtered_cases", []):
            st.markdown(f"**{case['name']}**")
            parsed = urlsplit(case["source"])
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                st.link_button("查看案例来源", case["source"])
            st.write(case["relevance"])
        for analysis in state.get("case_analysis", []):
            st.write(analysis)
        if state.get("research_gaps"):
            st.write("研究局限：", state["research_gaps"])
    with st.expander("设计机会 / Vision", expanded=True):
        for opportunity in state.get("opportunities", []):
            st.write(opportunity)
        vision = state.get("vision", {})
        for key, label in {"theme": "主题", "positioning": "定位", "core_goal": "核心目标", "spatial_idea": "空间构想"}.items():
            st.write(label, vision.get(key, ""))
    for concept in state.get("concepts", []):
        with st.expander(concept["name"], expanded=True):
            st.write(concept["core_concept"])
            st.write("空间策略：", concept["spatial_strategy"])
            st.write("关键行动：", concept["key_actions"])
            st.write("设计机会：", concept["design_opportunities"])
            st.write("案例参考：", concept["case_references"])
            for image in state.get("images", []):
                if image["concept_name"] != concept["name"]:
                    continue
                try:
                    st.image(local_images.get(image["image_url"], image["image_url"]),
                             caption=f"{concept['name']} · 概念意向图", width="stretch")
                except Exception:
                    st.info("该意向图暂不可展示，其他成果不受影响。")
    if not state.get("images"):
        st.info("本次暂无可用意向图，概念与报告已保留。")
    st.subheader("最终 Markdown 报告")
    st.markdown(state.get("final_report", ""))


def _run_current_session() -> None:
    session = st.session_state
    session.latest_agent_state = None
    session.local_image_paths = {}
    session.report_path = None
    session.error_message = ""
    session.output_warning = ""
    with st.status("正在研究项目、形成概念并整理报告；图片生成可能需要数分钟。", expanded=True) as status:
        try:
            state = invoke_agent(session.original_user_input, session.uploaded_image_paths, session.supplemental_input)
            session.latest_agent_state = state
        except Exception:
            status.update(label="本次研究未完成", state="error")
            session.error_message = "研究执行失败。请检查本地配置、模型能力或网络后重试；输入图片需要当前模型支持多模态。"
            return
        if state.get("info_sufficient") is False:
            status.update(label="需要补充项目信息", state="complete")
            return
        status.update(label="正在保存意向图与 Markdown 报告")
        try:
            local, report = persist_outputs(state, Path(session.run_directory))
            session.local_image_paths = local
            session.report_path = str(report) if report else None
            if len(local) < len(state.get("images", [])):
                session.output_warning = "部分图片未能保存到本地，仍保留原链接和报告。"
        except OSError:
            session.output_warning = "本地成果保存失败，页面仍保留本次研究结果。"
        status.update(label="研究完成", state="complete")


def main() -> None:
    st.set_page_config(page_title="项目前期研究 Agent", layout="wide")
    st.title("项目前期研究 Agent")
    st.write("输入项目背景与场地条件，生成场地分析、案例研究、概念方向和 Markdown 报告。")
    errors, warnings = configuration_messages()
    for message in errors:
        st.error(message)
    for message in warnings:
        st.warning(message)
    session = st.session_state
    defaults = {"run_id": None, "run_directory": None, "original_user_input": "",
                "uploaded_image_paths": [], "supplemental_input": "", "latest_agent_state": None,
                "local_image_paths": {}, "report_path": None, "project_input": "",
                "error_message": "", "output_warning": ""}
    for key, value in defaults.items():
        if key not in session:
            session[key] = value
    if st.button("加载示例"):
        try:
            session.project_input = SAMPLE_PATH.read_text(encoding="utf-8")
        except OSError:
            st.error("示例暂不可读取，请直接输入项目描述。")
    with st.form("project_form"):
        user_input = st.text_area("项目描述", key="project_input", height=180,
                                  placeholder="项目背景、类型、场地空间条件、设计要求，以及指定研究方向或案例。")
        uploads = st.file_uploader("场地图片（可选，每张不超过 10MB）", type=["png", "jpg", "jpeg"],
                                   accept_multiple_files=True, max_upload_size=10)
        submitted = st.form_submit_button("开始研究", disabled=bool(errors))
    if submitted:
        if not user_input.strip():
            st.error("请填写项目描述。")
        else:
            try:
                directory = create_run_directory()
                paths = save_uploads(uploads, directory)
                session.update(run_id=directory.name, run_directory=str(directory), original_user_input=user_input,
                               uploaded_image_paths=paths, supplemental_input="", latest_agent_state=None,
                               local_image_paths={}, report_path=None)
                _run_current_session()
            except ValueError as error:
                st.error(str(error))
            except OSError:
                st.error("无法创建运行目录或保存上传图片，请检查本地磁盘权限。")
    state = session.latest_agent_state
    if session.error_message:
        st.error(session.error_message)
    if session.output_warning:
        st.warning(session.output_warning)
    if state and state.get("info_sufficient") is False:
        st.subheader("补充项目信息")
        st.write(state.get("followup_question", "请补充项目定位和场地空间条件。"))
        if state.get("missing_critical"):
            st.write("需要补充：", state["missing_critical"])
        with st.form("supplement_form"):
            supplemental = st.text_area("补充描述")
            supplement_submitted = st.form_submit_button("提交补充并继续研究", disabled=bool(errors))
        if supplement_submitted:
            if not supplemental.strip():
                st.error("请填写补充描述。")
            else:
                session.supplemental_input = "\n\n".join(filter(None, [session.supplemental_input, supplemental.strip()]))
                _run_current_session()
                st.rerun()
    elif state and state.get("final_report"):
        _render_results(state, session.local_image_paths)
        report = state["final_report"]
        if session.report_path:
            try:
                report = Path(session.report_path).read_text(encoding="utf-8")
                st.caption(f"成果目录：outputs/{session.run_id}/")
            except OSError:
                st.warning("本地报告暂不可读取，仍可下载原始报告。")
        st.download_button("下载 Markdown 报告", report, file_name="report.md", mime="text/markdown")


if __name__ == "__main__":
    main()
