"""
文章写作节点
负责根据选定的选题生成文章内容
使用流式输出（非结构化）+ token统计
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def write_draft_node(state: AgentState) -> Dict[str, Any]:
    """
    文章写作节点（流式输出 + 非结构化）
    
    根据选定的选题，调用 LLM 流式生成文章草稿
    如果有修改意见，则根据意见进行修订
    
    注意：这里使用流式方法调用 LLM，配合 graph.astream_events 可以
    实现 token 级别的流式输出到客户端
    
    Args:
        state: 当前工作流状态
        
    Returns:
        更新后的状态字段，包含：
        - article_content: 生成的文章内容
        - node_metrics: 节点执行指标（包含 token 统计）
    """
    selected_topic = state.get("selected_topic", "")
    review_feedback = state.get("review_feedback", "")
    revision_count = state.get("revision_count", 0)
    existing_metrics = state.get("node_metrics", [])
    
    if not selected_topic:
        return {
            "article_content": "",
            "status": "error",
            "error": "未选择选题，无法生成文章",
        }
    
    with MetricsContext("write_draft") as tracker:
        try:
            # 如果有修改意见，增加修订计数
            if review_feedback:
                revision_count += 1
            
            # 获取 LLM 服务
            llm_service = get_llm_service()
            
            # 使用流式输出方法，收集完整内容并获取 token 统计
            stream_result = await llm_service.stream_write_draft_with_usage(
                topic=selected_topic,
                feedback=review_feedback,
                revision_count=revision_count
            )
            
            article_content = stream_result.content
            usage_info = stream_result.usage
            
            # 记录 LLM 使用信息
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))
            
            result = {
                "article_content": article_content,
                "revision_count": revision_count,
                "review_status": "pending",
                "status": "draft_generated",
                "error": "",
            }
            
        except Exception as e:
            raise RuntimeError("模型节点执行失败，请检查配置后重试") from e

    # 在 with 块结束后（tracker.stop() 已被调用），再获取指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
