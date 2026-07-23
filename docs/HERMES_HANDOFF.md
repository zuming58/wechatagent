# Codex × Hermes 本地交接协议

## 1. 分工与边界

| 角色 | 负责事项 | 不负责事项 |
| --- | --- | --- |
| Codex（本对话） | 架构约束、任务拆分、代码/测试/安全审计、UI 视觉验收、最终合并建议 | 不直接替用户向 Hermes 发消息，不绕过用户修改真实微信数据 |
| Hermes | 按交接任务实现代码、运行规定验证、提交清晰的回传说明 | 不自行扩大范围、不读取或上传真实聊天内容、不跳过测试 |
| 用户 | 将“发给 Hermes”区块复制给 Hermes；将 Hermes 回传内容复制回本对话 | 不需要手工整理技术细节 |

协作媒介是本仓库与本文件。每次实现任务必须有唯一编号（例如 `DEV-001`）；一次只处理一个进行中的任务，避免并发修改同一文件。

## 2. 不可突破的安全边界

1. 真实微信数据只能在用户本机、只读、明确 Go/No-Go 后处理；不得上传、写入日志、提交 Git 或发往外部网络。
2. 不安装、不执行、也不以管理员身份运行任何采集器，除非任务明确写明且用户已再次确认。
3. 所有 API 仅监听 `127.0.0.1`；联系人身份只能使用“账号标识 + 稳定内部标识”，不得以昵称、实名或头像作主键。
4. `prototypes/ui-demo/reference/relationship-workbench-final-bright-blue.png` 是唯一 UI 视觉基准。不得恢复深蓝左栏、灰蓝雾感或旧绿色主题。
5. 不得使用 `git reset --hard`、覆盖无关改动，或提交 `data/`、`.venv/`、`node_modules/`、真实聊天导出和密钥。

## 3. 当前基线（交接前）

- 分支：`agent/ui-demo`
- 基线提交：`ff7ed85 feat: start local relationship memory application`
- UI Demo：`prototypes/ui-demo/`，亮蓝版已通过 `design-qa.md` 验收。
- 后端：`backend/`，FastAPI + SQLite + SQLAlchemy + Alembic + FTS5(trigram)。
- 正式前端：`frontend/`，React + TypeScript，已接通合成数据的状态、首次归档、联系人和原文搜索。
- 已通过：`backend/.venv/Scripts/python.exe -m pytest -q`（3 项）；`npm run build`（`frontend/`）；`npm run build && npm run test:sites`（`prototypes/ui-demo/`）。
- 实机只读探测结果：微信 `4.1.11.24`、发现两个账号目录、`wx-cli` 未安装；当前必须显示 `connector_missing`，未读取任何真实聊天内容。

## 4. 标准工作流

1. Codex 在本文件新增“发给 Hermes”任务区块。
2. 用户将该区块原样复制给 Hermes。
3. Hermes 实现后，回传“回传给 Codex”模板中的完整内容。
4. 用户将 Hermes 回传原样复制回本对话。
5. Codex 审计 diff、边界、测试、UI（如涉及），给出：通过 / 需修改 / 拒绝合并。
6. 只有 Codex 审计通过后，任务才标记完成并发下一张任务。

## 5. Hermes 回传模板

```text
任务编号：DEV-xxx
完成状态：完成 / 部分完成 / 阻塞

改动文件：
- <文件路径>：<一句话说明>

实现说明：
- <关键设计与取舍>

验证命令与结果：
- <命令> -> <通过/失败及摘要>

未完成项或风险：
- <没有则写“无”>

真实数据声明：
- 未读取、未导入、未上传真实微信聊天数据 / 如有例外必须逐项说明

提交：
- <commit hash；若未提交，说明原因>
```

## 6. 当前发给 Hermes 的任务：DEV-001

> 以下区块是给用户复制给 Hermes 的原文。

```text
你在 F:\WorkBuddy\wechatagent 项目中实现 DEV-001。请先阅读 docs\HERMES_HANDOFF.md，并严格遵守其中的安全与视觉边界。

任务目标：补齐“本地同步业务闭环”的数据一致性与自动化测试；本任务只使用合成数据，禁止安装、执行或接入 wx-cli，禁止读取任何真实微信聊天内容。

实施范围：
1. 后端同步完成后，正确维护 contacts.last_message_at：
   - 私聊消息应更新对应稳定 source_id 联系人的最后消息时间。
   - 群聊消息只在发送人可映射为已有联系人时更新该联系人时间。
   - 不得创建仅因消息发送人出现而产生的“猜测联系人”。
2. 增强同步测试：
   - 首次归档后联系人按 last_message_at 倒序返回。
   - 重复执行 initial 三次不增加消息量。
   - incremental 从水位前 5 分钟重叠回读时仍幂等；水位只在原始消息提交成功后推进。
   - 连接器非 ready 时，/api/v1/sync 返回清晰的失败状态，且不调用 collect。
3. 确保 SQLite FTS5(trigram) 的中文关键词搜索、消息上下文、账号隔离的既有测试继续通过。
4. 如需修改 API schema 或 README，只能为上述闭环补充，不做 AI、语义搜索、Obsidian、真实采集、桌面封装或 UI 重设计。

验收命令：
- 在 backend 目录运行 .\.venv\Scripts\python.exe -m pytest -q
- 在 frontend 目录运行 npm run build

提交要求：
- 只提交本任务相关文件；使用清晰英文 commit message。
- 不提交 data/、.venv/、node_modules/、日志、数据库、真实数据或密钥。
- 完成后按 docs\HERMES_HANDOFF.md 的“回传给 Codex”模板完整回传。
```

## 7. Codex 审计清单

- [ ] 任务范围与 diff 一致，无无关重构。
- [ ] 无真实数据、密钥、数据库、日志或构建产物进入 Git。
- [ ] 不破坏本地优先、仅 `127.0.0.1`、账号隔离、只读边界。
- [ ] 数据去重、水位推进、失败恢复与测试断言正确。
- [ ] 相关构建与测试均通过；如涉及 UI，再做同视口视觉与交互检查。
- [ ] 失败、权限不足、未知分片和不兼容状态对用户清晰可见，不伪装为已同步。
