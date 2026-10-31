"""
认证依赖 - 获取当前登录用户
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.core.security import decode_access_token
from app.models.user import User

# HTTP Bearer 认证方案
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """
    获取当前登录用户
    
    从 Authorization header 中获取 JWT token，验证并返回用户对象
    
    Args:
        credentials: HTTP Bearer 凭证
        db: 数据库会话
        
    Returns:
        当前登录的用户对象
        
    Raises:
        HTTPException: 401 认证失败
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    
    # 解码 token
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    # 获取用户 ID
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    # 查询用户
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_async_session)
) -> Optional[User]:
    """
    可选的用户认证（用于允许匿名访问的接口）
    
    Returns:
        用户对象或 None
    """
    if credentials is None:
        return None
    
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        return None
    
    user_id = payload.get("sub")
    if user_id is None:
        return None
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()
