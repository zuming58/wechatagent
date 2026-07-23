# wechatagent

本地优先的个人微信关系记忆：归档电脑端已同步到本机的聊天数据，提供原文可追溯搜索、联系人关系工作台与后续的待办/摘要能力。

## 当前状态

- 已进入正式开发：亮蓝 UI Demo 已验收，正式前后端骨架已建立。
- 数据范围：仅用户本人电脑端微信已经同步到本机的数据。
- 隐私边界：本地 API 仅监听 `127.0.0.1`；真实聊天内容不上传、不写运行日志、不提交 Git。
- 真实采集：本机发现微信 `4.1.11.24` 与多个账号目录，但 `wx-cli` 尚未安装，因此当前停在只读 Go/No-Go 的 `connector_missing` 状态，尚未读取或导入真实聊天记录。

## 项目结构

- `prototypes/ui-demo/`：已验收的视觉与交互基线（React + Vite）。
- `backend/`：FastAPI、SQLite、SQLAlchemy、Alembic、FTS5、标准采集适配器与自动化测试。
- `frontend/`：React + TypeScript 正式界面，已接入数据源状态、同步、联系人和原文搜索。
- `docs/`：PRD、开发计划、技术边界和 UI 规范。

## 本地开发验证

```powershell
# 后端：合成数据模式（默认）
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765

# 前端：另开一个终端
Set-Location frontend
npm install
npm run dev
```

首次启动后，在前端点击“首次归档”即可导入合成数据；这不会访问微信。

## 文档

- [PRD 总集](docs/PRD_REGISTRY.md)
- [PRD-001：本地微信沟通记忆库 MVP](docs/prd/PRD-001.md)
- [开发实施文档](docs/DEVELOPMENT_PLAN.md)
- [UI Demo 视觉方向定稿](docs/UI_DIRECTION.md)
- [技术可行性分析](docs/technical-feasibility.md)

## 重要边界

个人微信没有面向普通第三方的稳定全量历史 API。采集层必须保持为可替换、只读的适配器；产品不承诺手机端全量历史、零遗漏或永久兼容所有微信版本。
