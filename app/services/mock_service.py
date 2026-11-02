"""Deterministic local demonstration services, explicitly marked as mock."""
from app.services.llm_service import TopicsResponse, TopicItem, LLMUsageInfo, StreamResult, LLMService
from app.graph.quality import SemanticReview, QualityItem


class MockLLMService:
    ARTICLE_SYSTEM_PROMPT = LLMService.ARTICLE_SYSTEM_PROMPT
    _build_article_prompt = LLMService._build_article_prompt
    build_quality_messages = LLMService.build_quality_messages
    async def plan_topics(self, direction):
        return TopicsResponse(topics=[TopicItem(title=f'[模拟] {direction}实践{i}') for i in range(1,6)]), LLMUsageInfo(model='mock')

    async def stream_write_draft_with_usage(self, topic, feedback='', revision_count=0, on_chunk=None,
            topic_direction='', previous_article='', content_brief=None, **kwargs):
        brief = content_brief or {}
        content = previous_article or f'# [模拟文章，非真实模型] {topic}\n\n演示 Python API、FastAPI 和 RAG 的实践流程。'
        content += f'\n修改意见：{feedback}\n修订次数：{revision_count}\n'
        content += '\n'.join(brief.get('required_sections', []) + brief.get('preserve_phrases', []))
        content += '具体示例：先整理记录，再分类核对，最后人工确认。' * max(0, (brief.get('min_chars', 800) - len(content)) // 24 + 1)
        return StreamResult(content=content, usage=LLMUsageInfo(model='mock'))

    async def evaluate_article(self, article, direction, topic, brief, feedback, **kwargs):
        return SemanticReview(checks=[QualityItem(criterion=c, passed=True, evidence=article[:12])
            for c in ['受众匹配', '需求与修改意见落实', '建议可操作性']]), LLMUsageInfo(model='mock')

    async def extract_visual_points(self, article_content):
        return ['[模拟] API 请求流程', '[模拟] FastAPI 服务', '[模拟] RAG 检索步骤'], LLMUsageInfo(model='mock')
