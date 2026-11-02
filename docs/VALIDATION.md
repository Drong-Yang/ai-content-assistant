# 2026-11-02 发布验证记录

本次在独立 PostgreSQL 测试数据库 `project2_publish_test_20261102` 上运行回归，未写入演示数据库。模型和图片服务使用模拟或 HTTP mock，不产生真实云端生成调用。

- 后端：`python -m unittest test_quality_upgrade test_reproduction -v`，13/13 通过。
- 覆盖质量检查证据校验、原始需求与全文传递、修订次数和预算限制、检查异常与超时、旧检查点兼容、SSE 正文隔离、用户隔离、应用生命周期重启恢复、失败节点与配图重试。
- 前端：`node --test src/version-diff.test.js`，1/1 通过。
- 前端：`npm run build`，Vite 生产构建通过。
- README：采用“自媒体图文创作与审稿 Agent”名称，加入飞书与 Bilibili 演示链接和 5 张界面截图。

本次发布未重新运行真实文本或图片生成，也未读取或上传本地 mp4。此前真实文本 API 的固定 20 题评测见[正式评测报告](EVALUATION_2026-11-02.md)，不与本次模拟回归混为同一次验收。

---

# 2026-10-31 验证记录

前端 Vite 生产构建通过。图片服务回归测试 ImageTests 1/1 通过（模拟 HTTP 返回，不调用真实服务）。
Docker Linux 引擎未启动，本次未执行需要 PostgreSQL 的完整 WorkflowTests。GitHub Actions 已配置独立 PostgreSQL 运行完整 test_reproduction。
本次未调用真实文本与配图云服务。
