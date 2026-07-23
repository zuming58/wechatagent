# wechatagent

本地优先的个人微信关系记忆：归档电脑端已同步到本机的聊天数据，提供原文可追溯搜索、联系人关系工作台与后续的待办/摘要能力。

## 当前状态

- 已进入正式开发：亮蓝 UI Demo 已验收，正式前后端骨架已建立。
- 数据范围：仅用户本人电脑端微信已经同步到本机的数据。
- 隐私边界：本地 API 仅监听 `127.0.0.1`；真实聊天内容不上传、不写运行日志、不提交 Git。
- 真实采集：开发和自动化测试使用合成连接器；真实连接器仍保持 `connector_missing`。多账号显式选择安全闸门、合成适配器协议和前端安全交互均已覆盖，真实采集 Go/No-Go 尚未获执行授权，未读取或导入真实聊天记录。

## 项目结构

- `prototypes/ui-demo/`：已验收的视觉与交互基线（React + Vite）。
- `backend/`：FastAPI、SQLite、SQLAlchemy、Alembic、FTS5、标准采集适配器与自动化测试。
- `frontend/`：React + TypeScript 正式界面，已接入数据源状态、同步、联系人、聊天证据、原文搜索、消息上下文、用户确认事实和事实变更历史。
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

首次启动后，在前端点击“首次归档”即可导入合成数据；这不会访问微信。随后可在“聊天证据”查看联系人私聊与该联系人在已归档群聊中的发言，并从证据或关键词搜索结果打开消息上下文。关系总览中的“已确认事实”只由用户手动创建或确认；可选关联该联系人的原文证据，也可明确标记为“用户手动记录”。同步不会推断、覆盖或删除这些事实。“事实历史”仅记录用户在本地对事实的创建、编辑和删除快照，不代表聊天自动结论。

验证真实采集前，只能运行后端与前端的合成测试。不得安装或执行 `wx-cli`，也不得读取、解密、导入或上传真实微信聊天数据，直到用户明确授予 Go/No-Go 执行授权。

## 文档

- [PRD 总集](docs/PRD_REGISTRY.md)
- [PRD-001：本地微信沟通记忆库 MVP](docs/prd/PRD-001.md)
- [开发实施文档](docs/DEVELOPMENT_PLAN.md)
- [UI Demo 视觉方向定稿](docs/UI_DIRECTION.md)
- [Codex × Hermes 本地交接协议](docs/HERMES_HANDOFF.md)
- [技术可行性分析](docs/technical-feasibility.md)

## 重要边界

个人微信没有面向普通第三方的稳定全量历史 API。采集层必须保持为可替换、只读的适配器；产品不承诺手机端全量历史、零遗漏或永久兼容所有微信版本。
