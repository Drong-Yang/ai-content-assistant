# 社媒内容生产 Agent 工作流


**选题 / 撰写 / 配图的人机协同**

基于 Vue 3 + FastAPI + LangGraph 1.0 + PostgreSQL 的选题 / 撰写 / 审稿 / 配图 Agent 工作流，支持 AI 出选题、人在环审稿、中断续跑；基于状态图编排把「AI 出方案、人拍板」固化为可中断、可恢复、可回看的有状态流程。

## 功能与边界

- 注册、登录与按用户隔离的工作流历史。
- 7 节点工作流、选题与审稿 2 处人在环，PostgreSQL 保存检查点；刷新页面或重启应用后恢复任务。
- 流式写稿、审核反馈重写、失败节点重试、图片部分失败状态保留。
- 支持火山方舟文本与图片 API，也提供明确标识的模拟文本和 SVG 配图。
- 当前用于本地演示，不会自动发布到小红书或其他平台；生产部署需要额外配置 HTTPS、访问控制和服务运维。

## 环境

Python **3.13**（与 pyproject.toml / uv.lock 一致）、Node.js 22、npm、Docker Compose。无需本地 GPU。模拟模式也需要 PostgreSQL。

## 独立运行

下载或克隆本仓库后，在仓库根目录执行。无需外部工作区脚本。

### 1. 配置与数据库

`.env`、日志、生成图片和数据库包含本机配置或用户数据，请勿提交到仓库。

复制 `.env.example` 为 `.env`（PowerShell：`Copy-Item .env.example .env`；macOS/Linux：`cp .env.example .env`）。

- 将 `POSTGRES_PASSWORD` 改为自己的随机密码（建议使用字母数字，避免连接串转义问题）。
- 将 `DATABASE_URL`、`POSTGRES_URI` 中的 `CHANGE_ME` 替换为同一密码。
- 将 `JWT_SECRET_KEY` 改为长随机字符串。
- 首次体验设置 `MOCK_MODE=true`，无需模型密钥。

```bash
docker compose up -d --wait
```

数据库只绑定本机 `5432`。若端口已被占用，请先停止已有数据库，或同时修改 compose.yaml 的映射端口与两个数据库连接串。持久卷已有数据时，修改 `.env` 不会修改卷内密码。

### 2. 后端

```bash
python -m venv .venv
```

PowerShell 激活：`.\.venv\Scripts\Activate.ps1`；macOS/Linux 激活：`source .venv/bin/activate`。

```bash
python -m pip install -r requirements.txt
python run_server.py
```

已安装 uv 时也可用 `uv sync --frozen` 安装锁定版本，再 `uv run python run_server.py`。Windows 请使用 `run_server.py`，其中选择兼容 psycopg 的事件循环。

API 文档：<http://127.0.0.1:8000/docs>；健康检查：<http://127.0.0.1:8000/health>。

### 3. 前端

另开终端：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>，注册账号并登录。前端开发服务代理 `/api` 与 `/static` 到本机 8000 端口。

### 4. 真实模型

将 `MOCK_MODE=false`，填写自己的 `LLM_API_KEY`、`LLM_MODEL`；配图需要 `IMAGE_MODEL` 与 `IMAGE_API_KEY`（为空时复用文本密钥）。模型填实际开通的模型 ID 或接入点，API 地址以自己的服务区域为准。重启后端后生效，真实调用会产生云服务费用。

### 停止

前后端终端分别按 Ctrl+C，执行 `docker compose stop` 停止数据库并保留数据。不要用 `docker compose down -v` 排错，否则会删除持久卷。

## 测试

使用专用测试数据库及专用 `.env` 执行，测试会创建用户和工作流记录，勿连接生产数据库。测试使用模拟模型，不调用真实云服务。

```bash
python -m unittest test_reproduction -v
cd frontend
npm run build
```

GitHub Actions 为集成测试启动独立 PostgreSQL 服务，并验证前端构建；[验证记录](docs/VALIDATION.md)记录本地检查的范围。模拟测试通过不代表真实文本、图片 API 本次已验收。

## 目录

```text
app/                 FastAPI、认证、LangGraph 节点及服务
frontend/            Vue 页面与 Vite 开发代理
scripts/             数据库辅助脚本
run_server.py        跨平台后端入口
compose.yaml         本地 PostgreSQL
.env.example         配置模板（无真实密钥）
test_reproduction.py 工作流、隔离与图片接口回归
uv.lock              Python 依赖锁
```

本项目基于 `graph_xiaohongshu` 教学项目改造，实现内容生产流程的人机协同与持久化恢复，保留原代码中的说明。
