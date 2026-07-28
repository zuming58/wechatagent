import { useMemo, useState } from "react";
import {
  ArrowClockwise,
  Buildings,
  CalendarBlank,
  CaretDown,
  Check,
  CheckCircle,
  CheckSquareOffset,
  ClockCounterClockwise,
  CloudCheck,
  Copy,
  DotsThree,
  GearSix,
  LinkSimple,
  ListChecks,
  MagnifyingGlass,
  NotePencil,
  PaperPlaneTilt,
  ShieldCheck,
  Sparkle,
  Tag,
  Trash,
  UsersThree,
  X,
} from "@phosphor-icons/react";

const contacts = [
  {
    id: "zhang",
    name: "张工",
    company: "烽禾升 · CTO",
    role: "技术决策人",
    avatar: null,
    avatarTone: "sage",
    time: "10:42",
    preview: "下周二把方案细节再过一遍",
    tags: ["重点客户", "智能制造", "深圳"],
    facts: [
      ["公司与角色", "烽禾升科技 CTO，负责技术路线与供应商选型"],
      ["沟通偏好", "偏好直接给结论，重要事项在工作日上午确认"],
      ["当前项目", "工厂知识库二期，计划 8 月进入方案评审"],
    ],
    needs: ["需要离线部署与权限审计", "关注 200 人规模下的检索速度", "希望先用一个业务群做试点"],
  },
  {
    id: "chen",
    name: "陈姐",
    company: "远望咨询 · 合伙人",
    role: "长期合作伙伴",
    avatar: null,
    avatarTone: "rose",
    time: "昨天",
    preview: "客户访谈纪要我晚点发你",
    tags: ["合作伙伴", "咨询", "上海"],
    facts: [
      ["公司与角色", "远望咨询合伙人，长期负责制造业数字化项目"],
      ["沟通偏好", "习惯用语音快速确认，正式材料发文档"],
      ["合作状态", "已共同服务 4 个客户，正在准备联合方案"],
    ],
    needs: ["需要一份可对外展示的产品介绍", "希望支持访谈记录自动归档", "下月安排一次客户共创会"],
  },
  {
    id: "wang",
    name: "王总",
    company: "澜石资本 · 投资人",
    role: "资源连接人",
    avatar: null,
    avatarTone: "blue",
    time: "周一",
    preview: "我介绍一位产业方给你认识",
    tags: ["投资", "产业资源", "北京"],
    facts: [
      ["公司与角色", "澜石资本合伙人，关注企业服务与 AI 应用"],
      ["沟通偏好", "先看一页纸摘要，再约 30 分钟电话"],
      ["最近互动", "5 月行业会后保持联系，已介绍 2 位产业客户"],
    ],
    needs: ["希望看到真实留存数据", "关注本地数据的合规边界", "等待下一版演示链接"],
  },
  {
    id: "li",
    name: "李明",
    company: "知行科技 · 产品负责人",
    role: "产品同行",
    avatar: null,
    avatarTone: "violet",
    time: "6月18日",
    preview: "你这个关系记忆的思路挺好",
    tags: ["产品", "AI 应用", "杭州"],
    facts: [
      ["公司与角色", "知行科技产品负责人，负责 AI 助手方向"],
      ["沟通偏好", "喜欢先看可操作 Demo，再讨论产品边界"],
      ["共同话题", "长期记忆、个人知识库、数据隐私"],
    ],
    needs: ["希望支持跨群查找同一项目", "对知识图谱可视化感兴趣", "可以参与首批内测"],
  },
  {
    id: "zhou",
    name: "周老师",
    company: "南方研究院 · 研究员",
    role: "行业专家",
    avatar: null,
    avatarTone: "amber",
    time: "6月12日",
    preview: "那篇研究报告找到了",
    tags: ["研究", "知识管理", "广州"],
    facts: [["研究方向", "组织知识管理与协作网络"], ["沟通偏好", "资料完整、引用清晰"], ["最近互动", "分享了两篇行业报告"]],
    needs: ["需要保留资料来源", "希望支持研究主题聚合", "关注长期信息衰减"],
  },
  {
    id: "lin",
    name: "林峰",
    company: "锐度设计 · 创始人",
    role: "设计顾问",
    avatar: null,
    avatarTone: "slate",
    time: "6月08日",
    preview: "视觉方向我整理了三个版本",
    tags: ["设计", "品牌", "深圳"],
    facts: [["公司与角色", "锐度设计创始人，负责品牌与体验设计"], ["沟通偏好", "用截图和标注快速沟通"], ["合作状态", "正在共创产品视觉体系"]],
    needs: ["需要确认设计关键词", "等待产品信息架构", "建议先完善核心工作台"],
  },
];

const navItems = [
  ["关系记忆", UsersThree],
  ["待办事项", CheckSquareOffset],
  ["全局搜索", MagnifyingGlass],
  ["时间线", ClockCounterClockwise],
  ["标签管理", Tag],
];

const initialTasks = [
  { id: 1, text: "周二前发送离线部署方案", due: "明天 18:00", done: false },
  { id: 2, text: "补充 200 人并发测试数据", due: "7 月 25 日", done: false },
  { id: 3, text: "整理试点群的实施清单", due: "本周", done: true },
];

const evidence = [
  { date: "今天 10:42", title: "明确了下次方案沟通时间", body: "下周二上午有空，我们把离线部署和权限这两块再过一遍。", source: "原文 3" },
  { date: "7 月 20 日", title: "补充了试点范围", body: "可以先从售后群开始，先跑一个月看看检索和整理的效果。", source: "原文 5" },
  { date: "7 月 16 日", title: "提出数据安全要求", body: "客户资料不能上云，最好能看到谁在什么时候访问过。", source: "原文 4" },
];

function Avatar({ contact, size = "medium" }) {
  if (contact.avatar) {
    return <img className={`avatar avatar--${size}`} src={contact.avatar} alt={`${contact.name}的微信头像`} />;
  }

  return (
    <span className={`avatar avatar--${size} avatar--fallback avatar--${contact.avatarTone}`} aria-label={`${contact.name}暂无微信头像`}>
      {contact.name.slice(0, 1)}
    </span>
  );
}

export function App() {
  const [activeNav, setActiveNav] = useState("关系记忆");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("zhang");
  const [activeTab, setActiveTab] = useState("关系总览");
  const [suggestions, setSuggestions] = useState([
    "张工可能是最终技术决策人，建议标记为“关键决策人”",
    "“离线部署”在近 30 天出现 6 次，可升级为高优先级需求",
  ]);
  const [tasks, setTasks] = useState(initialTasks);
  const [drawer, setDrawer] = useState(null);
  const [toast, setToast] = useState("");

  const selected = contacts.find((contact) => contact.id === selectedId) || contacts[0];
  const filteredContacts = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return contacts;
    return contacts.filter((contact) => `${contact.name}${contact.company}${contact.role}`.toLowerCase().includes(term));
  }, [query]);

  const notify = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  };

  const chooseContact = (id) => {
    setSelectedId(id);
    setActiveTab("关系总览");
  };

  const handleSuggestion = (index, accepted) => {
    setSuggestions((items) => items.filter((_, itemIndex) => itemIndex !== index));
    notify(accepted ? "已写入已确认事实" : "已忽略这条建议");
  };

  const toggleTask = (id) => {
    setTasks((items) => items.map((task) => (task.id === id ? { ...task, done: !task.done } : task)));
  };

  return (
    <div className="app-shell">
      <aside className="primary-nav" aria-label="主导航">
        <div>
          <div className="brand">
            <span className="brand-mark"><LinkSimple weight="bold" /></span>
            <span>微信关系记忆</span>
          </div>
          <nav className="nav-list">
            {navItems.map(([label, Icon]) => (
              <button
                className={`nav-item ${activeNav === label ? "is-active" : ""}`}
                key={label}
                onClick={() => {
                  setActiveNav(label);
                  if (label !== "关系记忆") notify(`${label}模块将在下一阶段接入`);
                }}
              >
                <Icon size={19} weight={activeNav === label ? "fill" : "regular"} />
                <span>{label}</span>
                {label === "待办事项" && <span className="nav-badge">2</span>}
              </button>
            ))}
          </nav>
        </div>

        <div className="nav-footer">
          <button className="nav-item"><GearSix size={19} /><span>设置</span></button>
          <button className="nav-item"><Trash size={19} /><span>回收站</span></button>
          <div className="local-profile">
            <div className="local-avatar">我</div>
            <div><strong>本地账户</strong><span><ShieldCheck size={13} weight="fill" /> 数据仅存本机</span></div>
            <DotsThree size={18} />
          </div>
        </div>
      </aside>

      <section className="contacts-pane" aria-label="联系人列表">
        <div className="contacts-head">
          <label className="search-field">
            <MagnifyingGlass size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索联系人、公司或角色" />
            <kbd>⌘ K</kbd>
          </label>
          <div className="list-title-row">
            <div><h2>全部联系人</h2><span>{filteredContacts.length} / 128</span></div>
            <button className="icon-button" title="筛选联系人"><CaretDown size={17} /></button>
          </div>
        </div>

        <div className="contact-list">
          {filteredContacts.map((contact) => (
            <button
              className={`contact-row ${selectedId === contact.id ? "is-selected" : ""}`}
              key={contact.id}
              onClick={() => chooseContact(contact.id)}
            >
              <Avatar contact={contact} />
              <span className="contact-copy">
                <span className="contact-name-line"><strong>{contact.name}</strong><time>{contact.time}</time></span>
                <span className="contact-company">{contact.company}</span>
                <span className="contact-preview">{contact.preview}</span>
              </span>
            </button>
          ))}
          {filteredContacts.length === 0 && <div className="empty-state">没有找到匹配的联系人</div>}
        </div>
      </section>

      <main className="workspace">
        <div className="sync-bar">
          <span><CloudCheck size={16} weight="fill" /> 本地数据已同步 · 今天 10:44</span>
          <button onClick={() => notify("已完成增量同步，暂无新消息")}><ArrowClockwise size={15} /> 立即同步</button>
        </div>

        <header className="profile-header">
          <div className="profile-identity">
            <Avatar contact={selected} size="large" />
            <div>
              <div className="profile-name"><h1>{selected.name}</h1><span>{selected.role}</span></div>
              <p><Buildings size={16} /> {selected.company}</p>
              <div className="tag-row">{selected.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
              <button className="avatar-status" onClick={() => setDrawer({ type: "avatar", title: "头像同步规则" })}><ArrowClockwise size={12} /> 微信头像自动同步 · 暂无头像时显示姓名首字</button>
            </div>
          </div>
          <div className="profile-actions">
            <button className="secondary-button" onClick={() => setDrawer({ type: "search", title: `搜索与${selected.name}的记录` })}><MagnifyingGlass size={17} /> 搜索记录</button>
            <button className="primary-button" onClick={() => notify("已确认 2 条待办，提醒已开启")}><CheckCircle size={17} weight="fill" /> 确认待办</button>
            <button className="icon-button" title="更多操作"><DotsThree size={20} /></button>
          </div>
        </header>

        <div className="tabs" role="tablist">
          {["关系总览", "聊天证据", "待办事项", "标签与备注"].map((tab) => (
            <button className={activeTab === tab ? "is-active" : ""} key={tab} onClick={() => setActiveTab(tab)}>
              {tab}
              {tab === "待办事项" && <span>{tasks.filter((task) => !task.done).length}</span>}
            </button>
          ))}
        </div>

        <section className="content-scroll">
          {activeTab === "关系总览" && (
            <div className="dashboard-grid">
              <div className="dashboard-column">
                <section className="panel panel--mint">
                  <div className="panel-heading">
                    <div><span className="panel-icon panel-icon--mint"><Check size={17} weight="bold" /></span><div><h3>已确认事实</h3><p>来自聊天记录并经你确认</p></div></div>
                    <button className="text-button" onClick={() => notify("已进入事实编辑模式")}><NotePencil size={16} /> 编辑</button>
                  </div>
                  <div className="fact-list">
                    {selected.facts.map(([label, value]) => (
                      <div className="fact-row" key={label}><span>{label}</span><p>{value}</p><button onClick={() => navigator.clipboard?.writeText(value).then(() => notify("已复制"))}><Copy size={15} /></button></div>
                    ))}
                  </div>
                </section>

                <section className="panel panel--blue">
                  <div className="panel-heading">
                    <div><span className="panel-icon panel-icon--blue"><Sparkle size={17} weight="fill" /></span><div><h3>AI 新发现</h3><p>{suggestions.length ? `${suggestions.length} 条等待确认` : "已处理完毕"}</p></div></div>
                  </div>
                  <div className="suggestion-list">
                    {suggestions.map((suggestion, index) => (
                      <div className="suggestion" key={suggestion}>
                        <p>{suggestion}</p>
                        <div><button onClick={() => handleSuggestion(index, false)}><X size={14} /> 忽略</button><button className="accept" onClick={() => handleSuggestion(index, true)}><Check size={14} /> 确认</button></div>
                      </div>
                    ))}
                    {!suggestions.length && <div className="resolved-state"><CheckCircle size={20} weight="fill" /> AI 建议已全部处理</div>}
                  </div>
                </section>

                <section className="panel panel--amber">
                  <div className="panel-heading">
                    <div><span className="panel-icon panel-icon--amber"><ListChecks size={17} weight="fill" /></span><div><h3>需求与关注点</h3><p>从近 90 天对话整理</p></div></div>
                  </div>
                  <ul className="need-list">{selected.needs.map((need) => <li key={need}><span />{need}</li>)}</ul>
                </section>
              </div>

              <div className="dashboard-column dashboard-column--right">
                <section className="panel panel--lavender task-panel">
                  <div className="panel-heading">
                    <div><span className="panel-icon panel-icon--lavender"><CheckSquareOffset size={17} weight="fill" /></span><div><h3>待办事项</h3><p>{tasks.filter((task) => !task.done).length} 项未完成</p></div></div>
                    <button className="text-button" onClick={() => setActiveTab("待办事项")}>查看全部</button>
                  </div>
                  <div className="task-list">
                    {tasks.map((task) => (
                      <button className={`task-row ${task.done ? "is-done" : ""}`} key={task.id} onClick={() => toggleTask(task.id)}>
                        <span className="task-check">{task.done && <Check size={13} weight="bold" />}</span>
                        <span><strong>{task.text}</strong><small><CalendarBlank size={13} /> {task.due}</small></span>
                      </button>
                    ))}
                  </div>
                </section>

                <section className="panel timeline-panel">
                  <div className="panel-heading">
                    <div><span className="panel-icon panel-icon--gray"><ClockCounterClockwise size={17} /></span><div><h3>最近证据</h3><p>关键结论都可追溯到原文</p></div></div>
                    <button className="text-button" onClick={() => setActiveTab("聊天证据")}>完整时间线</button>
                  </div>
                  <div className="timeline">
                    {evidence.map((item) => (
                      <article className="timeline-item" key={item.date}>
                        <span className="timeline-dot" />
                        <time>{item.date}</time>
                        <h4>{item.title}</h4>
                        <p>“{item.body}”</p>
                        <button onClick={() => setDrawer({ type: "evidence", title: item.title, body: item.body, date: item.date })}>{item.source} <CaretDown size={13} /></button>
                      </article>
                    ))}
                  </div>
                </section>
              </div>
            </div>
          )}

          {activeTab === "聊天证据" && (
            <section className="full-panel">
              <div className="full-panel-heading"><div><h2>聊天证据时间线</h2><p>所有摘要都保留原始消息位置，方便随时核对。</p></div><button className="secondary-button"><CalendarBlank size={16} /> 最近 90 天</button></div>
              <div className="evidence-feed">{evidence.concat(evidence).map((item, index) => <article key={`${item.date}-${index}`}><time>{index > 2 ? `6 月 ${26 - index} 日` : item.date}</time><div><span>{index % 2 === 0 ? "张工" : "我"}</span><p>{item.body}</p><button onClick={() => setDrawer({ type: "evidence", title: item.title, body: item.body, date: item.date })}>查看上下文</button></div></article>)}</div>
            </section>
          )}

          {activeTab === "待办事项" && (
            <section className="full-panel">
              <div className="full-panel-heading"><div><h2>与 {selected.name} 相关的待办</h2><p>由对话自动识别，你确认后才会进入正式清单。</p></div><button className="primary-button" onClick={() => notify("新建待办功能已准备好")}><CheckSquareOffset size={16} /> 新建待办</button></div>
              <div className="large-task-list">{tasks.map((task) => <button className={task.done ? "is-done" : ""} onClick={() => toggleTask(task.id)} key={task.id}><span className="task-check">{task.done && <Check size={13} weight="bold" />}</span><span><strong>{task.text}</strong><small>{task.due} · 来自微信对话</small></span><CaretDown size={16} /></button>)}</div>
            </section>
          )}

          {activeTab === "标签与备注" && (
            <section className="full-panel notes-panel">
              <div className="full-panel-heading"><div><h2>标签与备注</h2><p>把你对这段关系的个人判断放在这里。</p></div><button className="primary-button" onClick={() => notify("标签已保存")}><Check size={16} /> 保存修改</button></div>
              <div className="editable-tags">{selected.tags.map((tag) => <span key={tag}>{tag}<X size={13} /></span>)}<button>＋ 添加标签</button></div>
              <label><span>私人备注</span><textarea defaultValue={`${selected.name}沟通效率高，先准备结论和数据，再讨论实现细节。后续重点跟进试点范围和时间表。`} /></label>
            </section>
          )}
        </section>

        <footer className="workspace-footer">
          <span><ShieldCheck size={14} weight="fill" /> 本地加密存储</span>
          <span>消息 3,842 条 · 最近同步 今天 10:44</span>
        </footer>
      </main>

      {drawer && (
        <div className="drawer-backdrop" onMouseDown={() => setDrawer(null)}>
          <aside className="drawer" onMouseDown={(event) => event.stopPropagation()}>
            <div className="drawer-head"><div><span>{drawer.type === "search" ? "记录检索" : drawer.type === "avatar" ? "联系人身份" : "证据原文"}</span><h3>{drawer.title}</h3></div><button className="icon-button" onClick={() => setDrawer(null)}><X size={20} /></button></div>
            {drawer.type === "search" ? (
              <div className="drawer-body"><label className="search-field search-field--large"><MagnifyingGlass size={18} /><input autoFocus placeholder="输入项目、日期或一句话…" /></label><p className="helper-copy">支持语义搜索，例如“上次谈到离线部署是什么时候”。</p><div className="search-examples"><button onClick={() => notify("找到 8 条关于离线部署的记录")}>离线部署 <span>8 条</span></button><button onClick={() => notify("找到 3 条关于试点的记录")}>试点范围 <span>3 条</span></button><button onClick={() => notify("找到 5 条关于权限的记录")}>权限审计 <span>5 条</span></button></div></div>
            ) : drawer.type === "avatar" ? (
              <div className="drawer-body avatar-rule">
                <div className="avatar-rule-preview"><Avatar contact={selected} size="large" /><div><strong>{selected.name}</strong><span>当前无可用微信头像</span></div></div>
                <dl>
                  <div><dt>身份依据</dt><dd>微信内部账号标识，不依赖昵称或头像</dd></div>
                  <div><dt>显示名称</dt><dd>优先备注名，其次微信昵称；实名由你确认</dd></div>
                  <div><dt>头像更新</dt><dd>增量同步发现变化后自动替换本地缓存</dd></div>
                  <div><dt>缺省状态</dt><dd>没有头像时显示姓名首字，不需要手工上传</dd></div>
                </dl>
                <p className="helper-copy">头像只用于快速识别，不参与联系人匹配、搜索或关系记忆。</p>
              </div>
            ) : (
              <div className="drawer-body"><div className="message-context"><time>{drawer.date}</time><div className="message-bubble"><strong>{selected.name}</strong><p>{drawer.body}</p></div><div className="message-bubble message-bubble--mine"><strong>我</strong><p>收到，我整理完方案后发你，我们到时一起过。</p></div></div><button className="primary-button drawer-action" onClick={() => notify("已定位到本地聊天记录")}><PaperPlaneTilt size={16} /> 在本地记录中定位</button></div>
            )}
          </aside>
        </div>
      )}

      {toast && <div className="toast"><CheckCircle size={18} weight="fill" /> {toast}</div>}
    </div>
  );
}
