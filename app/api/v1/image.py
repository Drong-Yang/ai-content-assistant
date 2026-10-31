"""
图片生成测试接口
使用 火山方舟图片模型 生成小红书风格配图
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from app.dependencies.auth import get_current_user
from app.models.user import User
from pydantic import BaseModel, Field

from app.services import get_image_service

router = APIRouter(prefix="/image", tags=["Image"])


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., description="图片描述文案")
    optimize_for_xhs: bool = Field(True, description="是否优化为小红书爆款风格")


class GenerateImageResponse(BaseModel):
    url: Optional[str] = Field(None, description="生成的图片访问路径")
    model: str = Field(..., description="使用的图片模型")
    success: bool = Field(..., description="是否生成成功")


@router.post("/generate", response_model=GenerateImageResponse)
async def generate_image(req: GenerateImageRequest, current_user: User = Depends(get_current_user)) -> GenerateImageResponse:
    """
    生成单张图片（用于连通性测试）
    
    - 默认会自动优化提示词，生成小红书爆款风格图片
    - 图片比例固定为 3:4 竖版（适合手机浏览）
    """
    try:
        image_service = get_image_service()
        url = await image_service.generate_single_image(
            prompt=req.prompt,
            optimize_for_xhs=req.optimize_for_xhs,
        )

        # 获取模型名称
        model_name = getattr(image_service, "model", "unknown")

        return GenerateImageResponse(
            url=url, 
            model=model_name,
            success=url is not None
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"图片生成失败: {str(e)}",
        ) from e
