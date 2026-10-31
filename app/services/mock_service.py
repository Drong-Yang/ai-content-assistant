"""Deterministic local demonstration services, explicitly marked as mock."""
from app.services.llm_service import TopicsResponse, TopicItem, LLMUsageInfo, StreamResult


class MockLLMService:
    async def plan_topics(self, direction):
        return TopicsResponse(topics=[TopicItem(title=f'[模拟] {direction}实践{i}') for i in range(1,6)]), LLMUsageInfo(model='mock')

    async def stream_write_draft_with_usage(self, topic, feedback='', revision_count=0, on_chunk=None):
        content=f'# [模拟文章，非真实模型] {topic}\n\n演示 Python API、FastAPI 和 RAG 的实践流程。\n修改意见：{feedback}\n修订次数：{revision_count}'
        return StreamResult(content=content, usage=LLMUsageInfo(model='mock'))

    async def extract_visual_points(self, article_content):
        return ['[模拟] API 请求流程', '[模拟] FastAPI 服务', '[模拟] RAG 检索步骤'], LLMUsageInfo(model='mock')
