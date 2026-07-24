import { useEffect, useMemo, useState } from "react";
import { ArrowClockwise, ChatCircleDots, CheckCircle, CircleNotch, CloudCheck, Database, LinkSimple, MagnifyingGlass, UsersThree, WarningCircle } from "@phosphor-icons/react";
import { api, LocalApiError, type Contact, type ContactProfileHistoryEvent, type ContactProfileWrite, type Fact, type FactHistoryEvent, type FactKind, type FactWrite, type Message, type MessageContext, type SourceStatus, type SyncRun, type SyncSchedule } from "./api";

const nav = ["关系记忆", "待办事项", "全局搜索", "时间线", "标签管理"];
const factKindLabels: Record<FactKind, string> = {
  company: "公司",
  role: "角色",
  need: "需求",
  concern: "顾虑",
  commitment: "承诺",
};
const factHistoryLabels: Record<FactHistoryEvent["event_type"], string> = {
  created: "已创建",
  updated: "已编辑",
  deleted: "已删除",
};
const emptyFact = (): FactWrite => ({ kind: "company", content: "", message_ids: [] });
const emptyProfile = (): ContactProfileWrite => ({ remark_name: "", confirmed_real_name: "", company: "", role: "" });

function avatar(contact: Contact) {
  return contact.avatar_ref ? <img src={contact.avatar_ref} alt="" /> : <span>{contact.display_name.slice(0, 1)}</span>;
}

function formatMessageTime(value: string | null | undefined) {
  if (!value) return "暂无消息";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function contactSummary(contact: Contact) {
  return contact.effective_company ?? contact.company ?? contact.effective_role ?? contact.role ?? "已归档联系人";
}

function profileSnapshot(event: ContactProfileHistoryEvent) {
  const values = [event.user_remark_name, event.user_confirmed_real_name, event.user_company, event.user_role].filter(Boolean);
  return values.length ? values.join(" · ") : "已清除全部用户维护资料";
}

function syncResultCopy(run: SyncRun) {
  const counts = `新增 ${run.inserted_count} 条，重复 ${run.duplicate_count} 条。`;
  if (run.status === "completed") return `同步完成：${counts}`;
  if (run.status === "completed_with_warning") return `同步已完成，但数据质量警告（${run.error_code ?? "unknown"}）：${counts}`;
  return `同步未完成（${run.error_code ?? "unknown"}）。`;
}

function syncRunSummary(run: SyncRun) {
  if (run.status === "completed") return `已完成 · 新增 ${run.inserted_count} · 重复 ${run.duplicate_count}`;
  if (run.status === "completed_with_warning") return `需关注（${run.error_code ?? "unknown"}）· 新增 ${run.inserted_count} · 重复 ${run.duplicate_count}`;
  return `未完成（${run.error_code ?? "unknown"}）`;
}

export function App() {
  const [source, setSource] = useState<SourceStatus | null>(null);
  const [accountId, setAccountId] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [query, setQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<Message[]>([]);
  const [evidence, setEvidence] = useState<Message[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [factHistory, setFactHistory] = useState<FactHistoryEvent[]>([]);
  const [profileDraft, setProfileDraft] = useState<ContactProfileWrite | null>(null);
  const [profileHistory, setProfileHistory] = useState<ContactProfileHistoryEvent[]>([]);
  const [factDraft, setFactDraft] = useState<FactWrite | null>(null);
  const [editingFactId, setEditingFactId] = useState<string | null>(null);
  const [context, setContext] = useState<MessageContext | null>(null);
  const [schedule, setSchedule] = useState<SyncSchedule | null>(null);
  const [syncRuns, setSyncRuns] = useState<SyncRun[]>([]);
  const [activeTab, setActiveTab] = useState<"overview" | "evidence">("overview");
  const [loading, setLoading] = useState(true);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [factsLoading, setFactsLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [profileHistoryOpen, setProfileHistoryOpen] = useState(false);
  const [profileHistoryLoading, setProfileHistoryLoading] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [factSaving, setFactSaving] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState("");

  const accountSelectionRequired = source?.status === "account_selection_required";
  const sourceReady = source?.status === "ready";
  const sourceCanSync = sourceReady || accountSelectionRequired;
  const canSync = sourceCanSync && Boolean(accountId);
  const coverageWarning = source?.unknown_shards.length ? `数据范围不完整：有 ${source.unknown_shards.length} 个未纳入的数据分片。` : "";
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
    api.syncSchedule().then(setSchedule).catch(() => setNotice("自动同步状态读取失败。"));
  }, []);

  useEffect(() => {
    if (!accountId || !sourceCanSync) return;
    api.contacts(accountId, query).then((items) => {
      setContacts(items);
      setSelected((current) => items.find((item) => item.id === current?.id) ?? items[0] ?? null);
    }).catch(() => setNotice("联系人读取失败。"));
  }, [accountId, query, sourceCanSync]);

  useEffect(() => {
    if (!accountId) {
      setSyncRuns([]);
      return;
    }
    let active = true;
    api.syncRuns(accountId).then((items) => active && setSyncRuns(items)).catch(() => active && setNotice("同步记录读取失败。"));
    return () => { active = false; };
  }, [accountId]);

  useEffect(() => {
    if (!selected || !accountId) {
      setEvidence([]);
      return;
    }
    let active = true;
    setEvidenceLoading(true);
    api.contactMessages(selected.id, accountId)
      .then((items) => active && setEvidence(items))
      .catch(() => active && setNotice("聊天证据读取失败。"))
      .finally(() => active && setEvidenceLoading(false));
    return () => { active = false; };
  }, [accountId, selected?.id]);

  useEffect(() => {
    if (!selected || !accountId) {
      setFacts([]);
      return;
    }
    let active = true;
    setFactsLoading(true);
    api.facts(selected.id, accountId)
      .then((items) => active && setFacts(items))
      .catch(() => active && setNotice("已确认事实读取失败。"))
      .finally(() => active && setFactsLoading(false));
    return () => { active = false; };
  }, [accountId, selected?.id]);

  useEffect(() => {
    if (!historyOpen || !selected || !accountId) return;
    let active = true;
    setHistoryLoading(true);
    api.factHistory(selected.id, accountId)
      .then((items) => active && setFactHistory(items))
      .catch(() => active && setNotice("事实历史读取失败。"))
      .finally(() => active && setHistoryLoading(false));
    return () => { active = false; };
  }, [accountId, historyOpen, selected?.id]);

  useEffect(() => {
    if (!profileHistoryOpen || !selected || !accountId) return;
    let active = true;
    setProfileHistoryLoading(true);
    api.contactProfileHistory(selected.id, accountId)
      .then((items) => active && setProfileHistory(items))
      .catch(() => active && setNotice("联系人资料历史读取失败。"))
      .finally(() => active && setProfileHistoryLoading(false));
    return () => { active = false; };
  }, [accountId, profileHistoryOpen, selected?.id]);

  async function sync(mode: "initial" | "incremental") {
    if (!canSync) return;
    setSyncing(true);
    try {
      const run = await api.sync(accountId, mode);
      setNotice(syncResultCopy(run));
      setSyncRuns((current) => [run, ...current.filter((item) => item.id !== run.id)].slice(0, 20));
      if (run.status === "failed") return;
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
    catch { setNotice("搜索失败；请先完成首次归档。"); }
  }

  async function showContext(message: Message) {
    setContextLoading(true);
    try { setContext(await api.messageContext(message.id)); }
    catch { setNotice("消息上下文读取失败。"); }
    finally { setContextLoading(false); }
  }

  async function refreshFactHistory() {
    if (!historyOpen || !selected || !accountId) return;
    setHistoryLoading(true);
    try { setFactHistory(await api.factHistory(selected.id, accountId)); }
    catch { setNotice("事实历史读取失败。"); }
    finally { setHistoryLoading(false); }
  }

  async function refreshProfileHistory() {
    if (!profileHistoryOpen || !selected || !accountId) return;
    setProfileHistoryLoading(true);
    try { setProfileHistory(await api.contactProfileHistory(selected.id, accountId)); }
    catch { setNotice("联系人资料历史读取失败。"); }
    finally { setProfileHistoryLoading(false); }
  }

  function beginProfileEdit() {
    if (!selected) return;
    setProfileDraft({ remark_name: selected.user_remark_name ?? "", confirmed_real_name: selected.user_confirmed_real_name ?? "", company: selected.user_company ?? "", role: selected.user_role ?? "" });
  }

  function replaceContact(updated: Contact) {
    setContacts((current) => current.map((item) => item.id === updated.id ? updated : item));
    setSelected(updated);
  }

  async function saveProfile(profile: ContactProfileWrite) {
    if (!selected || !accountId) return;
    setProfileSaving(true);
    try {
      const updated = await api.updateContactProfile(selected.id, accountId, profile);
      replaceContact(updated);
      setProfileDraft(null);
      await refreshProfileHistory();
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `联系人资料未保存（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查账号。"}` : "联系人资料未保存，请检查本地 API 状态。");
    } finally { setProfileSaving(false); }
  }

  function selectContact(contact: Contact) {
    setSelected(contact);
    setContext(null);
    setFactDraft(null);
    setEditingFactId(null);
    setFactHistory([]);
    setHistoryOpen(false);
    setProfileDraft(null);
    setProfileHistory([]);
    setProfileHistoryOpen(false);
  }

  function beginFact(message?: Message) {
    setActiveTab("overview");
    setEditingFactId(null);
    setFactDraft({ ...emptyFact(), message_ids: message ? [message.id] : [] });
  }

  function editFact(fact: Fact) {
    setEditingFactId(fact.id);
    setFactDraft({ kind: fact.kind, content: fact.content, message_ids: fact.evidence.map((item) => item.id) });
  }

  function toggleFactEvidence(messageId: string) {
    setFactDraft((current) => {
      if (!current) return current;
      const included = current.message_ids.includes(messageId);
      return { ...current, message_ids: included ? current.message_ids.filter((id) => id !== messageId) : [...current.message_ids, messageId] };
    });
  }

  async function saveFact() {
    if (!selected || !accountId || !factDraft || !factDraft.content.trim()) return;
    setFactSaving(true);
    try {
      const saved = editingFactId
        ? await api.updateFact(editingFactId, accountId, { ...factDraft, content: factDraft.content.trim() })
        : await api.createFact(selected.id, accountId, { ...factDraft, content: factDraft.content.trim() });
      setFacts((current) => editingFactId ? current.map((item) => item.id === saved.id ? saved : item) : [saved, ...current]);
      setFactDraft(null);
      setEditingFactId(null);
      await refreshFactHistory();
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `事实未保存（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查原文证据。"}` : "事实未保存，请检查本地 API 状态。");
    } finally { setFactSaving(false); }
  }

  async function removeFact(factId: string) {
    if (!accountId) return;
    try {
      await api.deleteFact(factId, accountId);
      setFacts((current) => current.filter((item) => item.id !== factId));
      await refreshFactHistory();
      if (editingFactId === factId) {
        setFactDraft(null);
        setEditingFactId(null);
      }
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `事实未删除（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查账号。"}` : "事实未删除，请检查本地 API 状态。");
    }
  }

  const messageRows = (items: Message[], emptyCopy: string, canUseForFact = false) => {
    if (!items.length && !evidenceLoading) return <p className="empty-message">{emptyCopy}</p>;
    return items.map((item) => <article className="message-row" key={item.id}>
      <div><strong>{item.conversation_name}</strong><span>{item.sender_display_name} · {item.conversation_type === "group" ? "群聊" : "私聊"} · {item.message_type}</span></div>
      <p>{item.text_content}</p>
      <footer><time>{formatMessageTime(item.sent_at)}</time><span><button className="link" onClick={() => showContext(item)}>查看上下文</button>{canUseForFact && <button className="link" onClick={() => beginFact(item)}>用于新事实</button>}</span></footer>
    </article>);
  };

  return <div className="app-shell">
    <aside className="nav">
      <div><div className="brand"><span><LinkSimple weight="bold" /></span>微信关系记忆</div><nav>{nav.map((item, index) => <button className={index === 0 ? "active" : ""} key={item}><UsersThree size={18} />{item}</button>)}</nav></div>
      <div className="local"><Database size={17} /><span>本地关系工作台<small>数据仅存本机</small></span></div>
    </aside>
    <section className="contacts">
      <label className="search"><MagnifyingGlass size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索联系人、公司或角色" /></label>
      <div className="pane-title"><strong>全部联系人</strong><span>{contacts.length}</span></div>
      <p className="sort-hint">按最后消息时间排序，最新在前</p>
      <div className="contact-list">{contacts.map((contact) => <button key={contact.id} className={selected?.id === contact.id ? "selected" : ""} onClick={() => selectContact(contact)}><i>{avatar(contact)}</i><span><strong>{contact.display_name}</strong><small>{contactSummary(contact)}</small><time>最后消息：{formatMessageTime(contact.last_message_at)}</time></span></button>)}{!loading && !contacts.length && <p className="empty">首次归档完成后，联系人会显示在这里。</p>}</div>
    </section>
    <main>
      <header className="status"><div className="source-status"><span className={sourceReady ? "ok" : "warn"}>{sourceReady ? <CloudCheck weight="fill" /> : <WarningCircle weight="fill" />}{statusCopy}</span>{coverageWarning && <span className="coverage-warning"><WarningCircle weight="fill" />{coverageWarning}</span>}</div><button disabled={!canSync || syncing} onClick={() => sync("incremental")}>{syncing ? <CircleNotch className="spin" /> : <ArrowClockwise />}立即同步</button></header>
      <section className="hero"><div className="profile-avatar">{selected ? avatar(selected) : <UsersThree />}</div><div><h1>{selected?.display_name ?? "开始建立本地关系记忆"}</h1><p>{selected ? contactSummary(selected) : accountSelectionRequired ? "请先明确选择本地账号；系统不会按目录、昵称或头像猜测。" : "先选择一个已确认的数据源账号，再开始首次归档。"}</p><div className="chips"><span>本地优先</span><span>原文可追溯</span><span>身份稳定</span></div></div><div className="hero-actions"><button className="secondary" onClick={() => sync("initial")} disabled={!canSync || syncing}>首次归档</button><button className="primary" onClick={search}><MagnifyingGlass />搜索聊天记录</button></div></section>
      <div className="tabs"><button className={activeTab === "overview" ? "active" : ""} aria-selected={activeTab === "overview"} onClick={() => setActiveTab("overview")}>关系总览</button><button className={activeTab === "evidence" ? "active" : ""} aria-selected={activeTab === "evidence"} onClick={() => setActiveTab("evidence")}>聊天证据</button><button disabled>待办事项</button><button disabled>标签与备注</button></div>
      <div className="content">
        {activeTab === "overview" && <>
          <section className="card profile-card"><header className="card-heading"><h2><UsersThree weight="fill" />联系人档案</h2><span><button className="link" disabled={!selected} onClick={() => setProfileHistoryOpen((current) => !current)}>资料历史</button><button className="link" disabled={!selected} onClick={beginProfileEdit}>编辑资料</button></span></header>{selected ? <><p>用户维护资料只保存在本机，不会被同步覆盖，也不会由聊天自动推断。</p><dl className="profile-fields"><div><dt>备注</dt><dd>{selected.user_remark_name ?? selected.remark_name ?? "暂无"}<small>{selected.user_remark_name ? "用户维护" : "采集资料"}</small></dd></div><div><dt>确认实名</dt><dd>{selected.user_confirmed_real_name ?? selected.confirmed_real_name ?? "暂无"}<small>{selected.user_confirmed_real_name ? "用户维护" : "采集资料"}</small></dd></div><div><dt>公司</dt><dd>{selected.effective_company ?? selected.company ?? "暂无"}<small>{selected.user_company ? "用户维护" : "采集资料"}</small></dd></div><div><dt>角色</dt><dd>{selected.effective_role ?? selected.role ?? "暂无"}<small>{selected.user_role ? "用户维护" : "采集资料"}</small></dd></div></dl>{profileDraft && <form className="profile-editor" onSubmit={(event) => { event.preventDefault(); void saveProfile(profileDraft); }}><label>备注<input value={profileDraft.remark_name ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, remark_name: event.target.value })} maxLength={255} /></label><label>确认实名<input value={profileDraft.confirmed_real_name ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, confirmed_real_name: event.target.value })} maxLength={255} /></label><label>公司<input value={profileDraft.company ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, company: event.target.value })} maxLength={255} /></label><label>角色<input value={profileDraft.role ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, role: event.target.value })} maxLength={255} /></label><footer><button type="button" className="link" onClick={() => setProfileDraft(null)}>取消</button><button className="primary" type="submit" disabled={profileSaving}>{profileSaving ? "保存中…" : "保存资料"}</button></footer></form>}{!profileDraft && <button className="link clear-profile" disabled={profileSaving || ![selected.user_remark_name, selected.user_confirmed_real_name, selected.user_company, selected.user_role].some(Boolean)} onClick={() => void saveProfile(emptyProfile())}>清除用户维护</button>}{profileHistoryOpen && <section className="profile-history"><h3>资料历史</h3>{profileHistoryLoading ? <p className="empty-message">正在读取资料历史…</p> : !profileHistory.length ? <p className="empty-message">当前联系人尚无资料操作历史。</p> : <div className="profile-history-list">{profileHistory.map((event) => <article key={event.id}><strong>{profileSnapshot(event)}</strong><time>{formatMessageTime(event.occurred_at)}</time><span>用户操作记录</span></article>)}</div>}</section>}</> : <p className="empty-message">选择联系人后可维护本地资料。</p>}</section>
          <section className="card confirmed"><header className="card-heading"><h2><CheckCircle weight="fill" />已确认的事实</h2><span><button className="link" disabled={!selected} onClick={() => setHistoryOpen((current) => !current)}>事实历史</button><button className="link" disabled={!selected} onClick={() => beginFact()}>添加事实</button></span></header><p>仅由用户手动记录或确认；系统不会从聊天自动推断事实。</p>{factDraft && <form className="fact-editor" onSubmit={(event) => { event.preventDefault(); void saveFact(); }}><label>类型<select value={factDraft.kind} onChange={(event) => setFactDraft({ ...factDraft, kind: event.target.value as FactKind })}>{Object.entries(factKindLabels).map(([kind, label]) => <option value={kind} key={kind}>{label}</option>)}</select></label><label>内容<textarea value={factDraft.content} onChange={(event) => setFactDraft({ ...factDraft, content: event.target.value })} placeholder="输入用户确认的内容" maxLength={2000} required /></label><fieldset><legend>原文证据（可选）</legend>{evidence.length ? evidence.map((message) => <label className="fact-evidence-choice" key={message.id}><input type="checkbox" checked={factDraft.message_ids.includes(message.id)} onChange={() => toggleFactEvidence(message.id)} />{message.conversation_name} · {formatMessageTime(message.sent_at)} · {message.text_content}</label>) : <p>无原文证据时将标记为“用户手动记录”。</p>}</fieldset><footer><button type="button" className="link" onClick={() => { setFactDraft(null); setEditingFactId(null); }}>取消</button><button className="primary" type="submit" disabled={factSaving || !factDraft.content.trim()}>{factSaving ? "保存中…" : editingFactId ? "保存修改" : "保存事实"}</button></footer></form>}{factsLoading ? <p className="empty-message">正在读取已确认事实…</p> : !facts.length ? <p className="empty-message">尚无已确认事实。可手动记录，或从聊天证据添加原文关联。</p> : <div className="fact-list">{facts.map((fact) => <article className="fact-row" key={fact.id}><div><strong>{factKindLabels[fact.kind]}</strong><time>更新于 {formatMessageTime(fact.updated_at)}</time></div><p>{fact.content}</p><footer>{fact.evidence.length ? <button className="link" onClick={() => showContext(fact.evidence[0])}>原文证据 {fact.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span><button className="link" onClick={() => editFact(fact)}>编辑</button><button className="link danger" onClick={() => void removeFact(fact.id)}>删除</button></span></footer></article>)}</div>}{historyOpen && <section className="fact-history"><h3>事实历史</h3>{historyLoading ? <p className="empty-message">正在读取事实历史…</p> : !factHistory.length ? <p className="empty-message">当前联系人尚无事实操作历史。</p> : <div className="fact-list">{factHistory.map((event) => <article className="fact-row history-row" key={event.id}><div><strong>{factHistoryLabels[event.event_type]} · {factKindLabels[event.kind]}</strong><time>{formatMessageTime(event.occurred_at)}</time></div><p>{event.content}</p><footer>{event.evidence.length ? <button className="link" onClick={() => showContext(event.evidence[0])}>原文证据 {event.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span className="history-source">用户操作记录</span></footer></article>)}</div>}</section>}</section>
          <section className="card ai"><h2><ChatCircleDots weight="fill" />原文搜索</h2><div className="search-results"><label className="inline-search"><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && search()} placeholder="输入关键词后按 Enter" /><button className="link" onClick={search}>搜索</button></label>{messageRows(results, "输入关键词后可查看原文命中与上下文。")}</div></section>
        </>}
        {activeTab === "evidence" && <section className="card evidence-card"><h2><ChatCircleDots weight="fill" />{selected ? `${selected.display_name} 的聊天证据` : "聊天证据"}</h2><p>包含与该联系人的私聊，以及该联系人在已归档群聊中的发言。</p><div className="evidence-list">{evidenceLoading ? <p className="empty-message">正在读取聊天证据…</p> : messageRows(evidence, "当前联系人尚无可追溯聊天证据。", true)}</div></section>}
        {context && <section className="card context-card"><h2>消息上下文</h2><div className="context-list">{context.messages.map((item) => <article className={item.id === context.anchor_id ? "context-message anchor" : "context-message"} key={item.id}><strong>{item.sender_display_name} · {formatMessageTime(item.sent_at)}</strong><p>{item.text_content}</p></article>)}</div></section>}
        <section className="card needs"><h2>同步状态与下一步</h2>{source && (accountSelectionRequired || source.accounts.length > 1) && <label className="account-picker">{accountSelectionRequired ? "请选择本地账号" : "当前本地账号"}<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="" disabled>请选择一个已探测账号</option>{source.accounts.map((account) => <option value={account.id} key={account.id}>{account.display_name}</option>)}</select></label>}{schedule && <div className="schedule-state"><strong>{schedule.enabled ? `自动增量同步已启用（每 ${Math.round(schedule.interval_seconds / 60)} 分钟）` : "自动增量同步未启用"}</strong><span>{schedule.enabled ? "仅对已首次归档的合成账号生效。" : schedule.reason}</span></div>}{syncRuns.length > 0 && <div className="recent-sync"><strong>最近同步</strong>{syncRuns.slice(0, 3).map((run) => <span key={run.id}>{syncRunSummary(run)}</span>)}</div>}<p>{contextLoading ? "正在读取消息上下文…" : notice || "查看聊天证据可核对联系人消息来源与前后文。真实微信连接仍需通过只读 Go/No-Go。"}</p></section>
      </div>
    </main>
  </div>;
}
