# 内容质量闭环与文章版本（2026-11-02）

本次实现升级建议的第一阶段：定向改稿、版本对比、有限次质量检查、固定任务评测。配图按失败项补生成、MCP、多租户属于后续范围，当前图片重试仍是整批重新生成。

## 实际工作流

选题子图 → 写稿 → quality_check → 人工审核 → 配图要点 → 配图。

quality_check发现问题，且次数、输入长度与预算允许时，回到写稿节点自动修订；再次检查后进入人工审核。人工驳回会开始新的审核周期，但工作流累计自动修订上限不重置。人工批准始终是生成配图的必要条件。

这是自行搭建的Evaluator–optimizer工作流。LangGraph提供StateGraph、条件路由、检查点和interrupt等构件，不会因为安装框架就默认出现这段闭环。新任务默认开启，是本项目的应用配置。

## 新增输入与版本

页面支持目标读者、语气、最少/最多字符、必含栏目、必须逐字保留的文本。字符数按Python非空白字符统计，包含标点和Markdown符号。结构化篇幅要求优先于默认800—1200字符模板；自然语言中的不同篇幅要求应同步填写到表单。

`POST /api/v1/workflow/start`继续接受原来的`topic_direction`，新增可选字段：

```json
{
  "topic_direction": "介绍如何用AI整理周报",
  "content_brief": {
    "audience": "刚毕业的职场新人",
    "tone": "务实友好，避免夸张承诺",
    "min_chars": 200,
    "max_chars": 400,
    "required_sections": ["三步清单"],
    "preserve_phrases": ["案例甲：先归类，再核对。"]
  },
  "quality_enabled": true
}
```

写稿服务收到原始方向、内容要求、上一版全文和本轮意见；空反馈驳回也算一次人工修订。修改输入合计上限16000字符，反馈上限2000字符，超过限制明确报错，不静默截断原稿。

`article_versions`保存版本ID、父版本、正文、反馈、触发来源、时间和关联指标。`revision_count`只统计人工修订，`auto_revision_count`单独统计自动修订。前端用本地行级LCS计算差异，不调用模型；超大行数比较退化为整篇新增/删除，以限制浏览器计算量。正文以纯文本展示。

状态接口、普通resume返回的`values`和SSE最终`done.values`均包含这些记录。旧版文章首次修改时补存一个`legacy`父版本。

## 检查规则与失败处理

- 长度、必含栏目和保留文本：代码判断。
- 受众匹配、用户需求/反馈落实、操作建议：模型输出经过Pydantic验证的检查项。模型引用`article_segments`编号，程序校验编号并回填实际正文。对未采用编号的结果仍验证引用文本，允许仅换行/空格差异并标记。
- 模型检查是建议，不能替代事实核验、平台合规检查或预测流量；评分也不是独立质量证明。
- JSON/Schema无效、证据不存在、服务异常、超时：显示`check_failed`，保留文章并转人工审核，不伪装成通过。
- 达到修订次数或预算限制：显示具体原因，交人工处理。
- 写稿失败保留已完成检查点，沿用现有失败可见与retry恢复机制。失败调用的供应商账单可能不可知，不能据界面统计承诺准确费用。

SSE只把`langgraph_node=write_draft`的模型片段发为正文Token，携带文章版本ID。每次开始新版本先清空流式正文，防止首稿和自动修订拼接。检查节点通过独立节点事件与最终状态更新检查面板，不把JSON混入正文。

## 限制与配置

新任务创建时将配置快照保存进`quality_policy`。修改环境配置并重启影响新任务，不追溯修改已有工作流策略。

- `QUALITY_ENABLED=true`：应用允许新任务开启检查；请求字段只能关闭，不能绕过服务端关闭。
- `QUALITY_MAX_AUTO_PER_REVIEW=1`：每轮人工审核前最多自动修订一次，可配置0—2。
- `QUALITY_MAX_AUTO_TOTAL=3`：整个工作流累计自动修订最多三次，可配置0—5。
- `QUALITY_TOKEN_BUDGET=30000`：质量检查和自动修订的准入预算，不包含首稿、人工要求的改稿、选题或配图。按保守字符估算输入需求，限制单次输出额度，已获得用量优先使用API数据。它不是供应商账单的硬上限；检查失败时会预留未知消耗，避免无限继续。
- `QUALITY_TIMEOUT_SECONDS=45`：单次检查超时；检查客户端关闭SDK自动重试。单次写稿外层超时120秒，沿用文本客户端的SDK重试设置。
- Ark服务默认`LLM_THINKING_MODE=disabled`，用于内容写作和检查，避免思考内容占尽输出额度导致空稿。非Ark地址默认`provider_default`；切换供应商时按支持情况设置。

旧检查点没有quality_policy时保持人工审核，不自动开启检查；原有human_review、write_draft等节点名称保留。已有暂停会话无须迁移或重写数据库。禁用检查后仍保留改稿上下文、文章版本功能。

关闭应用时清理新增检查客户端及其他文本客户端。检查点使用原有PostgreSQL表，无业务数据库迁移。

## 验证与复现

在代码根目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest test_quality_upgrade test_reproduction -v
Push-Location frontend
npm.cmd run build
node --test src/version-diff.test.js
Pop-Location
```

后端覆盖：原文/方向/反馈确实传入、首轮失败后修订通过、反复失败的轮次与累计上限、检查异常/超时、预算耗尽不调用模型、旧图检查点在新拓扑恢复、检查证据ID校验、SSE不泄入检查JSON、版本在真实PostgreSQL与应用新生命周期间一致，以及原有用户隔离、失败恢复、配图部分失败流程。

真实评测会调用付费文本API，不生成图片：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_revision.py --real --limit 20
```

固定输入为`evals/revision_tasks.json`，正式结果目录`evals/results-final-2026-11-02`。基线是5838eda版本的旧写稿提示，双方使用相同当前模型、温度和思考模式，这是旧提示与新流程的受控对比，不是历史运行环境重演。

每题保留两版原始正文、机械规则、用量来源、延迟、版本和检查记录。`summary.json`汇总硬规则结果；`blind_review.json`是待人工填写的A/B偏好表，`blind_key.json`存映射。不要提前看映射后再声称盲评。尚未填写的人工偏好不能写成已有结论。试跑/调试结果不计入正式报告。

单次20题不能证明生产规模收益，也不衡量全部事实准确性。普通内容质量需要人工复核；升级带来的额外调用与延迟必须与约束改善一起报告。

## 面试表述

建议简历写：

> 基于LangGraph构建内容生产工作流，引入结构化质量检查与有限次自动修订，支持保留原文的反馈改稿、文章版本对比及PostgreSQL检查点恢复。

实测指标另按正式报告与任务口径填写。面试再补充“使用Evaluator–optimizer模式”，讲清评估标准、条件路由、停止条件、检查失败处理和成本取舍。无需在项目简介写“对应LangGraph官方某模式”，名称不能替代实际实现和证据。

参考：[LangGraph工作流模式](https://docs.langchain.com/oss/python/langgraph/workflows-agents#evaluator-optimizer)、[方舟Seed 1.8模型说明](https://docs.volcengine.com/docs/ark/bytedance-seed-1-8?lang=zh)、[方舟深度思考参数](https://docs.volcengine.com/docs/ark/deep-thinking?lang=zh)。
