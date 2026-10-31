"""
FastAPI 应用入口
AI 内容运营助手后端服务 (v1.1 - 添加日志系统)
"""
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import os
import asyncio
from sqlalchemy import text
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.db import init_db, close_db, engine
from app.core.logger import setup_logging, app_logger
from app.core.middleware import RequestLoggingMiddleware
from app.graph.utils import setup_checkpointer, close_checkpointer
from app.graph.workflow import reset_graph
from app.api.v1.workflow import router as workflow_router
from app.api.v1.image import router as image_router
from app.api.v1.auth import router as auth_router

# 初始化日志系统（在导入其他模块之前）
setup_logging(
    log_level=settings.log_level,
    log_target=settings.log_target,
    log_dir=settings.log_dir,
    json_logs=settings.log_json,
    console_output=settings.log_console,
    pii_anonymize=settings.log_pii_anonymize,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理
    
    启动时：
    - 初始化数据库连接
    - 初始化 LangGraph Checkpointer（创建必要的表）
    
    关闭时：
    - 关闭数据库连接
    - 关闭 Checkpointer 连接池
    """
    # 启动时执行
    app_logger.info(f"Starting {settings.app_name}...")
    
    try:
        # 初始化 SQLAlchemy 数据库
        app_logger.info("Initializing database connection...")
        await init_db()
        app_logger.db_connected(database_url=settings.database_url.split("@")[-1])  # 不记录密码
        
        # 初始化 LangGraph Checkpointer
        app_logger.info("Initializing LangGraph Checkpointer...")
        await reset_graph()
        await setup_checkpointer()
        
        app_logger.service_started(
            app_name=settings.app_name,
            debug=settings.debug,
            log_level=settings.log_level,
            docs_url="http://localhost:8000/docs"
        )
        
        # 同时保留控制台输出，方便开发时查看
        print(f"[OK] {settings.app_name} started successfully!")
        print(f"[Docs] API docs: http://localhost:8000/docs")
        print(f"[Logs] Log files: {settings.log_dir}/")
        
    except Exception as e:
        app_logger.error(f"Startup failed: {str(e)}", error=str(e))
        raise
    
    yield
    
    # 关闭时执行
    app_logger.info(f"Stopping {settings.app_name}...")
    
    try:
        await reset_graph()
        await close_checkpointer()
        await close_db()
        app_logger.db_disconnected()
        app_logger.service_stopped(app_name=settings.app_name)
    except Exception as e:
        app_logger.warning(f"Error during shutdown: {str(e)}", error=str(e))


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="""
## AI 内容运营助手 API

为教育培训公司提供的自动化内容生成工作流服务。

### 核心功能

- **选题生成**: AI 根据主题方向生成多个候选选题
- **文章撰写**: AI 根据选定选题生成技术文章
- **人工审核**: 支持通过/驳回机制，驳回后可重写
- **配图生成**: 自动提取视觉要点并生成配图

### 工作流程

1. 启动工作流，AI 生成候选选题
2. 人工选择一个选题
3. AI 生成文章草稿
4. 人工审核（通过/驳回）
5. 通过后自动生成配图
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# 配置中间件（注意顺序：先添加的后执行）
# 1. 请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 2. CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(image_router, prefix="/api/v1")

# 挂载静态文件目录（用于访问生成的图片）
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """根路径 - 服务健康检查"""
    return {
        "service": settings.app_name,
        "status": "running",
        "version": "1.0.0",
        "mock": os.getenv("MOCK_MODE", "false").lower() == "true",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    async def probe_database():
        async with engine.connect() as connection:
            await connection.execute(text('SELECT 1'))
    try:
        await asyncio.wait_for(probe_database(), timeout=2)
    except Exception:
        return JSONResponse({'status': 'unavailable', 'detail': '数据库暂不可用'}, status_code=503)
    return {
        "status": "healthy",
        "service": settings.app_name,
        "mock": os.getenv("MOCK_MODE", "false").lower() == "true"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
