"""Generate or revise against the original brief and the previous article."""
import asyncio
import uuid
from datetime import datetime, timezone
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics
from app.graph.quality import remaining_tokens, input_estimate


async def write_draft_node(state: AgentState) -> dict:
    if not state.get("selected_topic"):
        raise ValueError("未选择选题，无法生成文章")
    source = state.get("pending_revision_source") or (
        "human" if state.get("review_status") == "rejected" else "initial")
    previous = state.get("article_content", "")
    feedback = (state.get("auto_feedback", "") if source == "auto"
                else state.get("review_feedback", ""))
    human_count = state.get("revision_count", 0) + int(source == "human")
    service = get_llm_service()
    versions = list(state.get("article_versions", []))
    if previous and not versions:
        versions.append({"version_id": "legacy", "parent_version_id": None,
            "content": previous, "source": "legacy", "feedback": "", "created_at": ""})
    version_id = uuid.uuid4().hex
    prompt = service._build_article_prompt(state["selected_topic"], feedback, human_count,
        state.get("topic_direction", ""), previous, state.get("content_brief", {}))
    output_limit = max(2600, state.get("content_brief", {}).get("max_chars", 1200) * 2 + 256)
    if source == "auto":
        output_limit = min(output_limit, remaining_tokens(state) - input_estimate(prompt + service.ARTICLE_SYSTEM_PROMPT))
        if output_limit < 256:
            return {"pending_revision_source": "", "automation_stop_reason": "自动修订预算不足", "quality_report": {
                **state.get("quality_report", {}), "route": "manual", "reason": "自动修订预算不足"}}
    with MetricsContext("write_draft") as tracker:
        result = await asyncio.wait_for(service.stream_write_draft_with_usage(
            topic=state["selected_topic"], feedback=feedback, revision_count=human_count,
            topic_direction=state.get("topic_direction", ""), previous_article=previous,
            content_brief=state.get("content_brief", {}), max_output_tokens=output_limit,
            version_id=version_id), timeout=120)
        if not result.content.strip():
            raise ValueError("模型未生成正文，请重试")
        usage = result.usage
        tracker.set_llm_usage(LLMUsage(usage.input_tokens, usage.output_tokens, usage.total_tokens, usage.model))
    metric = {**tracker.to_dict(), "version_id": version_id, "source": source,
              "usage_source": usage.usage_source}
    versions.append({"version_id": version_id,
        "parent_version_id": versions[-1]["version_id"] if versions else None,
        "content": result.content, "feedback": feedback, "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(), "metric": metric})
    return {"article_content": result.content, "article_versions": versions,
        "revision_count": human_count,
        "auto_revision_count": state.get("auto_revision_count", 0) + int(source == "auto"),
        "auto_revisions_this_review": state.get("auto_revisions_this_review", 0) + int(source == "auto"),
        "quality_tokens_used": state.get("quality_tokens_used", 0) + (usage.total_tokens if source == "auto" else 0),
        "pending_revision_source": "", "review_status": "pending", "status": "draft_generated", "error": "",
        "node_metrics": merge_metrics(state.get("node_metrics", []), metric)}
