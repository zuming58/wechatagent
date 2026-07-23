import { useEffect, useMemo, useState } from "react";
import { ArrowClockwise, ChatCircleDots, CheckCircle, CircleNotch, CloudCheck, Database, LinkSimple, MagnifyingGlass, UsersThree, WarningCircle } from "@phosphor-icons/react";
import { api, LocalApiError, type Contact, type Message, type SourceStatus } from "./api";

const nav = ["关系记忆", "待办事项", "全局搜索", "时间线", "标签管理"];

function avatar(contact: Contact) {
  return contact.avatar_ref ? <img src={contact.avatar_ref} alt="" /> : <span>{contact.display_name.slice(0, 1)}</span>;
}

export function App() {
  const [source, setSource] = useState<SourceStatus | null>(null);
  const [accountId, setAccountId] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [query, setQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState("");

  const accountSelectionRequired = source?.status === "account_selection_required";
  const sourceReady = source?.status === "ready";
  const sourceCanSync = sourceReady || accountSelectionRequired;
  const canSync = sourceCanSync && Boolean(accountId);
  const statusCopy = useMemo(() => {
    if (!source) return "正在检查本地数据源…";
    if (sourceReady) return "数据源已就绪，仅在本机处理";
    if (accountSelectionRequired) return "请选择本地账号后再开始同步";
    return source.reason ?? "数据源尚未就绪";
  }, [source, sourceReady, accountSelectionRequired]);

  useEffect(() => {
    api.sourceStatus().then((payload) => {
      setSource(payload);
      if (payload.status === "account_selection_required") {
        setAccountId("");
      } else {
        const preferred = payload.accounts.find((item) => item.selected) ?? payload.accounts[0];
        setAccountId(preferred?.id ?? "");
      }
    }).catch(() => setNotice("本地 API 未启动。请先启动 backend 服务。"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!accountId || !sourceCanSync) return;
    api.contacts(accountId, query).then((items) => {
      setContacts(items);
      setSelected((current) => items.find((item) => item.id === current?.id) ?? items[0] ?? null);
    }).catch(() => setNotice("联系人读取失败。"));
  }, [accountId, query, sourceCanSync]);

  async function sync(mode: "initial" | "incremental") {
    if (!canSync) return;
    setSyncing(true);
    try {
      const run = await api.sync(accountId, mode);
      setNotice(`同步完成：新增 ${run.inserted_count} 条，重复 ${run.duplicate_count} 条。`);
      const refreshed = await api.contacts(accountId, query);
      setContacts(refreshed);
      setSelected((current) => refreshed.find((item) => item.id === current?.id) ?? refreshed[0] ?? null);
    } catch (error) {
      if (error instanceof LocalApiError) {
        setNotice(`同步未完成（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查数据源状态。"}`);
      } else {
        setNotice("同步未完成，请查看数据源状态。");
      }
    } finally { setSyncing(false); }
  }

  async function search() {
    if (!accountId || !searchQuery.trim()) return;
    try { setResults(await api.search(accountId, searchQuery.trim())); }
    catch { setNotice("搜索失败；请先完成首次归档。" ); }
  }

  return <div className="app-shell">
    <aside className="nav">
      <div><div className="brand"><span><LinkSimple weight="bold" /></span>微信关系记忆</div><nav>{nav.map((item, index) => <button className={index === 0 ? "active" : ""} key={item}><UsersThree size={18} />{item}</button>)}</nav></div>
      <div className="local"><Database size={17} /><span>本地关系工作台<small>数据仅存本机</small></span></div>
    </aside>
    <section className="contacts">
      <label className="search"><MagnifyingGlass size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索联系人、公司或角色" /></label>
      <div className="pane-title"><strong>全部联系人</strong><span>{contacts.length}</span></div>
      <div className="contact-list">{contacts.map((contact) => <button key={contact.id} className={selected?.id === contact.id ? "selected" : ""} onClick={() => setSelected(contact)}><i>{avatar(contact)}</i><span><strong>{contact.display_name}</strong><small>{contact.company || contact.role || "本地联系人"}</small></span></button>)}{!loading && !contacts.length && <p className="empty">首次归档完成后，联系人会显示在这里。</p>}</div>
    </section>
    <main>
      <header className="status"><span className={sourceReady ? "ok" : "warn"}>{sourceReady ? <CloudCheck weight="fill" /> : <WarningCircle weight="fill" />}{statusCopy}</span><button disabled={!canSync || syncing} onClick={() => sync("incremental")}>{syncing ? <CircleNotch className="spin" /> : <ArrowClockwise />}立即同步</button></header>
      <section className="hero"><div className="profile-avatar">{selected ? avatar(selected) : <UsersThree />}</div><div><h1>{selected?.display_name ?? "开始建立本地关系记忆"}</h1><p>{selected?.company || selected?.role || (accountSelectionRequired ? "请先明确选择本地账号；系统不会按目录、昵称或头像猜测。" : "先选择一个已确认的数据源账号，再开始首次归档。")}</p><div className="chips"><span>本地优先</span><span>原文可追溯</span><span>身份稳定</span></div></div><div className="hero-actions"><button className="secondary" onClick={() => sync("initial")} disabled={!canSync || syncing}>首次归档</button><button className="primary" onClick={search}><MagnifyingGlass />搜索聊天记录</button></div></section>
      <div className="tabs"><button className="active">关系总览</button><button>聊天证据</button><button>待办事项</button><button>标签与备注</button></div>
      <div className="content"><section className="card confirmed"><h2><CheckCircle weight="fill" />已确认的事实</h2><p>真实聊天同步后，在这里保存由你确认的关系事实；每一条都会保留原文上下文入口。</p><ul><li>联系人身份由账号标识与稳定内部标识绑定。</li><li>头像变化仅更新缓存，不会产生新联系人。</li><li>原始消息落库成功后才推进同步水位。</li></ul></section><section className="card ai"><h2><ChatCircleDots weight="fill" />原文搜索</h2><div className="search-results"><label className="inline-search"><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && search()} placeholder="输入关键词后按 Enter" /><button className="link" onClick={search}>搜索</button></label>{results.map((item) => <article key={item.id}><strong>{item.conversation_name} · {item.sender_display_name}</strong><p>{item.text_content}</p><small>{new Date(item.sent_at).toLocaleString("zh-CN")}</small></article>)}</div></section><section className="card needs"><h2>同步状态与下一步</h2>{source && (accountSelectionRequired || source.accounts.length > 1) && <label className="account-picker">{accountSelectionRequired ? "请选择本地账号" : "当前本地账号"}<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="" disabled>请选择一个已探测账号</option>{source.accounts.map((account) => <option value={account.id} key={account.id}>{account.display_name}</option>)}</select></label>}<p>{notice || "使用合成数据完成一次归档后，可验证联系人、搜索与上下文。真实微信连接仍需通过只读 Go/No-Go。"}</p></section></div>
    </main>
  </div>;
}
