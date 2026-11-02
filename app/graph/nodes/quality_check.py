"""Bounded evaluator–optimizer: rules + semantic advice, always before a person."""
import asyncio
from datetime import datetime, timezone
from app.graph.quality import rule_checks, remaining_tokens, input_estimate
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics
from app.services import get_llm_service


async def quality_check_node(state: dict) -> dict:
    policy = state.get("quality_policy", {})
    if not policy.get("enabled", False):
        return {"quality_report": {"status": "disabled", "route": "manual",
            "reason": "历史会话或配置未启用质量检查"}, "pending_revision_source": ""}
    versions = state.get("article_versions", [])
    report = {"version_id": versions[-1]["version_id"] if versions else "legacy",
        "created_at": datetime.now(timezone.utc).isoformat(), "checks": [],
        "status": "needs_revision", "route": "manual", "reason": ""}
    article = state.get("article_content", "")
    brief = state.get("content_brief", {})
    report["checks"] = rule_checks(article, brief)
    used = state.get("quality_tokens_used", 0)
    budget = remaining_tokens(state)
    metric = None
    service = get_llm_service()
    with MetricsContext("quality_check") as tracker:
        try:
            messages = service.build_quality_messages(article, state.get("topic_direction", ""),
                state.get("selected_topic", ""), brief, state.get("review_feedback", ""))
            reserve_input = input_estimate("".join(m.content for m in messages))
            output_limit = min(1800, budget - reserve_input)
            if output_limit < 256:
                report.update(status="budget_exhausted", reason="质量检查预算不足，交人工审核")
            else:
                review, usage = await asyncio.wait_for(service.evaluate_article(article,
                    state.get("topic_direction", ""), state.get("selected_topic", ""),
                    brief, state.get("review_feedback", ""), max_output_tokens=output_limit),
                    timeout=policy.get("timeout_seconds", 45))
                used += usage.total_tokens
                tracker.set_llm_usage(LLMUsage(usage.input_tokens, usage.output_tokens, usage.total_tokens, usage.model))
                report["checks"] += [item.model_dump() for item in review.checks]
                report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "needs_revision"
                metric = {"usage_source": usage.usage_source}
        except Exception as exc:
            # The supplier may have processed a failed request. Reserve it, don't silently retry.
            used += min(budget, max(0, locals().get("reserve_input", 0)) + 1800)
            report.update(status="check_failed", reason="质量检查失败，草稿已保留，请人工审核",
                          error_type=type(exc).__name__)
            metric = {"usage_source": "reserved_unknown", "failed": True}
    failures = [c for c in report["checks"] if not c["passed"]]
    feedback = "\n".join(c["suggestion"] or c["issue"] for c in failures)
    if state.get("review_feedback"):
        feedback = "用户修改意见：" + state["review_feedback"] + "\n质量检查建议：\n" + feedback
    if report["status"] == "needs_revision":
        if state.get("automation_stop_reason"):
            report["reason"] = state["automation_stop_reason"]
        elif state.get("auto_revisions_this_review", 0) >= policy.get("max_auto_per_review", 1):
            report["reason"] = "已达本轮自动修订上限，交人工审核"
        elif state.get("auto_revision_count", 0) >= policy.get("max_auto_total", 3):
            report["reason"] = "已达工作流累计自动修订上限，交人工审核"
        else:
            try:
                prompt = service._build_article_prompt(state.get("selected_topic", ""), feedback,
                    state.get("revision_count", 0), state.get("topic_direction", ""), article, brief)
                required = input_estimate(prompt + service.ARTICLE_SYSTEM_PROMPT) + 256
                if policy.get("token_budget", 30000) - used < required:
                    report["reason"] = "自动修订预算不足，交人工审核"
                else:
                    report["route"] = "auto"
            except ValueError:
                report["reason"] = "修改上下文过长，交人工审核"
    metric = {**tracker.to_dict(), **(metric or {}), "version_id": report["version_id"]}
    return {"quality_report": report,
        "quality_history": list(state.get("quality_history", [])) + [report],
        "quality_tokens_used": used, "auto_feedback": feedback,
        "pending_revision_source": "auto" if report["route"] == "auto" else "",
        "node_metrics": merge_metrics(state.get("node_metrics", []), metric)}


def route_quality(state: dict) -> str:
    return "write_draft" if state.get("pending_revision_source") == "auto" else "human_review"
