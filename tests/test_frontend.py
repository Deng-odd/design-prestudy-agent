from copy import deepcopy
from io import BytesIO
from unittest.mock import Mock
from urllib.error import URLError

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.agent.graph import graph
from src.frontend import app
from src.schemas import GeneratedImage


PNG = b"\x89PNG\r\n\x1a\n" + b"local-image-fixture"


def test_run_directory_and_upload_paths(tmp_path):
    directory = app.create_run_directory(tmp_path)
    another = app.create_run_directory(tmp_path)
    assert directory != another and directory.parent == tmp_path
    assert {item.name for item in directory.iterdir()} == {"inputs", "images"}
    uploads = [Mock(name="upload") for _ in range(2)]
    for upload in uploads:
        upload.name = "../../same.png"
        upload.getvalue.return_value = PNG
    paths = app.save_uploads(uploads, directory)
    assert len(set(paths)) == 2
    for path in paths:
        assert app.Path(path).is_absolute() and app.Path(path).parent == directory / "inputs"
        assert app.Path(path).read_bytes() == PNG
    assert app.save_uploads([], directory) == []


@pytest.mark.parametrize("filename,data", [("file.txt", PNG), ("file.png", b""),
                                           ("file.png", b"invalid"), ("file.png", b"x" * (10 * 1024 * 1024 + 1))],
                         ids=["extension", "empty", "content", "too-large"])
def test_bad_upload_is_controlled(tmp_path, filename, data):
    upload = Mock()
    upload.name = filename
    upload.getvalue.return_value = data
    with pytest.raises(ValueError):
        app.save_uploads([upload], app.create_run_directory(tmp_path))


def test_merge_input_and_followup_fresh_initial_state(monkeypatch):
    assert app.merge_input("原始描述", "补充空间条件") == "原始描述\n\n用户补充信息：\n补充空间条件"
    assert app.merge_input("原始描述", "  ") == "原始描述"
    paths = ["local-site.png"]
    invoke = Mock(return_value={"info_sufficient": False, "followup_question": "请补充"})
    monkeypatch.setattr(graph, "invoke", invoke)
    app.invoke_agent("原始描述", paths)
    app.invoke_agent("原始描述", paths, "补充空间条件")
    first, second = [call.args[0] for call in invoke.call_args_list]
    assert set(first) == set(second) == {"user_input", "site_images", "search_attempts"}
    assert first["site_images"] == second["site_images"] == paths
    assert first["site_images"] is not second["site_images"]
    assert first["search_attempts"] == second["search_attempts"] == 0
    assert second["user_input"] == app.merge_input("原始描述", "补充空间条件")


def test_followup_executes_actual_graph_again(fake_llm):
    fake_llm.sufficient = False
    first = app.invoke_agent("初始资料", ["site.png"])
    assert not first["info_sufficient"] and "final_report" not in first
    fake_llm.sufficient = True
    second = app.invoke_agent("初始资料", ["site.png"], "滨水公共空间，北侧道路、南侧河流")
    assert second["final_report"] and second["site_images"] == first["site_images"]
    assert second["search_attempts"] == 0
    assert [task for task, _, _ in fake_llm.calls].count("parse_and_check") == 2


def image_state():
    image = GeneratedImage(concept_name="滨水联系", image_url="https://example.com/temporary.png?signature=test",
                           prompt="空间意向", mode="text2img", reference_images=[])
    return {"images": [image.model_dump()], "final_report": f"# 报告\n\n![{image.concept_name}]({image.image_url})"}


def test_image_download_and_report_persistence_without_mutating_state(tmp_path, monkeypatch):
    directory = app.create_run_directory(tmp_path)
    state = image_state()
    before = deepcopy(state)
    download = Mock(return_value=BytesIO(PNG))
    monkeypatch.setattr(app, "urlopen", download)
    local, report = app.persist_outputs(state, directory)
    url = state["images"][0]["image_url"]
    download.assert_called_once_with(url, timeout=30)
    assert app.Path(local[url]).read_bytes() == PNG
    assert report == directory / "report.md"
    assert "images/concept_01.png" in report.read_text(encoding="utf-8")
    assert url not in report.read_text(encoding="utf-8")
    assert state == before and not list((directory / "images").glob("*.tmp"))


@pytest.mark.parametrize("failure", ["network", "content", "write"])
def test_download_failure_preserves_report_and_original_url(tmp_path, monkeypatch, failure):
    directory = app.create_run_directory(tmp_path)
    state = image_state()
    download = Mock(side_effect=URLError("private response")) if failure == "network" else Mock(return_value=BytesIO(b"invalid"))
    monkeypatch.setattr(app, "urlopen", download)
    if failure == "write":
        original = app.Path.open
        def open_file(path, *args, **kwargs):
            if path.suffix == ".tmp":
                raise PermissionError("private local path")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(app.Path, "open", open_file)
    local, report = app.persist_outputs(state, directory)
    assert local == {} and report.read_text(encoding="utf-8") == state["final_report"]
    assert not list((directory / "images").iterdir())


def test_no_images_and_ask_user_outputs(tmp_path, monkeypatch):
    download = Mock()
    monkeypatch.setattr(app, "urlopen", download)
    directory = app.create_run_directory(tmp_path)
    local, report = app.persist_outputs({"final_report": "# 纯文字报告", "images": []}, directory)
    assert local == {} and report.read_text(encoding="utf-8") == "# 纯文字报告"
    local, report = app.persist_outputs({"info_sufficient": False}, app.create_run_directory(tmp_path))
    assert local == {} and report is None
    download.assert_not_called()


def test_configuration_errors_never_expose_secrets(monkeypatch):
    errors, warnings = app.configuration_messages()
    assert "LLM_MODEL" in errors[0] and "DASHSCOPE_API_KEY" in errors[0]
    assert "TAVILY_API_KEY" in warnings[0]
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "private-key-never-show")
    monkeypatch.setattr(config, "LLM_MODEL", "configured-model")
    errors, _ = app.configuration_messages()
    assert not errors and "private-key-never-show" not in str((errors, warnings))


def button(at, label):
    return next(item for item in at.button if item.label == label)


def test_page_configuration_hint_and_sample_loading():
    at = AppTest.from_string("from src.frontend.app import main\nmain()").run()
    assert not at.exception and at.error
    assert button(at, "开始研究").disabled
    button(at, "加载示例").click().run()
    assert "滨水公共空间" in at.text_area(key="project_input").value


def test_page_ask_user_resubmits_and_saves_report(tmp_path, monkeypatch, fake_llm):
    monkeypatch.setattr(app, "OUTPUTS_ROOT", tmp_path)
    monkeypatch.setattr(config, "LLM_MODEL", "configured-model")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "test-only-placeholder")
    fake_llm.sufficient = False
    at = AppTest.from_string("from src.frontend.app import main\nmain()").run()
    at.text_area(key="project_input").set_value("初始项目资料")
    button(at, "开始研究").click().run()
    assert not at.exception and not at.session_state["latest_agent_state"]["info_sufficient"]
    fake_llm.sufficient = True
    next(item for item in at.text_area if item.label == "补充描述").set_value("滨水公共空间，北侧道路、南侧河流")
    button(at, "提交补充并继续研究").click().run()
    assert not at.exception and at.session_state["latest_agent_state"]["final_report"]
    assert app.Path(at.session_state["report_path"]).is_file()
    assert at.session_state["latest_agent_state"]["search_attempts"] == 0
    assert "用户补充信息" in at.session_state["latest_agent_state"]["user_input"]
    assert len(list(tmp_path.iterdir())) == 1
