"""
选题规划节点
负责根据用户输入的主题方向生成候选选题
使用结构化输出（非流式）+ token统计
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def plan_topics_node(state: AgentState) -> Dict[str, Any]:
    """
    选题规划节点（结构化输出 + 非流式）
    
    根据用户输入的主题方向，调用 LLM 生成候选选题列表
    
    Args:
        state: 当前工作流状态
        
    Returns:
        更新后的状态字段，包含：
        - generated_topics: 选题标题列表（5个）
        - node_metrics: 节点执行指标（包含 token 统计）
    """
    topic_direction = state.get("topic_direction", "")
    existing_metrics = state.get("node_metrics", [])
    
    with MetricsContext("plan_topics") as tracker:
        try:
            # 获取 LLM 服务
            llm_service = get_llm_service()
            
            # 使用结构化输出方法
            topics_response, usage_info = await llm_service.plan_topics(topic_direction)
            
            # 记录 LLM 使用信息
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))
            
            if not topics_response.topics:
                raise ValueError("模型未生成选题")
            # 提取标题列表
            generated_topics = [topic.title for topic in topics_response.topics]
            
            result = {
                "generated_topics": generated_topics,
                "status": "topics_generated",
                "error": "",
            }
            
        except Exception as e:
            raise RuntimeError("模型节点执行失败，请检查配置后重试") from e

    # 在 with 块结束后（tracker.stop() 已被调用），再获取指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
