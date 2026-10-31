"""
安全模块 - JWT 认证与密码处理
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# 密码哈希上下文 - 使用 argon2（更安全，无长度限制）和 bcrypt 作为备选
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT access token
    
    Args:
        data: 要编码的数据（通常包含 sub: user_id）
        expires_delta: 过期时间增量
        
    Returns:
        JWT token 字符串
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt_secret_key, 
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码 JWT token
    
    Args:
        token: JWT token 字符串
        
    Returns:
        解码后的数据，失败返回 None
    """
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None
