"""
FastAPI 中间件模块
提供请求日志记录、request_id 注入等功能
"""
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logger import (
    app_logger,
    set_request_id,
    clear_request_id,
    get_request_id,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    
    功能：
    1. 为每个请求生成唯一的 request_id
    2. 记录请求开始和结束
    3. 计算请求耗时
    4. 记录异常
    """
    
    # 不记录日志的路径（健康检查等）
    SKIP_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过不需要记录的路径
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)
        
        # 生成 request_id（优先使用请求头中的，便于链路追踪）
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        set_request_id(request_id)
        
        # 获取客户端 IP
        client_ip = self._get_client_ip(request)
        
        # 记录请求开始
        start_time = time.perf_counter()
        app_logger.request_started(
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            query_params=str(request.query_params) if request.query_params else None,
        )
        
        # 处理请求
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            
            # 添加 request_id 到响应头（便于客户端追踪）
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # 记录异常
            app_logger.request_error(
                method=request.method,
                path=request.url.path,
                error=str(e),
                status_code=500,
            )
            raise
            
        finally:
            # 计算耗时并记录请求完成
            duration_ms = (time.perf_counter() - start_time) * 1000
            app_logger.request_finished(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            # 清除 request_id
            clear_request_id()
    
    def _get_client_ip(self, request: Request) -> str:
        """获取客户端真实 IP"""
        # 优先从代理头获取
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # 直接连接的客户端
        if request.client:
            return request.client.host
        
        return "unknown"


class LangSmithTracingMiddleware(BaseHTTPMiddleware):
    """
    LangSmith 链路追踪中间件
    
    将 request_id 传递给 LangSmith，实现日志与 LLM 追踪的关联
    
    使用方式：在 LLM 调用时，可以通过 langsmith.traceable 装饰器的 
    metadata 参数传递 request_id
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 将 request_id 存储到 request.state，供后续使用
        request.state.request_id = get_request_id()
        
        # 可以在这里设置 LangSmith 的 run 名称或 metadata
        # 通过环境变量或 contextvars 传递给 LangChain
        
        response = await call_next(request)
        return response
