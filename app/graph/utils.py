"""
LangGraph 工具函数模块
包含 Checkpointer 初始化等工具函数

LangGraph 1.0+ 语法

使用 PostgreSQL 模式：使用 AsyncPostgresSaver，数据持久化到数据库
"""
import psycopg
from psycopg.rows import dict_row
from typing import Union

from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings

# 全局 Checkpointer 实例
_checkpointer: Union[AsyncPostgresSaver, None] = None
# 全局连接池实例
_connection_pool: AsyncConnectionPool | None = None


async def setup_checkpointer() -> BaseCheckpointSaver:
    """
    设置并初始化 Checkpointer
    
    使用 AsyncPostgresSaver (PostgreSQL 持久化)
    
    Returns:
        配置好的 Checkpointer 实例
    """
    global _checkpointer, _connection_pool
    
    if _checkpointer is not None:
        return _checkpointer
    
    # 使用 PostgreSQL Checkpointer (数据持久化)
    print(f"[Checkpointer] Connecting to PostgreSQL: {settings.postgres_uri.split('@')[-1]}")
    
    # 首先使用 autocommit 模式的连接来执行 setup()
    # 因为 CREATE INDEX CONCURRENTLY 不能在事务块中运行
    async with await psycopg.AsyncConnection.connect(
        settings.postgres_uri,
        autocommit=True, row_factory=dict_row, prepare_threshold=0
    ) as setup_conn:
        # 创建临时 checkpointer 用于 setup
        temp_checkpointer = AsyncPostgresSaver(setup_conn)
        await temp_checkpointer.setup()
        print("[OK] Checkpointer tables created/verified")
    
    # 创建异步连接池用于正常操作
    _connection_pool = AsyncConnectionPool(
        conninfo=settings.postgres_uri,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        open=False,  # 稍后手动打开
    )
    
    # 打开连接池
    await _connection_pool.open()
    
    # 创建 PostgreSQL Checkpointer
    _checkpointer = AsyncPostgresSaver(_connection_pool)
    
    print("[OK] PostgreSQL Checkpointer initialized - data will persist")
    
    return _checkpointer


async def get_checkpointer() -> BaseCheckpointSaver:
    """
    获取已初始化的 Checkpointer 实例
    
    Returns:
        Checkpointer 实例 (AsyncPostgresSaver)
        
    Raises:
        RuntimeError: 如果 Checkpointer 未初始化
    """
    global _checkpointer
    
    if _checkpointer is None:
        return await setup_checkpointer()
    
    return _checkpointer


async def close_checkpointer() -> None:
    """
    关闭 Checkpointer 和连接池
    
    需要关闭连接池释放资源
    """
    global _checkpointer, _connection_pool
    
    if _connection_pool is not None:
        # 关闭 PostgreSQL 连接池
        await _connection_pool.close()
        _connection_pool = None
        print("[Checkpointer] PostgreSQL connection pool closed")
    
    _checkpointer = None
    print("[Checkpointer] Cleaned up")
