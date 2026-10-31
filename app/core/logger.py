"""
日志系统模块
使用 structlog 实现结构化日志，支持：
- JSON 文件输出（按天轮转）
- 控制台彩色输出（开发模式）
- 预留云服务接口（阿里云 SLS / 火山引擎 TLS / Loki 等）

迁移到云服务时，只需修改 LOG_TARGET 环境变量并添加对应的 handler
"""
import os
import sys
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from logging.handlers import TimedRotatingFileHandler
from contextvars import ContextVar

import structlog
from structlog.types import Processor

from app.core.pii_anonymizer import pii_anonymize_processor

# ============== Context Variables ==============
# 用于在请求生命周期内传递 request_id
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """获取当前请求的 request_id，如果没有则生成一个"""
    rid = request_id_var.get()
    if rid is None:
        rid = str(uuid.uuid4())[:8]  # 使用短 ID
        request_id_var.set(rid)
    return rid


def set_request_id(rid: str) -> None:
    """设置当前请求的 request_id"""
    request_id_var.set(rid)


def clear_request_id() -> None:
    """清除当前请求的 request_id"""
    request_id_var.set(None)


# ============== Custom Processors ==============

def add_request_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """添加 request_id 到日志事件"""
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def add_service_info(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """添加服务信息"""
    event_dict["service"] = os.getenv("APP_NAME", "xiaohongshu-assistant")
    return event_dict


# ============== Logger Setup ==============

def setup_logging(
    log_level: str = "INFO",
    log_target: str = "file",
    log_dir: str = "logs",
    json_logs: bool = True,
    console_output: bool = True,
    pii_anonymize: bool = True,
) -> None:
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_target: 日志输出目标 (file, loki, aliyun, volcengine)
        log_dir: 日志文件目录
        json_logs: 是否输出 JSON 格式
        console_output: 是否同时输出到控制台
    """
    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 获取数字日志级别
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # ============== 配置标准 logging ==============
    
    # 移除所有已有 handlers
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(numeric_level)
    
    # 创建 handlers 列表
    handlers = []
    
    # 文件 Handler（按天轮转）
    if log_target == "file":
        log_file = log_path / "app.log"
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",  # 按天轮转
            interval=1,
            backupCount=30,  # 保留 30 天
            encoding="utf-8",
        )
        file_handler.suffix = "%Y-%m-%d"  # 文件后缀格式
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)
    
    # 控制台 Handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        handlers.append(console_handler)
    
    # 添加 handlers 到 root logger
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # ============== 配置 structlog ==============
    
    # 共享处理器（所有输出目标都使用）
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        add_service_info,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    # 添加 PII 脱敏处理器（在输出前脱敏）
    if pii_anonymize:
        shared_processors.append(pii_anonymize_processor)
    
    # 根据是否输出到控制台选择不同的渲染器
    if console_output and not json_logs:
        # 开发模式：控制台彩色输出
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        # 生产模式：JSON 输出
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    
    # 配置 structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 为所有 handlers 设置 formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        # 控制台使用彩色，文件使用 JSON
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    
    # 为文件 handler 设置 JSON formatter
    json_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    
    # 控制台彩色 formatter
    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )
    
    # 分别设置 formatter
    for handler in root_logger.handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            handler.setFormatter(json_formatter)  # 文件始终用 JSON
        elif isinstance(handler, logging.StreamHandler):
            handler.setFormatter(console_formatter)  # 控制台用彩色


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    获取 logger 实例
    
    Args:
        name: logger 名称，通常使用 __name__
        
    Returns:
        structlog BoundLogger 实例
    """
    return structlog.get_logger(name)


# ============== 业务日志辅助函数 ==============

class AppLogger:
    """
    应用级别日志记录器
    提供语义化的日志方法，方便记录不同类型的事件
    """
    
    def __init__(self, name: str = "app"):
        self._logger = get_logger(name)
    
    # ---------- 系统事件 ----------
    
    def service_started(self, **kwargs: Any) -> None:
        """服务启动"""
        self._logger.info("service_started", **kwargs)
    
    def service_stopped(self, **kwargs: Any) -> None:
        """服务停止"""
        self._logger.info("service_stopped", **kwargs)
    
    def db_connected(self, **kwargs: Any) -> None:
        """数据库连接成功"""
        self._logger.info("db_connected", **kwargs)
    
    def db_disconnected(self, **kwargs: Any) -> None:
        """数据库断开连接"""
        self._logger.info("db_disconnected", **kwargs)
    
    def db_error(self, error: str, **kwargs: Any) -> None:
        """数据库错误"""
        self._logger.error("db_error", error=error, **kwargs)
    
    # ---------- API 请求事件 ----------
    
    def request_started(
        self,
        method: str,
        path: str,
        client_ip: str = "",
        **kwargs: Any
    ) -> None:
        """API 请求开始"""
        self._logger.info(
            "request_started",
            method=method,
            path=path,
            client_ip=client_ip,
            **kwargs
        )
    
    def request_finished(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        **kwargs: Any
    ) -> None:
        """API 请求完成"""
        log_method = self._logger.info if status_code < 400 else self._logger.warning
        log_method(
            "request_finished",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            **kwargs
        )
    
    def request_error(
        self,
        method: str,
        path: str,
        error: str,
        status_code: int = 500,
        **kwargs: Any
    ) -> None:
        """API 请求错误"""
        self._logger.error(
            "request_error",
            method=method,
            path=path,
            error=error,
            status_code=status_code,
            **kwargs
        )
    
    # ---------- 工作流事件 ----------
    
    def workflow_started(
        self,
        thread_id: str,
        topic_direction: str,
        **kwargs: Any
    ) -> None:
        """工作流启动"""
        self._logger.info(
            "workflow_started",
            thread_id=thread_id,
            topic_direction=topic_direction,
            **kwargs
        )
    
    def workflow_stage_changed(
        self,
        thread_id: str,
        stage: str,
        **kwargs: Any
    ) -> None:
        """工作流阶段变化"""
        self._logger.info(
            "workflow_stage_changed",
            thread_id=thread_id,
            stage=stage,
            **kwargs
        )
    
    def topic_selected(
        self,
        thread_id: str,
        selected_topic: str,
        **kwargs: Any
    ) -> None:
        """选题选择"""
        self._logger.info(
            "topic_selected",
            thread_id=thread_id,
            selected_topic=selected_topic,
            **kwargs
        )
    
    def draft_generated(
        self,
        thread_id: str,
        word_count: int = 0,
        **kwargs: Any
    ) -> None:
        """草稿生成完成"""
        self._logger.info(
            "draft_generated",
            thread_id=thread_id,
            word_count=word_count,
            **kwargs
        )
    
    def draft_approved(self, thread_id: str, **kwargs: Any) -> None:
        """草稿审核通过"""
        self._logger.info(
            "draft_approved",
            thread_id=thread_id,
            **kwargs
        )
    
    def draft_rejected(
        self,
        thread_id: str,
        feedback: str = "",
        revision_count: int = 0,
        **kwargs: Any
    ) -> None:
        """草稿被驳回"""
        self._logger.info(
            "draft_rejected",
            thread_id=thread_id,
            feedback=feedback,
            revision_count=revision_count,
            **kwargs
        )
    
    def workflow_completed(
        self,
        thread_id: str,
        duration_ms: float = 0,
        **kwargs: Any
    ) -> None:
        """工作流完成"""
        self._logger.info(
            "workflow_completed",
            thread_id=thread_id,
            duration_ms=round(duration_ms, 2),
            **kwargs
        )
    
    def workflow_error(
        self,
        thread_id: str,
        error: str,
        stage: str = "",
        **kwargs: Any
    ) -> None:
        """工作流错误"""
        self._logger.error(
            "workflow_error",
            thread_id=thread_id,
            error=error,
            stage=stage,
            **kwargs
        )
    
    # ---------- 通用方法 ----------
    
    def info(self, message: str, **kwargs: Any) -> None:
        """记录 INFO 级别日志"""
        self._logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """记录 WARNING 级别日志"""
        self._logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        """记录 ERROR 级别日志"""
        self._logger.error(message, **kwargs)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """记录 DEBUG 级别日志"""
        self._logger.debug(message, **kwargs)
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """记录异常（包含堆栈信息）"""
        self._logger.exception(message, **kwargs)


# ============== 全局 Logger 实例 ==============
app_logger = AppLogger("xiaohongshu-assistant")
