"""
视觉内容生成节点
负责从文章中提取配图要点并生成图片
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service, get_image_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def extract_visuals_node(state: AgentState) -> Dict[str, Any]:
    """
    提取视觉要点节点
    
    从文章内容中提取适合配图的要点
    
    Args:
        state: 当前工作流状态
        
    Returns:
        更新后的状态字段
    """
    article_content = state.get("article_content", "")
    existing_metrics = state.get("node_metrics", [])
    
    if not article_content:
        return {
            "visual_points": [],
            "status": "error",
            "error": "文章内容为空，无法提取视觉要点",
        }
    
    with MetricsContext("extract_visuals") as tracker:
        try:
            # 获取 LLM 服务
            llm_service = get_llm_service()
            visual_points, usage_info = await llm_service.extract_visual_points(article_content)
            
            # 记录 LLM 使用信息
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))
            
            result = {
                "visual_points": visual_points,
                "status": "visuals_extracted",
                "error": "",
            }
            
        except Exception as e:
            raise RuntimeError("提取配图要点失败，请重试") from e

    # 在 with 块结束后（tracker.stop() 已被调用），再获取指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result


async def generate_images_node(state: AgentState) -> Dict[str, Any]:
    """
    生成配图节点
    
    根据视觉要点生成配图（部分失败时仍会返回成功的图片）
    
    Args:
        state: 当前工作流状态
        
    Returns:
        更新后的状态字段
    """
    visual_points = state.get("visual_points", [])
    existing_metrics = state.get("node_metrics", [])
    
    if not visual_points:
        return {
            "image_urls": [],
            "status": "images_failed",
            "error": "视觉要点为空，跳过配图生成",
        }
    
    with MetricsContext("generate_images") as tracker:
        try:
            # 获取图片服务
            image_service = get_image_service()
            image_urls = await image_service.generate_images(visual_points)
            
            # 即使部分图片生成失败，也标记为完成
            if len(image_urls) < len(visual_points):
                error_msg = f"部分配图生成失败 ({len(image_urls)}/{len(visual_points)} 成功)"
            else:
                error_msg = ""
            
            result = {
                "image_urls": image_urls,
                "status": "completed" if not error_msg else "images_failed",
                "error": error_msg,
            }
            
        except Exception as e:
            # 即使全部失败，也标记为完成（不阻塞工作流）
            result = {
                "image_urls": [],
                "status": "images_failed",
                "error": f"配图生成失败: {str(e)[:100]}",
            }
    
    # 在 with 块结束后（tracker.stop() 已被调用），再获取指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
