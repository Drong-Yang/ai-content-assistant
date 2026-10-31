"""
应用配置模块
使用 pydantic-settings 管理环境变量
"""
from pathlib import Path
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # 应用配置
    app_name: str = "AI内容运营助手"
    debug: bool = True
    
    # 数据库配置 (SQLAlchemy AsyncIO)
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/aicontent"
    
    # PostgreSQL 连接配置 (psycopg3 / LangGraph Checkpointer)
    postgres_uri: str = "postgresql://postgres:password@localhost:5432/aicontent"
    
    # ============== 日志配置 ==============
    # 日志级别: DEBUG, INFO, WARNING, ERROR
    log_level: str = "INFO"
    
    # 日志输出目标: file, loki, aliyun, volcengine
    # 目前支持 file，后续可扩展云服务
    log_target: Literal["file", "loki", "aliyun", "volcengine"] = "file"
    
    # 日志文件目录
    log_dir: str = "logs"
    
    # 是否输出 JSON 格式（文件始终是 JSON，此选项影响控制台）
    log_json: bool = False
    
    # 是否在控制台输出日志（开发时建议开启）
    log_console: bool = True
    
    # 是否启用 PII 脱敏（邮箱、信用卡、API Key、手机号）
    log_pii_anonymize: bool = True
    
    # ============== JWT 认证配置 ==============
    jwt_secret_key: str = "your-super-secret-key-change-in-production-2024"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24小时
    
    @property
    def async_database_url(self) -> str:
        """获取异步数据库 URL"""
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
