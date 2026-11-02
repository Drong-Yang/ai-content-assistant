"""Paired real-API evaluation; --real explicitly opts in to paid text requests.

Legacy writer prompt is frozen from commit 5838eda; no database/image calls.
Outputs include raw text, deterministic checks, usage, latency and blind-review sheets.
"""
import argparse
import asyncio
import hashlib
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.llm_service import LLMService, LLMUsageInfo
from app.graph.quality import rule_checks
from app.graph.nodes.writer import write_draft_node
from app.graph.nodes.quality_check import quality_check_node


async def legacy(service, case):
    from langchain_core.messages import SystemMessage, HumanMessage
    prompt = f"选题：{case['topic']}\n\n第1次修订，修改意见：{case['feedback']}\n\n请针对性修改。"
    messages = [SystemMessage(content=service.ARTICLE_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    content, usage = '', LLMUsageInfo(model=service.model)
    async for chunk in service.llm.bind(max_tokens=2600).astream(messages):
        content += chunk.content or ''
        service._update_usage_from_chunk(chunk, usage)
    usage.usage_source = 'api' if usage.total_tokens else 'estimated'
    if not usage.total_tokens:
        usage.input_tokens = sum(len(m.content) for m in messages) // 2
        usage.output_tokens = len(content) // 2
        usage.total_tokens = usage.input_tokens + usage.output_tokens
    if not content.strip():
        raise ValueError('Legacy model returned empty content')
    return content, usage


async def evaluate_case(case):
    service = LLMService(enable_pii_anonymize=False)
    outputs = {}
    # Alternate order to reduce systematic warm-up effects.
    for mode in (['legacy', 'upgraded'] if int(case['id'][-2:]) % 2 else ['upgraded', 'legacy']):
        started = time.perf_counter()
        try:
            if mode == 'legacy':
                content, usage = await asyncio.wait_for(legacy(service, case), timeout=120)
                metrics = [vars(usage)]
                extra = {}
            else:
                state = {'selected_topic':case['topic'], 'topic_direction':case['direction'],
                    'article_content':case['previous_article'], 'content_brief':case['brief'],
                    'review_status':'rejected', 'review_feedback':case['feedback'],
                    'quality_policy':{'enabled':True, 'max_auto_per_review':1,'max_auto_total':3,
                                      'token_budget':30000,'timeout_seconds':45}}
                state.update(await write_draft_node(state))
                state.update(await quality_check_node(state))
                if state.get('pending_revision_source') == 'auto':
                    state.update(await write_draft_node(state))
                    state.update(await quality_check_node(state))
                content, metrics = state['article_content'], state['node_metrics']
                extra = {'quality_history':state.get('quality_history', []),
                    'versions':state['article_versions'], 'auto_revisions':state.get('auto_revision_count',0)}
            outputs[mode] = {'content': content, 'checks':rule_checks(content,case['brief']),
                'duration_ms':round((time.perf_counter()-started)*1000,2),
                'total_tokens':sum(m.get('total_tokens',0) for m in metrics), 'calls':len(metrics),
                'usage':metrics, **extra}
        except Exception as exc:
            outputs[mode] = {'error_type':type(exc).__name__, 'duration_ms':round((time.perf_counter()-started)*1000,2)}
    # Reuse application clients inside a run; the service above is only the baseline client.
    await service.close()
    return {'id':case['id'], 'category':case['category'], 'input':case, 'outputs':outputs}


async def main(args):
    if not args.real:
        raise SystemExit('Pass --real to call the configured paid text model (no images).')
    os.environ['MOCK_MODE'] = 'false'
    cases = json.loads((ROOT / 'evals/revision_tasks.json').read_text(encoding='utf-8'))[:args.limit]
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    results = []
    semaphore = asyncio.Semaphore(2)
    async def run(case):
        async with semaphore:
            result = await evaluate_case(case)
            results.append(result)
            (out / (case['id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f"Finished {len(results)}/{len(cases)}: {case['id']}", flush=True)
    await asyncio.gather(*(run(c) for c in cases))
    from app.services.llm_service import llm_service
    await llm_service.close()
    results.sort(key=lambda r:r['id'])
    summary = {'date_utc':datetime.now(timezone.utc).isoformat(),'model':LLMService().model,
        'baseline_commit':'5838eda','prompt_version':'revision-v2-quality-v2', 'tasks':len(cases),
        'inference_control':'Same current model, temperature and thinking mode for both arms; legacy PROMPT ablation, not historical runtime replay.',
        'dataset_sha256':hashlib.sha256((ROOT/'evals/revision_tasks.json').read_bytes()).hexdigest(),
        'human_review_status':'pending', 'note':'Single generation per case; mechanical checks only; not a production estimate.'}
    for mode in ['legacy','upgraded']:
        records=[r['outputs'][mode] for r in results if 'error_type' not in r['outputs'][mode]]
        checks=[c for r in records for c in r['checks']]
        durations=sorted(r['duration_ms'] for r in records)
        summary[mode]={'succeeded':len(records),'failed':len(cases)-len(records),
            'all_rules_passed':sum(all(c['passed'] for c in r['checks']) for r in records),
            'rule_items_passed':sum(c['passed'] for c in checks),'rule_items_total':len(checks),
            'total_tokens':sum(r['total_tokens'] for r in records),
            'calls':sum(r['calls'] for r in records),
            'median_duration_ms':statistics.median(durations) if durations else None,
            'auto_revisions':sum(r.get('auto_revisions',0) for r in records)}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    rng=random.Random(20261102)
    blind, key=[],[]
    for r in results:
        modes=['legacy','upgraded']; rng.shuffle(modes)
        blind.append({'id':r['id'],'input':r['input'], 'A':r['outputs'][modes[0]].get('content','生成失败'),
            'B':r['outputs'][modes[1]].get('content','生成失败'), 'preference':'', 'reason':''})
        key.append({'id':r['id'],'A':modes[0],'B':modes[1]})
    (out/'blind_review.json').write_text(json.dumps(blind,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'blind_key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real',action='store_true')
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--output',default='evals/results-final-2026-11-02')
    args=parser.parse_args()
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
