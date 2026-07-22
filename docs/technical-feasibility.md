# 微信聊天记录智能管理工具 — 技术可行性分析文档

> [!WARNING]
> 本文档为早期调研快照，所依赖的 `sjzar/chatlog` 已于 2025-10-20 因微信官方函件移除全部代码与历史，不能作为当前开发依赖。现行方案以 [PRD-001](prd/PRD-001.md) 与 [开发实施文档](DEVELOPMENT_PLAN.md) 为准；采集层必须采用可替换适配器，并先完成本机 PoC 验证。

> 项目代号：wechatagent  
> 编写日期：2026-07-22  
> 编写人：小宇（AI数字分身）  
> 文档版本：v1.0

---

## 一、项目概述

### 1.1 项目目标

开发一个本地部署的微信聊天记录智能管理工具，实现以下核心功能：

1. **自动备份**：自动读取PC端微信本地数据库，全量备份聊天记录
2. **智能搜索**：基于向量数据库的语义搜索，支持自然语言查询
3. **知识库沉淀**：将聊天记录结构化为Obsidian知识库，支持双向链接
4. **客户画像**：AI分析聊天内容，自动生成联系人画像，识别潜在客户
5. **每日摘要**：AI自动归纳群消息，筛选值得关注的内容

### 1.2 核心原则

- **本地部署**：所有数据在本地处理，不上传云端，保护隐私
- **自动获取**：不依赖手动导入，自动从PC端微信数据库读取
- **增量同步**：首次全量迁移，后续增量更新

### 1.3 使用场景

- 老王每天用PC端微信办公，群多、资料多、客户多
- 需要快速查找历史聊天中的某条信息、某个文件、某次对话
- 需要记住每个客户是谁、什么时候加的、聊过什么、是否有合作意向
- 需要每天从大量群消息中筛选出有价值的信息

---

## 二、数据获取方案

### 2.1 微信PC端数据存储机制

微信PC客户端将聊天记录存储在本地SQLite数据库中，使用SQLCipher 4进行加密。

**数据库位置（Windows）：**

```
微信4.x版本：
%USERPROFILE%\Documents\WeChat Files\{wxid}\msg\
  ├── db_storage\
  │   ├── message_0.db    # 聊天消息
  │   ├── message_1.db    # 聊天消息（分库）
  │   ├── contact.db      # 联系人
  │   ├── microMsg.db     # 微信核心数据
  │   ├── media.db        # 媒体文件索引
  │   └── ...
  └── attachment\         # 附件（图片、视频、文件）

微信3.x版本：
%USERPROFILE%\Documents\WeChat Files\{wxid}\Msg\
  ├── Misc.db
  ├── MSG0.db
  ├── MSG1.db
  ├── MicroMsg.db
  └── MediaMSG1.db
```

**加密方式：**
- 算法：AES-256-CBC（SQLCipher 4）
- 密钥：64位十六进制字符串，存储在微信进程内存中
- 密钥获取：通过读取微信进程内存偏移量提取

### 2.2 数据获取流程

```
┌──────────────────────────────────────────────────┐
│                数据获取流程                        │
├──────────────────────────────────────────────────┤
│                                                  │
│  1. 微信PC客户端运行中                             │
│       ↓                                          │
│  2. chatlog扫描微信进程内存，提取数据库密钥          │
│       ↓                                          │
│  3. 用密钥解密SQLite数据库（SQLCipher 4）           │
│       ↓                                          │
│  4. 通过SQL查询读取全量聊天记录                     │
│       ↓                                          │
│  5. 通过HTTP API对外提供数据访问                    │
│       ↓                                          │
│  6. 我们的应用调用API，进行增量同步                 │
│       ↓                                          │
│  7. 数据进入我们的本地数据库 + 向量数据库            │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 2.3 历史数据迁移

**首次使用流程：**

1. 在手机微信中操作：`设置 → 聊天 → 聊天记录迁移与备份 → 迁移到电脑`
2. 选择迁移全部聊天记录（或选择指定聊天）
3. 等待迁移完成（取决于数据量，可能需要较长时间）
4. 迁移完成后，PC端本地数据库包含完整历史记录
5. chatlog读取数据库，一次性导入全部历史数据

**后续增量同步：**

- PC端微信运行时，新消息自动同步到本地数据库
- chatlog支持Webhook回调，新消息到达时自动通知应用
- 应用定时（如每5分钟）调用chatlog API拉取增量数据

### 2.4 数据字段说明

chatlog解密后可获取的主要数据结构：

**消息表（MSG）：**

| 字段 | 说明 | 示例 |
|------|------|------|
| localId | 本地消息ID | 12345 |
| TalkerId | 发送者ID | wxid_abc123 |
| Type | 消息类型 | 1=文本, 3=图片, 34=语音, 43=视频, 49=文件 |
| SubType | 子类型 | 6=文件, 8=链接 |
| IsSender | 是否自己发送 | 0=收到, 1=发送 |
| CreateTime | 发送时间戳 | 1719000000 |
| StrContent | 消息内容 | 文本内容/XML |
| StrTalker | 会话ID | wxid_abc123 / 12345@chatroom |
| BytesExtra | 附加数据 | 文件路径、缩略图等 |

**联系人表（Contact）：**

| 字段 | 说明 |
|------|------|
| UserName | 微信ID（wxid） |
| NickName | 昵称 |
| Remark | 备注名 |
| Type | 联系人类型 |
| SmallHeadImgUrl | 头像URL |

### 2.5 消息类型处理策略

| 消息类型 | 处理方式 | 可搜索 | 可索引 |
|----------|----------|--------|--------|
| 文本（1） | 直接存储全文 | ✅ | ✅ 向量化 |
| 图片（3） | 记录文件名+时间+发送者 | ✅ 元数据 | ⚠️ 仅元数据 |
| 语音（34） | 转换为MP3，可选ASR转文字 | ✅ 元数据 | ⚠️ 转文字后可索引 |
| 视频（43） | 记录文件名+时间+发送者 | ✅ 元数据 | ⚠️ 仅元数据 |
| 文件（49-6） | 记录文件名+大小+时间+发送者 | ✅ 元数据 | ✅ 文件名可索引 |
| 链接（49-8） | 提取标题+摘要+URL | ✅ | ✅ 标题摘要向量化 |
| 转账/红包 | 记录金额+时间+发送者 | ✅ 元数据 | ⚠️ 仅元数据 |
| 位置 | 提取经纬度+地址描述 | ✅ | ✅ 地址可索引 |
| 系统消息 | 记录原文 | ✅ | ❌ |

---

## 三、核心开源项目评估

### 3.1 数据获取层

#### chatlog（推荐 — 数据底座）

| 项目 | 详情 |
|------|------|
| 仓库 | github.com/sjzar/chatlog |
| 语言 | Go |
| 协议 | MIT |
| 维护状态 | 活跃维护（2025-2026持续更新） |
| 微信版本 | 支持3.x和4.x |
| 平台 | Windows + macOS |

**核心能力：**
- 自动提取微信数据库密钥（从进程内存）
- 解密SQLCipher 4加密的SQLite数据库
- 提供HTTP API查询聊天记录、联系人、群聊
- 支持MCP协议（可接入AI助手）
- 支持Webhook新消息回调
- 支持图片/语音解密
- 单文件二进制部署，开箱即用

**API示例：**
```
GET /api/v1/chatlog?time=2024-01-01~2024-01-31&talker=wxid_xxx
GET /api/v1/contact?username=wxid_xxx
GET /api/v1/session
GET /api/v1/chatroom?roomid=12345@chatroom
```

**选择理由：** 唯一同时支持微信4.x + 持续维护 + 提供完整API的项目。不需要自己写任何解密代码。

#### chatlog_alpha（增强版分支）

| 项目 | 详情 |
|------|------|
| 基础 | 基于chatlog二开 |
| 增强功能 | 向量搜索、语义检索、时间知识图谱、每日摘要模板 |
| 向量引擎 | Ollama embedding + 本地向量存储 |
| MCP推送 | 支持MCP主动推送新消息 |

**评估：** 功能更丰富，但属于社区fork，维护稳定性不如原版。可作为参考，但不建议直接依赖。向量搜索和AI摘要功能我们自己实现更可控。

#### WeChatMsg / MemoTrace / 留痕

| 项目 | 详情 |
|------|------|
| 仓库 | github.com/LC044/WeChatMsg |
| Stars | 20.7k+ |
| 语言 | Python |
| 定位 | 聊天记录导出工具 |
| 输出 | HTML / Word / CSV / TXT |

**评估：** 最知名的项目，但定位是导出工具，不提供API。适合个人使用，不适合做应用底座。可参考其数据库解析逻辑。

### 3.2 向量搜索层

#### 方案对比

| 方案 | 类型 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|----------|
| Chroma | 嵌入式向量数据库 | 轻量、Python原生、易部署 | 大规模性能一般 | 个人版首选 |
| Qdrant | 独立向量数据库 | 高性能、支持过滤 | 需独立部署 | 数据量大时升级 |
| LanceDB | 嵌入式向量数据库 | 列式存储、压缩率高 | 生态较小 | 备选 |
| FAISS | 向量检索库 | 极高性能 | 无数据库功能 | 需自行管理元数据 |
| SQLite-VSS | SQLite扩展 | 与业务数据库统一 | 功能简单 | 小规模数据 |

**推荐：Chroma**（个人版）→ 数据量超10万条后可迁移到Qdrant

#### Embedding模型选择

| 模型 | 部署方式 | 维度 | 中文效果 | 速度 |
|------|----------|------|----------|------|
| BAAI/bge-m3 | 本地Ollama | 1024 | 优秀 | 中 |
| BAAI/bge-small-zh | 本地 | 512 | 良好 | 快 |
| text-embedding-3-small | OpenAI API | 1536 | 良好 | 快（需联网） |
| DeepSeek embedding | API | 1024 | 优秀 | 快（需联网） |

**推荐：BAAI/bge-m3**（本地部署，中文效果优秀，无需联网，免费）

### 3.3 知识库导出层

#### wechat-to-obsidian

| 项目 | 详情 |
|------|------|
| 功能 | 将微信聊天记录导出为Obsidian Markdown |
| 格式 | 按日期生成文件，支持附件、双向链接、标签 |
| 参考 | 可参考其格式设计，但自行实现导出逻辑 |

### 3.4 企业微信API（备选路线）

如果未来转向企业微信：
- 官方提供「会话内容存档」API
- 完全合法合规，官方SDK
- 可获取混群（企微+个人微信）聊天记录
- 需要企业认证 + 开通权限 + 员工同意
- **当前不采用，但作为未来企业版的备选**

---

## 四、系统架构设计

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    展示层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Web UI   │  │ Obsidian │  │ MCP 接口  │             │
│  │ React    │  │ 导出     │  │ (AI助手) │             │
│  └──────────┘  └──────────┘  └──────────┘             │
├─────────────────────────────────────────────────────────┤
│                    应用层（自研）                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ 客户画像  │  │ AI摘要   │  │ 搜索服务  │             │
│  │ 引擎     │  │ 引擎     │  │          │             │
│  └──────────┘  └──────────┘  └──────────┘             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ 增量同步  │  │ Obsidian │  │ 通知提醒  │             │
│  │ 服务     │  │ 导出     │  │ 服务     │             │
│  └──────────┘  └──────────┘  └──────────┘             │
├─────────────────────────────────────────────────────────┤
│                    数据层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ SQLite   │  │ Chroma   │  │ 文件存储  │             │
│  │ 业务数据  │  │ 向量数据  │  │ 附件索引  │             │
│  └──────────┘  └──────────┘  └──────────┘             │
├─────────────────────────────────────────────────────────┤
│                    数据获取层                            │
│  ┌──────────────────────────────────────────┐          │
│  │  chatlog (HTTP API)                      │          │
│  │  · 自动解密微信数据库                      │          │
│  │  · 提供查询API                            │          │
│  │  · Webhook新消息回调                      │          │
│  └──────────────────────────────────────────┘          │
├─────────────────────────────────────────────────────────┤
│                    数据源                                │
│  ┌──────────────────────────────────────────┐          │
│  │  微信PC客户端 (运行中)                     │          │
│  │  本地SQLite数据库 (SQLCipher加密)          │          │
│  └──────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────┘
```

### 4.2 数据流

```
微信PC端 → chatlog解密 → chatlog HTTP API
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
              增量同步服务           Webhook回调
                    ↓                   ↓
              SQLite存储           实时处理
                    ↓                   ↓
              Chroma向量化        客户画像更新
                    ↓                   ↓
              搜索服务             AI摘要触发
                    ↓                   ↓
              Web UI展示           通知推送
```

### 4.3 模块划分

#### 模块1：数据同步服务（sync_service）
- 负责调用chatlog API拉取数据
- 首次全量同步 + 后续增量同步
- 数据清洗、去重、格式标准化
- 写入SQLite + 触发向量化

#### 模块2：向量搜索服务（search_service）
- 将文本消息通过embedding模型向量化
- 存入Chroma向量数据库
- 提供语义搜索API
- 支持时间范围、联系人、群聊等过滤条件

#### 模块3：客户画像引擎（profile_engine）
- 基于聊天内容分析联系人特征
- 提取关键词：行业、公司、产品、需求
- 判断客户意向度（潜在/活跃/流失）
- 生成联系人画像卡片

#### 模块4：AI摘要引擎（summary_engine）
- 定时触发（如每天晚上10点）
- 对指定群聊当天消息进行归纳
- 筛选值得关注的信息
- 生成每日摘要报告

#### 模块5：Obsidian导出（obsidian_exporter）
- 按日期/联系人/群聊生成Markdown文件
- 添加YAML frontmatter（元数据）
- 生成双向链接（[[联系人]]、[[日期]]）
- 生成标签和图谱关系

#### 模块6：Web UI（web_ui）
- 聊天记录浏览（类似微信界面）
- 搜索框（支持语义搜索）
- 客户画像卡片
- 每日摘要查看
- 设置页面

---

## 五、技术栈选型

### 5.1 技术栈总览

| 层级 | 技术选型 | 理由 |
|------|----------|------|
| 数据获取 | chatlog（Go二进制） | 开箱即用，无需自己写解密 |
| 后端框架 | Python FastAPI | 异步高性能，AI生态丰富 |
| 业务数据库 | SQLite | 轻量本地，无需独立部署 |
| 向量数据库 | Chroma | Python原生，嵌入式部署 |
| Embedding | BAAI/bge-m3 (Ollama) | 本地部署，中文效果好 |
| LLM | DeepSeek API / 本地Ollama | 便宜/免费，效果好 |
| 前端框架 | React 18 + Vite | 与投资管理系统统一技术栈 |
| UI组件库 | Ant Design 5 | 组件丰富，中文友好 |
| 搜索UI | 自研（基于Ant Design） | 定制化需求 |
| Obsidian导出 | Python脚本生成Markdown | 简单直接 |

### 5.2 运行时依赖

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 后端运行时 |
| Node.js | 18+ | 前端构建 |
| chatlog | latest | 数据获取层 |
| Ollama | latest | 本地embedding模型 |
| 微信PC端 | 4.x | 数据源（需保持运行） |

### 5.3 Python核心依赖

```
fastapi
uvicorn
chromadb
ollama
httpx          # 调用chatlog API
sqlalchemy     # SQLite ORM
pydantic       # 数据模型
python-multipart
deepseek       # LLM API (可选)
jinja2         # Markdown模板
```

### 5.4 前端核心依赖

```
react
react-dom
antd
@ant-design/icons
echarts / @echarts-for-react
axios
react-router-dom
dayjs
```

---

## 六、功能模块详细设计

### 6.1 数据同步模块

**首次全量同步流程：**

```python
# 伪代码
async def initial_sync():
    # 1. 通过chatlog API获取所有会话列表
    sessions = await chatlog_api.get_sessions()
    
    # 2. 遍历每个会话，拉取全部历史消息
    for session in sessions:
        messages = await chatlog_api.get_messages(
            talker=session.talker,
            start_time="2000-01-01",
            end_time="now"
        )
        
        # 3. 数据清洗 + 标准化
        cleaned = clean_and_normalize(messages)
        
        # 4. 存入SQLite
        await db.insert_messages(cleaned)
        
        # 5. 文本消息向量化
        for msg in cleaned:
            if msg.type == "text":
                embedding = await ollama.embed(msg.content)
                await chroma.add(msg.id, embedding, metadata)
    
    # 6. 标记同步完成
    await db.set_sync_status("initial_complete")
```

**增量同步流程：**

```python
async def incremental_sync():
    # 1. 获取上次同步时间
    last_sync = await db.get_last_sync_time()
    
    # 2. 拉取新消息
    new_messages = await chatlog_api.get_messages(
        start_time=last_sync,
        end_time="now"
    )
    
    # 3. 去重（根据localId）
    new_messages = deduplicate(new_messages)
    
    # 4. 存储 + 向量化
    for msg in new_messages:
        await db.insert_message(msg)
        if msg.type == "text":
            await vectorize_and_store(msg)
    
    # 5. 更新同步时间
    await db.update_sync_time()
```

### 6.2 向量搜索模块

**搜索API设计：**

```
POST /api/search
{
    "query": "之前谁跟我聊过半导体设备的设计需求？",
    "filters": {
        "time_range": ["2024-01-01", "2026-07-22"],
        "talker": null,          # 可选：指定联系人/群
        "msg_type": ["text"],    # 可选：消息类型
        "is_sender": null         # 可选：发送方向
    },
    "top_k": 20
}
```

**返回结果：**

```json
{
    "results": [
        {
            "message_id": "msg_12345",
            "content": "老王，我们这边有个电池产线的非标设计需求...",
            "talker": "wxid_xxx",
            "talker_name": "张工-烽禾升",
            "time": "2025-03-15 14:23:00",
            "similarity": 0.87,
            "context": [
                {"content": "上一条消息", "time": "..."},
                {"content": "下一条消息", "time": "..."}
            ]
        }
    ]
}
```

### 6.3 客户画像模块

**画像数据结构：**

```json
{
    "wxid": "wxid_abc123",
    "nickname": "张工",
    "remark": "张工-烽禾升",
    "avatar": "local_path/avatar.jpg",
    "first_contact": "2024-06-15",
    "last_active": "2026-07-22",
    "message_count": 342,
    "profile": {
        "company": "昆山烽禾升",
        "industry": "新能源设备",
        "role": "技术工程师",
        "interests": ["非标设计", "电池产线", "自动化"],
        "interaction_level": "high",
        "customer_status": "active",
        "potential_value": "high",
        "key_topics": [
            {"topic": "电池模组组装线", "count": 45},
            {"topic": "设计方案评审", "count": 23}
        ]
    },
    "ai_summary": "张工是昆山烽禾升的技术工程师，2024年6月添加...",
    "tags": ["客户-活跃", "新能源", "烽禾升"]
}
```

**画像生成流程：**

1. 提取与该联系人的所有聊天记录
2. 调用LLM分析内容，提取结构化信息
3. 结合消息频率、时间分布判断活跃度
4. 生成自然语言画像描述
5. 定期（如每周）更新画像

### 6.4 每日摘要模块

**摘要生成流程：**

1. 定时触发（每天22:00）
2. 获取用户关注的群聊列表
3. 拉取当天每个群的所有消息
4. 调用LLM进行归纳：
   - 今日关键信息（谁说了什么重要的事）
   - 待跟进事项（需要回复/处理的）
   - 行业动态（技术讨论、市场信息）
   - 无效信息过滤（广告、闲聊）
5. 生成摘要报告，推送到Web UI / 微信文件传输助手

**摘要示例：**

```markdown
# 2026-07-22 群消息摘要

## 烽禾升技术交流群（15条有效消息 / 87条总消息）

### 关键信息
- 张工提到下周要来苏州看设备，问有没有时间接待
- 李总发了一个竞品方案PDF，说价格比我们低20%

### 待跟进
- ⚠️ 张工的拜访请求需要回复
- ⚠️ 竞品价格问题需要准备应对话术

### 行业动态
- 讨论了4680电池产线的自动化方案趋势

### 可忽略
- 3条广告，2条签到，65条闲聊
```

### 6.5 Obsidian导出模块

**导出格式：**

```markdown
---
date: 2026-07-22
talker: 张工-烽禾升
wxid: wxid_abc123
type: private
message_count: 15
tags:
  - 客户
  - 烽禾升
---

# 2026-07-22 与 张工-烽禾升 的对话

## 14:23 张工
老王，我们这边有个电池产线的非标设计需求，方便聊聊吗？

## 14:25 我
可以，什么类型的产线？发个需求文档过来看看

## 14:30 张工
[文件] 电池模组组装线需求说明.pdf
4680圆柱电池，节拍3PPM，看看能不能做

---
相关：[[张工-烽禾升]] [[2026-07-22]] [[烽禾升技术交流群]]
```

---

## 七、数据库设计

### 7.1 SQLite核心表结构

```sql
-- 消息表
CREATE TABLE messages (
    id TEXT PRIMARY KEY,           -- 消息唯一ID (wxid + localId + time)
    local_id INTEGER,              -- 微信本地消息ID
    talker TEXT NOT NULL,          -- 发送者wxid或群ID
    is_sender INTEGER DEFAULT 0,   -- 0=收到, 1=自己发送
    msg_type INTEGER NOT NULL,     -- 消息类型
    msg_subtype INTEGER,           -- 消息子类型
    content TEXT,                  -- 消息内容（文本/XML）
    create_time INTEGER NOT NULL,  -- 发送时间戳
    group_sender TEXT,             -- 群内发送者wxid（群聊时）
    file_path TEXT,                -- 附件本地路径
    file_name TEXT,                -- 附件文件名
    file_size INTEGER,             -- 附件大小
    raw_data TEXT,                 -- 原始数据（JSON）
    synced_at TEXT DEFAULT (datetime('now')),
    vectorized INTEGER DEFAULT 0   -- 是否已向量化
);

-- 联系人表
CREATE TABLE contacts (
    wxid TEXT PRIMARY KEY,
    nickname TEXT,
    remark TEXT,
    avatar_path TEXT,
    type INTEGER,                  -- 联系人类型
    first_seen TEXT,               -- 首次出现在聊天记录中的时间
    last_active TEXT,              -- 最后活跃时间
    message_count INTEGER DEFAULT 0,
    profile_data TEXT,             -- 画像JSON
    profile_updated_at TEXT,
    tags TEXT                      -- 标签JSON数组
);

-- 群聊表
CREATE TABLE chatrooms (
    room_id TEXT PRIMARY KEY,      -- 群ID (xxx@chatroom)
    room_name TEXT,
    member_count INTEGER,
    notice TEXT,                   -- 群公告
    owner TEXT,                    -- 群主wxid
    monitored INTEGER DEFAULT 0,   -- 是否监控（生成摘要）
    tags TEXT
);

-- 群成员表
CREATE TABLE chatroom_members (
    room_id TEXT,
    wxid TEXT,
    display_name TEXT,             -- 群昵称
    join_time TEXT,
    PRIMARY KEY (room_id, wxid)
);

-- 每日摘要表
CREATE TABLE daily_summaries (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    scope TEXT NOT NULL,           -- room_id 或 wxid
    scope_name TEXT,
    total_messages INTEGER,
    effective_messages INTEGER,
    summary TEXT,                  -- 摘要Markdown
    action_items TEXT,             -- 待办事项JSON
    created_at TEXT DEFAULT (datetime('now'))
);

-- 同步状态表
CREATE TABLE sync_status (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_sync_time TEXT,
    initial_complete INTEGER DEFAULT 0,
    chatlog_version TEXT,
    wechat_version TEXT,
    total_messages INTEGER DEFAULT 0,
    total_contacts INTEGER DEFAULT 0
);

-- 索引
CREATE INDEX idx_messages_talker ON messages(talker);
CREATE INDEX idx_messages_time ON messages(create_time);
CREATE INDEX idx_messages_type ON messages(msg_type);
CREATE INDEX idx_messages_talker_time ON messages(talker, create_time);
```

### 7.2 Chroma向量数据库

```python
# Chroma Collection设计
collection = chroma_client.create_collection(
    name="wechat_messages",
    metadata={"description": "微信聊天记录向量索引"}
)

# 每条文本消息存储：
{
    "id": "msg_xxx",           # 与SQLite中id一致
    "embedding": [0.1, ...],   # bge-m3 1024维向量
    "document": "消息原文",
    "metadata": {
        "talker": "wxid_xxx",
        "talker_name": "张工",
        "time": "2026-07-22 14:23:00",
        "is_sender": 0,
        "msg_type": 1,
        "group_sender": null
    }
}
```

---

## 八、API设计

### 8.1 后端API路由

```
# 数据同步
POST   /api/sync/initial              # 触发首次全量同步
POST   /api/sync/incremental           # 触发增量同步
GET    /api/sync/status                # 同步状态

# 消息查询
GET    /api/messages                   # 查询消息列表
GET    /api/messages/{id}              # 消息详情
GET    /api/messages/by-talker         # 按联系人查询
GET    /api/messages/by-date           # 按日期查询

# 搜索
POST   /api/search/semantic            # 语义搜索
GET    /api/search/keyword             # 关键词搜索
POST   /api/search/advanced            # 高级搜索（多条件）

# 联系人
GET    /api/contacts                   # 联系人列表
GET    /api/contacts/{wxid}            # 联系人详情
GET    /api/contacts/{wxid}/profile    # 客户画像
POST   /api/contacts/{wxid}/profile    # 手动触发画像生成
GET    /api/contacts/potential         # 潜在客户列表

# 群聊
GET    /api/chatrooms                  # 群聊列表
GET    /api/chatrooms/{id}             # 群聊详情
POST   /api/chatrooms/{id}/monitor     # 设置监控

# 摘要
GET    /api/summaries                  # 摘要列表
GET    /api/summaries/{date}           # 按日期查看
POST   /api/summaries/generate         # 手动生成摘要

# 导出
POST   /api/export/obsidian            # 导出Obsidian格式
GET    /api/export/status              # 导出状态

# chatlog代理
GET    /api/chatlog/status             # chatlog运行状态
GET    /api/chatlog/sessions           # chatlog会话列表（代理）
```

---

## 九、风险分析

### 9.1 技术风险

| 风险 | 影响 | 概率 | 应对措施 |
|------|------|------|----------|
| 微信大版本更新导致密钥提取失效 | 高 | 中 | 依赖chatlog社区跟进；数据已同步到本地不受影响 |
| chatlog项目停止维护 | 高 | 低 | 可fork自维护；密钥提取逻辑相对稳定 |
| 向量数据库性能瓶颈 | 中 | 低 | 个人数据量<100万条，Chroma足够；超量可迁移Qdrant |
| LLM API不稳定 | 中 | 低 | 支持多LLM后端切换；关键功能可降级为关键词搜索 |
| Ollama本地模型占用资源 | 低 | 中 | bge-m3约2GB内存，现代PC可承受 |

### 9.2 合规风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 解密微信数据的法律风险 | 中 | 仅解密个人数据用于备份；不对外提供数据 |
| 用户隐私数据泄露 | 高 | 全本地处理；不联网上传；数据库加密 |
| 软件分发合规 | 中 | 个人使用无风险；如商用需用户授权+隐私协议 |

### 9.3 产品风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 用户觉得手动迁移历史记录麻烦 | 中 | 提供详细引导文档；迁移只需一次 |
| PC端微信未运行时无法同步 | 低 | 可接受；运行时自动补同步 |
| 群消息太多导致摘要质量差 | 中 | 分群摘要；LLM prompt优化；支持用户自定义关注关键词 |

---

## 十、开发路线图

### Phase 0：验证（1-2天）

**目标：验证chatlog可用性**

- [ ] 下载chatlog，在Windows上运行
- [ ] 测试密钥提取 + 数据库解密
- [ ] 调用chatlog HTTP API，验证数据完整性
- [ ] 检查消息字段是否包含所需信息
- [ ] 记录数据量、查询速度等基准数据

**交付物：** chatlog验证报告

### Phase 1：数据同步 + 存储（1周）

**目标：跑通数据从微信到本地数据库的完整链路**

- [ ] 搭建Python FastAPI项目骨架
- [ ] 实现chatlog API客户端
- [ ] 实现首次全量同步
- [ ] 实现增量同步（定时+Webhook）
- [ ] SQLite数据库建表 + 数据写入
- [ ] 搭建React前端骨架
- [ ] 基本的消息列表浏览页面

**交付物：** 可以浏览全部历史聊天记录的Web应用

### Phase 2：向量搜索（1周）

**目标：实现语义搜索**

- [ ] 安装Ollama + bge-m3模型
- [ ] 集成Chroma向量数据库
- [ ] 实现文本消息向量化
- [ ] 实现语义搜索API
- [ ] 前端搜索界面
- [ ] 搜索结果展示 + 上下文

**交付物：** 可以用自然语言搜索聊天记录

### Phase 3：客户画像（1-2周）

**目标：AI自动生成联系人画像**

- [ ] 画像数据结构设计
- [ ] LLM分析聊天内容提取关键信息
- [ ] 客户活跃度/意向度计算
- [ ] 画像卡片UI
- [ ] 潜在客户筛选
- [ ] 画像定期更新机制

**交付物：** 每个联系人都有AI生成的画像卡片

### Phase 4：每日摘要（1周）

**目标：AI自动归纳群消息**

- [ ] 定时任务调度
- [ ] 群消息聚合 + LLM归纳
- [ ] 摘要报告生成
- [ ] 摘要查看页面
- [ ] 关注关键词配置

**交付物：** 每天自动生成群消息摘要

### Phase 5：Obsidian导出（3-5天）

**目标：导出为Obsidian知识库**

- [ ] Markdown模板设计
- [ ] 双向链接生成
- [ ] 按日期/联系人/群聊导出
- [ ] 标签和图谱关系

**交付物：** 一键导出Obsidian知识库

### Phase 6：优化打磨（持续）

- [ ] 性能优化（大数量查询速度）
- [ ] UI/UX打磨
- [ ] 语音转文字（ASR）
- [ ] 文件附件管理
- [ ] 数据备份/恢复

---

## 十一、项目目录结构

```
wechatagent/
├── docs/
│   └── technical-feasibility.md     # 本文档
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI入口
│   │   ├── config.py                # 配置
│   │   ├── api/
│   │   │   ├── sync.py              # 同步相关API
│   │   │   ├── search.py            # 搜索相关API
│   │   │   ├── contacts.py          # 联系人API
│   │   │   ├── chatrooms.py         # 群聊API
│   │   │   ├── summaries.py         # 摘要API
│   │   │   └── export.py            # 导出API
│   │   ├── services/
│   │   │   ├── chatlog_client.py    # chatlog API客户端
│   │   │   ├── sync_service.py      # 数据同步
│   │   │   ├── search_service.py    # 向量搜索
│   │   │   ├── profile_engine.py    # 客户画像
│   │   │   ├── summary_engine.py    # AI摘要
│   │   │   └── obsidian_exporter.py # Obsidian导出
│   │   ├── models/
│   │   │   ├── database.py          # SQLAlchemy模型
│   │   │   └── schemas.py           # Pydantic模型
│   │   └── utils/
│   │       ├── llm.py               # LLM调用封装
│   │       ├── embedding.py         # Embedding封装
│   │       └── wechat_types.py      # 微信消息类型处理
│   ├── requirements.txt
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Messages.tsx         # 消息浏览
│   │   │   ├── Search.tsx           # 搜索
│   │   │   ├── Contacts.tsx         # 联系人/画像
│   │   │   ├── Summaries.tsx        # 每日摘要
│   │   │   ├── Settings.tsx         # 设置
│   │   │   └── Export.tsx           # 导出
│   │   ├── components/
│   │   └── api/
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── install_chatlog.sh           # chatlog安装脚本
│   └── initial_sync.py              # 首次同步脚本
└── README.md
```

---

## 十二、下一步行动

1. **立即执行：** 下载chatlog，在老王的Windows电脑上验证数据解密和API可用性
2. **验证通过后：** 搭建项目骨架，开始Phase 1开发
3. **并行准备：** 安装Ollama + bge-m3模型，为Phase 2做准备

---

> 本文档基于2026年7月的技术调研编写。微信和chatlog的版本更新可能影响部分技术细节，开发时以最新版本为准。
