import os
from app.services.llm_service import llm_service, LLMUsageInfo, TopicsResponse, StreamResult
from app.services.image_service import ImageService


def get_llm_service():
    if os.getenv('MOCK_MODE', 'false').lower() == 'true':
        from app.services.mock_service import MockLLMService
        return MockLLMService()
    return llm_service


def get_image_service():
    return ImageService()
