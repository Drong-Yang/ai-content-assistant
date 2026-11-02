"""Behaviour tests for bounded revision, original-context delivery and old checkpoints."""
import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START
from langgraph.types import Command, interrupt
from langchain_core.messages import AIMessageChunk, AIMessage
from app.graph.state import AgentState
from app.graph.workflow import build_workflow_graph
from app.graph.nodes.writer import write_draft_node
from app.graph.nodes.quality_check import quality_check_node
from app.graph.quality import ContentBrief, SemanticReview, QualityItem
from app.services.mock_service import MockLLMService
from app.services.llm_service import LLMService, LLMUsageInfo
from app.api.v1.workflow import stream_graph_updates


def initial(**overrides):
    return {"topic_direction": "为职场新人介绍周报整理", "content_brief": ContentBrief().model_dump(),
        "quality_policy": {"enabled": True, "max_auto_per_review": 1, "max_auto_total": 2,
            "token_budget": 30000, "timeout_seconds": 1}, **overrides}


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def run_to_review(self, service):
        graph = build_workflow_graph().compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "test"}}
        await graph.ainvoke(initial(), config)
        state = await graph.aget_state(config, subgraphs=True)
        topic = state.tasks[0].state.values['generated_topics'][0]
        await graph.ainvoke(Command(resume={"selected_topic": topic}), config)
        return graph, config

    async def test_fail_once_then_pass_and_human_revision_versions(self):
        service = MockLLMService()
        passed = await service.evaluate_article('正文', '', '', {}, '')
        failed = (SemanticReview(checks=[QualityItem(criterion=c, passed=False, issue='需要具体例子',
            suggestion='加入具体例子') for c in ['受众', '需求', '可操作性']]), LLMUsageInfo(model='mock'))
        service.evaluate_article = AsyncMock(side_effect=[failed, passed, passed])
        with patch('app.graph.nodes.planner.get_llm_service', return_value=service), \
             patch('app.graph.nodes.writer.get_llm_service', return_value=service), \
             patch('app.graph.nodes.quality_check.get_llm_service', return_value=service), \
             patch('app.graph.nodes.visualizer.get_image_service') as images:
            graph, config = await self.run_to_review(service)
            s = (await graph.aget_state(config)).values
            self.assertEqual(s['auto_revision_count'], 1)
            self.assertEqual(s['revision_count'], 0)
            self.assertEqual(s['quality_report']['status'], 'passed')
            self.assertEqual([v['source'] for v in s['article_versions']], ['initial', 'auto'])
            images.assert_not_called()
            # Empty human feedback is still a new human revision, not a fresh first draft.
            await graph.ainvoke(Command(resume={'action': 'reject', 'feedback': ''}), config)
            s = (await graph.aget_state(config)).values
            self.assertEqual(s['revision_count'], 1)
            self.assertEqual(s['article_versions'][-1]['source'], 'human')
            self.assertEqual(s['article_versions'][-1]['parent_version_id'], s['article_versions'][-2]['version_id'])

    async def test_repeated_failure_stops_at_cycle_and_total_limits(self):
        service = MockLLMService()
        bad = SemanticReview(checks=[QualityItem(criterion=c, passed=False, suggestion='补示例') for c in ['受众', '需求', '操作']])
        service.evaluate_article = AsyncMock(return_value=(bad, LLMUsageInfo(model='mock')))
        with patch('app.graph.nodes.planner.get_llm_service', return_value=service), \
             patch('app.graph.nodes.writer.get_llm_service', return_value=service), \
             patch('app.graph.nodes.quality_check.get_llm_service', return_value=service):
            graph, config = await self.run_to_review(service)
            for _ in range(3):
                await graph.ainvoke(Command(resume={'action': 'reject', 'feedback': '保留例子'}), config)
            s = (await graph.aget_state(config)).values
            self.assertEqual(s['auto_revision_count'], 2)
            self.assertEqual(s['revision_count'], 3)
            self.assertEqual(s['quality_report']['route'], 'manual')
            self.assertIn('累计', s['quality_report']['reason'])
            self.assertEqual((await graph.aget_state(config)).next, ('human_review',))

    async def test_checker_exception_and_timeout_keep_draft(self):
        for mode in ['exception', 'timeout']:
            service = MockLLMService()
            async def fail(*a, **k):
                if mode == 'timeout':
                    await asyncio.sleep(.05)
                raise RuntimeError('failure')
            service.evaluate_article = fail
            state = initial(selected_topic='周报', article_content='原稿例子',
                quality_policy={'enabled': True, 'timeout_seconds': .001})
            with patch('app.graph.nodes.quality_check.get_llm_service', return_value=service):
                result = await quality_check_node(state)
            self.assertEqual(result['quality_report']['status'], 'check_failed')
            self.assertEqual(result['pending_revision_source'], '')
            self.assertNotIn('article_content', result)

    async def test_budget_exhaustion_skips_model(self):
        service = MockLLMService()
        service.evaluate_article = AsyncMock()
        with patch('app.graph.nodes.quality_check.get_llm_service', return_value=service):
            out = await quality_check_node(initial(selected_topic='周报', article_content='原稿',
                quality_tokens_used=30000))
        service.evaluate_article.assert_not_called()
        self.assertEqual(out['quality_report']['status'], 'budget_exhausted')

    async def test_old_paused_graph_resumes_with_new_topology(self):
        saver = InMemorySaver()
        async def old_writer(state):
            return {'article_content': '历史原稿：保留案例甲', 'selected_topic': '周报', 'review_status': 'pending'}
        async def old_review(state):
            interrupt({'action_required': 'review'})
        old = StateGraph(AgentState)
        old.add_node('write_draft', old_writer)
        old.add_node('human_review', old_review)
        old.add_edge(START, 'write_draft')
        old.add_edge('write_draft', 'human_review')
        cfg = {'configurable': {'thread_id': 'legacy'}}
        await old.compile(checkpointer=saver).ainvoke({}, cfg)
        graph = build_workflow_graph().compile(checkpointer=saver)
        with patch('app.graph.nodes.writer.get_llm_service', return_value=MockLLMService()):
            await graph.ainvoke(Command(resume={'action': 'reject', 'feedback': '保留案例甲'}), cfg)
        s = (await graph.aget_state(cfg)).values
        self.assertEqual(s['quality_report']['status'], 'disabled')
        self.assertEqual(s['article_versions'][0]['source'], 'legacy')
        self.assertIn('保留案例甲', s['article_content'])


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_writer_sends_original_brief_previous_text_and_feedback(self):
        service = LLMService(enable_pii_anonymize=False)
        captured = []
        class Client:
            def bind(self, **kwargs): return self
            async def astream(self, messages, **kwargs):
                captured.extend(messages)
                yield AIMessageChunk(content='修改后的文章', usage_metadata={'input_tokens': 10, 'output_tokens': 8, 'total_tokens': 18})
        service._llm = Client()
        with patch('app.graph.nodes.writer.get_llm_service', return_value=service):
            out = await write_draft_node(initial(selected_topic='周报', article_content='案例甲：整理十条工作记录',
                review_status='rejected', review_feedback='保留案例甲，只改成三步清单'))
        prompt = captured[-1].content
        for phrase in ['职场新人', '案例甲：整理十条工作记录', '只改成三步清单']:
            self.assertIn(phrase, prompt)
        self.assertEqual(out['article_versions'][-1]['metric']['usage_source'], 'api')

    async def test_checker_rejects_invalid_json_and_invented_evidence(self):
        service = LLMService(enable_pii_anonymize=False)
        class Client:
            def model_copy(self, **k): return self
            def bind(self, **k): return self
            async def ainvoke(self, *a, **k): return AIMessage(content=output)
        service._llm_quality = Client()
        for output in ['not-json', json.dumps({'checks': [{'criterion': c, 'passed': True, 'evidence': '不在正文'} for c in ['a', 'b', 'c']]})]:
            with self.assertRaises(ValueError):
                await service.evaluate_article('正文', '', '', {}, '')

    async def test_sse_does_not_emit_checker_json_as_article(self):
        class Graph:
            async def astream_events(self, *a, **k):
                for node, text in [('quality_check', 'SECRET_JSON'), ('write_draft', '正文')]:
                    yield {'event': 'on_chat_model_stream', 'metadata': {'langgraph_node': node,
                        'article_version_id': 'v1'}, 'data': {'chunk': AIMessageChunk(content=text)}}
            async def aget_state(self, *a, **k):
                return SimpleNamespace(values={'status': 'draft_generated'}, tasks=[], next=('human_review',))
        output = ''.join([x async for x in stream_graph_updates(Graph(), None, {})])
        self.assertNotIn('SECRET_JSON', output)
        self.assertIn('正文', output)
        self.assertIn('v1', output)

    async def test_checker_evidence_ids_resolve_to_actual_body(self):
        service = LLMService(enable_pii_anonymize=False)
        class Client:
            def bind(self, **k): return self
            async def ainvoke(self, *a, **k): return AIMessage(content=json.dumps({'checks':[
                {'criterion': c, 'passed': True, 'evidence_id': ref} for c in ['受众','需求','操作']]}))
        service._llm_quality = Client()
        ref = 1
        review, _ = await service.evaluate_article('案例甲。\n具体步骤。', '', '', {}, '')
        self.assertEqual(review.checks[0].evidence, '案例甲。')
        ref = 99
        with self.assertRaises(ValueError):
            await service.evaluate_article('案例甲。', '', '', {}, '')

    async def test_length_validation_and_prompt_limit(self):
        with self.assertRaises(ValueError): ContentBrief(min_chars=1000, max_chars=100)
        with self.assertRaises(ValueError):
            LLMService()._build_article_prompt('标题', '', 1, previous_article='字' * 17000)


if __name__ == '__main__': unittest.main()
