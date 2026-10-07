"""Sequential, process-local eval runner. Never launches a baseline on import."""
import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler

from evals.dataset import ROOT, load_dataset
from evals.judge import RUBRICS, quality_readiness, judge_metric
from evals.metrics import aggregate, metric, rule_metrics


def images_enabled(case, requested="off"):
    return case.image_generation_mode == "required" or (case.image_generation_mode == "optional" and requested == "on")


def failure_type(error):
    message = str(error)
    if any(text in message for text in ("案例来源或标题", "案例标识重复", "案例分析与已筛选案例", "案例 source_id 不属于当前检索证据")):
        return "source_consistency_validation"
    if isinstance(error, FileNotFoundError):
        return "input_asset_missing"
    if "图片/调用参数" in message:
        return "model_capability_or_parameters"
    from src.llm import LLMError
    from src.tools.web_search import WebSearchError
    from src.tools.image_generation import ImageGenerationError
    if isinstance(error, LLMError):
        return "llm_call_or_validation"
    if isinstance(error, WebSearchError):
        return "search_tool_failure"
    if isinstance(error, ImageGenerationError):
        return "image_tool_failure"
    return "agent_execution_error"


def safe_error(error):
    """Retain known controlled failures without exporting arbitrary SDK payloads."""
    for message in ("案例来源或标题不属于检索证据", "案例标识重复，无法可靠对应分析",
                    "案例分析与已筛选案例无法对应", "案例 source_id 不属于当前检索证据"):
        if message in str(error):
            return message
    return f"{type(error).__name__}: {failure_type(error)}"


class NodeObservation(BaseCallbackHandler):
    """Observe existing Graph node callbacks, including exceptions; no node replacement."""
    def __init__(self, stats):
        self.stats = stats
        self.trace = []
        self.runs = {}
        self.current = None

    def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, **kwargs):
        node = (metadata or {}).get("langgraph_node")
        if not node or kwargs.get("name") != node:
            return
        entry = {"node": node, "status": "running", "update": {}, "state": deepcopy(inputs),
                 "search_queries": [], "search_observations": [], "retrieval_evidence": [],
                 "failure_type": None, "error": None, "tool_calls": {}}
        self.trace.append(entry)
        self.runs[run_id] = (entry, perf_counter(), {key: self.stats[key] for key in ("llm_calls", "search_calls", "image_calls")})
        self.current = entry
        if node == "case_research":
            entry["search_queries"] = list(inputs.get("search_queries", []))

    def _finish(self, run_id, outputs=None, error=None):
        observation = self.runs.pop(run_id, None)
        if observation is None:
            return
        entry, started, counts = observation
        entry["runtime_seconds"] = perf_counter() - started
        entry["tool_calls"] = {key: self.stats[key] - value for key, value in counts.items()}
        if error is None:
            entry["status"] = "success"
            entry["update"] = deepcopy(outputs or {})
            entry["state"].update(entry["update"])
        else:
            entry.update(status="failed", failure_type=failure_type(error), error=safe_error(error))
            if entry["failure_type"] == "source_consistency_validation":
                entry["source_validation_diagnostics"] = deepcopy(entry.get("source_candidate_comparisons", []))
        if self.current is entry:
            self.current = None

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._finish(run_id, outputs=outputs)

    def on_chain_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error=error)


@contextmanager
def observe(enabled, *, record_nodes=False):
    """Scoped wrappers preserve return values/errors. Run only in dedicated eval process."""
    from openai.resources.chat.completions import Completions
    from openai.resources.images import Images
    from tavily import TavilyClient
    from src.agent import nodes
    from src.skills import site_analysis, case_research, concept_generation, report_composition
    from src.llm import LLMError
    stats = dict(llm_calls=0, search_calls=0, image_calls=0, tokens=None, cost=None,
                 concept_regenerations=0, image_failures=0, tool_failures=[], evidence=[])
    token_values = []
    recorder = NodeObservation(stats) if record_nodes else None
    if recorder:
        stats["node_observer"] = recorder
    def provider_wrapper(original, kind):
        def wrapper(*args, **kwargs):
            stats[kind] += 1
            try:
                response = original(*args, **kwargs)
                if kind == "llm_calls":
                    usage = getattr(response, "usage", None)
                    token_values.append(getattr(usage, "total_tokens", None))
                    stats["tokens"] = sum(token_values) if all(x is not None for x in token_values) else None
                return response
            except Exception as error:
                stats["tool_failures"].append({"call_type": kind, "error_type": type(error).__name__})
                if kind == "llm_calls":
                    token_values.append(None)
                    stats["tokens"] = None
                raise
        return wrapper
    def structured_wrapper(original):
        def wrapper(prompt, schema, **kwargs):
            if "当前任务：regenerate_concepts\n" in prompt:
                stats["concept_regenerations"] += 1
            if "当前任务：analyze_cases\n" in prompt:
                evidence = json.loads(prompt.rsplit("INPUT_JSON:\n", 1)[1])["search_results"]
                stats["evidence"].extend(deepcopy(evidence))
                if recorder and recorder.current is not None:
                    recorder.current["retrieval_evidence"] = deepcopy(evidence)
            result = original(prompt, schema, **kwargs)
            if "当前任务：analyze_cases\n" in prompt and recorder and recorder.current is not None:
                recorder.current["selected_source_ids"] = [item.source_id for item in result.selected_cases]
            if "当前任务：generate_search_queries\n" in prompt and recorder and recorder.current is not None:
                recorder.current["search_queries"] = list(result.search_queries)
            return result
        return wrapper
    original_mapping = case_research._map_selected_cases
    def mapping_wrapper(selection, evidence):
        result = original_mapping(selection, evidence)
        if recorder and recorder.current is not None:
            try:
                from evals.source_diagnostics import compare_sources
                recorder.current["source_candidate_comparisons"] = compare_sources(
                    [item.model_dump() for item in result.filtered_cases], evidence)
            except Exception as error:
                recorder.current["source_diagnostic_error"] = type(error).__name__
        return result
    original_search = case_research.web_search
    def search_wrapper(query, *args, **kwargs):
        observation = {"query": query, "status": "running", "results": [], "failure_type": None}
        if recorder and recorder.current is not None:
            recorder.current["search_observations"].append(observation)
        try:
            result = original_search(query, *args, **kwargs)
            observation.update(status="success", results=deepcopy(result))
            return result
        except Exception as error:
            observation.update(status="failed", failure_type=failure_type(error), error=safe_error(error))
            raise
    original_text = concept_generation.call_llm
    def text_wrapper(prompt, **kwargs):
        if not enabled and any("当前任务：" + task + "\n" in prompt for task in ("image_prompt", "image_reference_check")):
            raise LLMError("Eval-only image generation disabled")
        return original_text(prompt, **kwargs)
    original_image = concept_generation.generate_image
    def image_wrapper(*args, **kwargs):
        if not enabled:
            from src.tools.image_generation import ImageGenerationError
            raise ImageGenerationError("Eval-only image generation disabled")
        try:
            return original_image(*args, **kwargs)
        except Exception:
            stats["image_failures"] += 1
            raise
    with ExitStack() as stack:
        for cls, method, kind in ((Completions, "create", "llm_calls"), (TavilyClient, "search", "search_calls"), (Images, "generate", "image_calls")):
            stack.enter_context(patch.object(cls, method, provider_wrapper(getattr(cls, method), kind)))
        for module in (nodes, site_analysis, case_research, concept_generation):
            stack.enter_context(patch.object(module, "call_llm_structured", structured_wrapper(module.call_llm_structured)))
        stack.enter_context(patch.object(concept_generation, "call_llm", text_wrapper))
        stack.enter_context(patch.object(concept_generation, "generate_image", image_wrapper))
        stack.enter_context(patch.object(case_research, "web_search", search_wrapper))
        stack.enter_context(patch.object(case_research, "_map_selected_cases", mapping_wrapper))
        yield stats


def run_case(case, *, images="off", judge=True, vision_supported=True, disable_image_generation=False):
    from src.agent.graph import graph
    from src.agent.state import create_initial_state
    paths = [str(ROOT / path) for path in case.site_images]
    state = create_initial_state(case.user_input, paths)
    trace = []
    started = perf_counter()
    status, failed = "success", None
    enabled = not disable_image_generation and images_enabled(case, images)
    with observe(enabled, record_nodes=True) as stats:
        recorder = stats["node_observer"]
        try:
            for path in paths:
                if not Path(path).is_file():
                    raise FileNotFoundError(path)
            for update in graph.stream(state, stream_mode="updates", config={"recursion_limit": 30, "callbacks": [recorder]}):
                for node, partial in update.items():
                    state.update(partial or {})
        except Exception as error:
            status, failed = "failed", failure_type(error)
        trace = deepcopy(recorder.trace)
        execution = {key: deepcopy(value) for key, value in stats.items() if key not in {"evidence", "node_observer"}}
        execution.update(status=status, failure_type=failed, runtime_seconds=perf_counter() - started,
                         image_generation_enabled=enabled,
                         image_generation_override=disable_image_generation,
                         dataset_image_generation_mode=case.image_generation_mode)
        if disable_image_generation:
            execution["image_generation_status"] = "skipped_override"
            if execution["image_calls"] != 0:
                raise RuntimeError("Evaluation image override did not prevent Image SDK calls")
        evidence = deepcopy(stats["evidence"])
    # Judge costs/calls do not inflate Agent execution metrics.
    quality = {}
    judge_failures = []
    with observe(False) as judge_stats:
        for name in RUBRICS:
            readiness = quality_readiness(case, state, name, vision_supported=vision_supported)
            if readiness["status"] != "ready":
                quality[name] = readiness
            elif not judge:
                quality[name] = {**metric(None, reason="Judge disabled"), "status": "unavailable"}
            else:
                try:
                    quality[name] = judge_metric(case, state, name, evidence=evidence, vision_supported=vision_supported)
                except Exception as error:
                    failure = {"metric": name, "failure_stage": "judge", "failure_type": failure_type(error),
                               "exception_type": type(error).__name__, "error": safe_error(error)}
                    quality[name] = {**metric(None, reason="Judge failed; score unavailable"),
                                     "status": "unavailable", **failure}
                    judge_failures.append(failure)
        judge_execution = {key: deepcopy(judge_stats[key]) for key in ("llm_calls", "tokens", "cost")}
    for entry in trace:
        for key in ("source_candidate_comparisons", "source_validation_diagnostics"):
            for row in entry.get(key, []):
                row["case_id"] = case.case_id
    return {"dataset_version": case.dataset_version, "case_id": case.case_id, "execution": execution,
            "decision_metrics": rule_metrics(case, state, trace, execution), "quality_metrics": quality,
            "usable": quality["end_to_end_usability"]["score"] >= 4 if quality["end_to_end_usability"]["score"] is not None else None,
            "judge_execution": judge_execution, "judge_failures": judge_failures,
            "agent_output": state, "execution_trace": trace, "retrieval_evidence": evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit evaluation run; no default baseline")
    parser.add_argument("--case", action="append", help="Repeat for multiple cases")
    parser.add_argument("--all", action="store_true", help="Explicitly run all ten frozen cases")
    parser.add_argument("--images", choices=("on", "off"), default="off", help="Only controls optional cases")
    parser.add_argument("--disable-image-generation", action="store_true",
                        help="Eval-only override: skip all image generation, including required cases; input images retained")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--vision-unsupported", action="store_true", help="Explicit known capability: Case 02 visual quality metrics N/A; input images retained")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cases = load_dataset()
    if bool(args.case) == args.all:
        parser.error("Select --case (repeatable) OR --all")
    if args.case and not set(args.case) <= {case.case_id for case in cases}:
        parser.error("Unknown case ID")
    selected = cases if args.all else [case for case in cases if case.case_id in args.case]
    directory = args.output or ROOT / "outputs/evals" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {"dataset_version": "1.0", "case_ids": [case.case_id for case in selected],
                "status": "running", "disable_image_generation": args.disable_image_generation,
                "image_generation_override": args.disable_image_generation,
                "image_generation_policy": "skip_real_generation" if args.disable_image_generation else "dataset",
                "optional_images_requested": args.images,
                "dataset_image_generation_modes": {case.case_id: case.image_generation_mode for case in selected}}
    metadata_path = directory / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    results = []
    for case in selected:
        # Judge failures are per-metric observations, never a run health assertion.
        result = run_case(case, images=args.images, judge=not args.no_judge, vision_supported=not args.vision_unsupported,
                          disable_image_generation=args.disable_image_generation)
        (directory / f"{case.case_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(result)
        print(case.case_id, result["execution"]["status"])
    (directory / "summary.json").write_text(json.dumps(aggregate(results), ensure_ascii=False, indent=2), encoding="utf-8")
    metadata.update(status="completed", completed_cases=len(results),
                    image_calls=sum(result["execution"]["image_calls"] for result in results))
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(directory)


if __name__ == "__main__":
    main()
