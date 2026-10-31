"""
LangChain Callback 模块
提供 LLM 调用的脱敏、日志记录等功能
"""
from typing import Any, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app.core.pii_anonymizer import default_anonymizer, PIIAnonymizer
from app.core.logger import get_logger

logger = get_logger(__name__)


class PIIAnonymizingCallback(BaseCallbackHandler):
    """
    PII 脱敏回调处理器
    
    在 LLM 输入/输出时自动脱敏敏感信息
    
    注意：此回调会修改发送到 LangSmith 的数据，
    确保追踪日志中不包含敏感信息
    """
    
    def __init__(
        self,
        anonymizer: Optional[PIIAnonymizer] = None,
        anonymize_input: bool = True,
        anonymize_output: bool = True,
    ):
        """
        初始化 PII 脱敏回调
        
        Args:
            anonymizer: PII 脱敏器实例，默认使用全局实例
            anonymize_input: 是否脱敏输入
            anonymize_output: 是否脱敏输出
        """
        super().__init__()
        self.anonymizer = anonymizer or default_anonymizer
        self.anonymize_input = anonymize_input
        self.anonymize_output = anonymize_output
    
    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用开始时脱敏 prompt"""
        if self.anonymize_input:
            for i, prompt in enumerate(prompts):
                prompts[i] = self.anonymizer.anonymize(prompt)
    
    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Chat 模型调用开始时脱敏消息"""
        if self.anonymize_input:
            for message_list in messages:
                for message in message_list:
                    if hasattr(message, 'content') and isinstance(message.content, str):
                        message.content = self.anonymizer.anonymize(message.content)
    
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束时脱敏输出"""
        if self.anonymize_output:
            for generations in response.generations:
                for generation in generations:
                    if hasattr(generation, 'text') and generation.text:
                        generation.text = self.anonymizer.anonymize(generation.text)
                    if hasattr(generation, 'message') and hasattr(generation.message, 'content'):
                        if isinstance(generation.message.content, str):
                            generation.message.content = self.anonymizer.anonymize(
                                generation.message.content
                            )
    
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用出错时记录日志"""
        logger.error(
            "llm_error",
            error=str(error),
            run_id=str(run_id),
        )


# 全局 PII 脱敏回调实例
pii_callback = PIIAnonymizingCallback()
