# 跨机器续开发交接

更新时间：2026-07-28

## 快照

- 仓库：`https://github.com/zuming58/wechatagent.git`
- 当前分支：`agent/ui-demo`
- 此交接文件与当前 Windows 4.1 预检加固改动应一并提交、推送后再在新机器拉取。
- 本次未读取、导入、解密、导出或上传任何真实微信聊天数据、数据库或密钥。

## 本次交付

Windows 4.1 只读预检链路已做一次修复与回归验证：

1. 预检只有在目标进程、版本、DLL、PE 定位与函数边界校验全部通过时才返回成功；不再只因 EXE 头可读而误报成功。
2. 版本由目标 PID 对应的可执行文件读取，不再从任意第一个微信进程取得。
3. 预检对同一次读取的 `Weixin.dll` 同时计算 SHA-256 和分析 PE；生成计划时会再次校验哈希，拒绝 DLL 在预检后发生替换或传入不同 DLL 的情况。
4. PE 分析不再用裸字节猜测函数序言，改用 x64 PE 异常目录（`.pdata`）中的运行时函数边界；定位不完整或歧义时失败关闭。
5. 新增预检、二进制绑定、PE 异常目录和目标可执行文件版本测试。

这些代码仍只进行只读预检和合成测试，不附加进程、不设断点、不读取数据库，也不会提取任何真实口令。

## 已验证

在 `backend/` 下执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app tests
```

结果：`71 passed`；仅有既存的 FastAPI/TestClient 与 Alembic 弃用警告。

## 新机器恢复

```powershell
git clone https://github.com/zuming58/wechatagent.git
Set-Location wechatagent
git switch agent/ui-demo

Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18765
```

在另一终端启动前端：

```powershell
Set-Location wechatagent\frontend
npm install
npm run dev
```

- 前端：`http://127.0.0.1:5181`
- 后端：`http://127.0.0.1:18765`
- 默认只使用合成连接器。不要安装或执行 `wx-cli`，也不要把真实微信数据放进仓库。

## 资料索引

| 文件 | 用途 |
| --- | --- |
| `README.md` | 项目概览、启动和本地数据边界 |
| `docs/HERMES_HANDOFF.md` | 开发协作协议、历史任务状态和审计清单 |
| `docs/DEVELOPMENT_PLAN.md` | 实施阶段与范围约束 |
| `docs/prd/PRD-001.md` | 产品需求 |
| `docs/technical-feasibility.md` | 技术取舍与风险 |
| `docs/UI_DIRECTION.md` | 正式界面视觉基准 |
| `prototypes/ui-demo/` | 已验收的 UI 原型 |
| `backend/README.md` | 后端专用开发说明 |

## 后续边界

- 当前真实连接器仍是 `connector_missing`；不要把本交接视为真实采集或管理员权限的授权。
- 若继续 Windows 预检，先运行合成测试并审计 diff；任何真实数据处理都必须有单独、明确且可撤销的用户授权。
- 推送前检查 `git status --short`，不得提交 `data/`、`.env`、`.venv/`、`node_modules/`、数据库、真实聊天导出、密钥、日志或构建产物。
