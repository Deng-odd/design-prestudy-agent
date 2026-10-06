"""Rule metrics, explicit applicability and separate A/B/C aggregation."""
from math import ceil
from statistics import median


def metric(score=None, *, applicable=True, reason=""):
    return {"applicable": applicable, "score": score, "reason": reason}


def rule_metrics(case, state, trace, execution):
    visits = [event["node"] for event in trace]
    result = {}
    for name, expected, actual in (
        ("info_sufficiency_decision", case.expected_info_sufficient, state.get("info_sufficient")),
        ("case_research_decision", case.expected_need_case_research, state.get("need_case_research")),
    ):
        result[name] = metric(None, applicable=False, reason="No applicable ground truth") if expected is None else metric(actual == expected, reason="Decision State compared with frozen expected behavior; downstream success is separate") if actual is not None else metric(None, reason="Decision not produced; unavailable")
    research = [i for i, event in enumerate(trace) if event["node"] == "check_research" and event.get("status", "success") == "success"]
    valid = True
    for i in research:
        event = trace[i]
        enough = event["update"].get("research_sufficient")
        attempts = event["state"].get("search_attempts", 0)
        next_node = trace[i + 1]["node"] if i + 1 < len(trace) else None
        target = "concept_generation" if enough or attempts >= 2 else "refine_search"
        # A missing downstream execution does not invalidate an already produced decision.
        if next_node is not None:
            valid &= next_node == target
        valid &= isinstance(enough, bool)
        if not enough:
            valid &= bool(event["update"].get("research_gaps"))
    result["research_sufficiency_decision"] = metric(valid, reason="Checks decision and gaps with entered downstream route; downstream success is separate") if research else metric(None, reason="Research decision failed before producing a result; unavailable") if "check_research" in visits else metric(None, applicable=False, reason="No research decision executed")
    completion = execution["status"] == "success" and (bool(state.get("final_report")) if case.expected_info_sufficient else visits == ["parse_and_check", "ask_user"])
    search_limit = state.get("search_attempts", 0) <= 2 and visits.count("case_research") <= 2
    regen = execution.get("concept_regenerations")
    result["workflow_compliance"] = {
        "search_limit": metric(search_limit),
        "concept_regeneration_limit": metric(regen <= 1) if regen is not None else metric(None, applicable=False, reason="Unavailable"),
        "fallback_correctness": metric(bool(state.get("final_report")) and "concept_generation" in visits) if execution.get("image_failures") or (research and state.get("research_sufficient") is False and state.get("search_attempts", 0) >= 2) else metric(None, applicable=False, reason="No fallback triggered"),
        "completion": metric(completion),
    }
    return result


def average(values):
    valid = [v["score"] for v in values if v.get("applicable") and v.get("score") is not None
             and ("status" not in v or v["status"] == "scored")]
    return {"average": sum(valid) / len(valid) if valid else None, "valid_cases": len(valid)}


def aggregate(results):
    decision = {}
    for key in ("info_sufficiency_decision", "case_research_decision", "research_sufficiency_decision"):
        decision[key] = average([r["decision_metrics"][key] for r in results])
    decision["workflow_compliance"] = {key: average([r["decision_metrics"]["workflow_compliance"][key] for r in results]) for key in ("search_limit", "concept_regeneration_limit", "fallback_correctness", "completion")}
    from evals.judge import RUBRICS
    quality = {key: average([r["quality_metrics"][key] for r in results]) for key in RUBRICS}
    times = sorted(r["execution"]["runtime_seconds"] for r in results)
    failures = [r["execution"]["failure_type"] for r in results if r["execution"]["status"] != "success"]
    operational = {"case_count": len(results), "runtime_median": median(times) if times else None,
                   "runtime_p95": times[ceil(.95 * len(times)) - 1] if times else None,
                   "failure_rate": len(failures) / len(results) if results else None,
                   "failure_types": {name: failures.count(name) for name in set(failures)}}
    for name in ("llm_calls", "search_calls", "image_calls", "tokens", "cost"):
        values = [r["execution"].get(name) for r in results]
        operational[name] = sum(values) if values and all(x is not None for x in values) else None
    return {"dataset_version": "1.0", "A_decision_workflow": decision, "B_quality": quality, "C_operational": operational}
