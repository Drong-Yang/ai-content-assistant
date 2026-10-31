"""
节点执行指标追踪模块
用于记录每个节点的执行时间和token使用量
"""
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class LLMUsage:
    """LLM 调用的 token 使用信息"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


class NodeMetricsTracker:
    """
    节点指标追踪器
    
    用于记录节点执行的开始/结束时间和token使用量
    """
    
    def __init__(self, node_name: str):
        self.node_name = node_name
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.duration_ms: float = 0.0
        self.llm_usage: Optional[LLMUsage] = None
    
    def start(self):
        """记录开始时间"""
        self.start_time = datetime.now()
    
    def stop(self):
        """记录结束时间并计算耗时"""
        self.end_time = datetime.now()
        if self.start_time:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000
    
    def set_llm_usage(self, usage: LLMUsage):
        """设置 LLM 使用信息"""
        self.llm_usage = usage
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "node_name": self.node_name,
            "duration_ms": round(self.duration_ms, 2),
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
        }
        
        if self.llm_usage:
            result.update({
                "input_tokens": self.llm_usage.input_tokens,
                "output_tokens": self.llm_usage.output_tokens,
                "total_tokens": self.llm_usage.total_tokens,
                "model": self.llm_usage.model,
            })
        else:
            result.update({
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "model": "",
            })
        
        return result


class MetricsContext:
    """
    指标上下文管理器
    
    使用方式：
    ```python
    async def my_node(state):
        with MetricsContext("my_node") as tracker:
            # 执行节点逻辑
            result, usage = await llm_service.call_with_metrics(...)
            tracker.set_llm_usage(usage)
        
        return {
            ...,
            "node_metrics": state.get("node_metrics", []) + [tracker.to_dict()]
        }
    ```
    """
    
    def __init__(self, node_name: str):
        self.tracker = NodeMetricsTracker(node_name)
    
    def __enter__(self) -> NodeMetricsTracker:
        self.tracker.start()
        return self.tracker
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tracker.stop()
        return False


def merge_metrics(existing_metrics: list, new_metric: Dict[str, Any]) -> list:
    """
    合并现有指标和新指标
    
    Args:
        existing_metrics: 现有的指标列表
        new_metric: 新的节点指标
        
    Returns:
        合并后的指标列表
    """
    metrics = list(existing_metrics) if existing_metrics else []
    metrics.append(new_metric)
    return metrics
