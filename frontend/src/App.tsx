import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwise, ChatCircleDots, CheckCircle, CircleNotch, CloudCheck, Database, LinkSimple, MagnifyingGlass, UsersThree, WarningCircle } from "@phosphor-icons/react";
import { api, LocalApiError, type AccountDeletionRequest, type ActionItem, type ActionItemHistoryEvent, type ActionItemWrite, type BackupManifest, type Contact, type ContactProfileHistoryEvent, type ContactProfileWrite, type Fact, type FactHistoryEvent, type FactKind, type FactWrite, type FtsIndexStatus, type KnowledgeCard, type KnowledgeCardHistoryEvent, type KnowledgeCardType, type KnowledgeCardWrite, type Message, type MessageContext, type MessageSearchFilters, type PrivacySettings, type SourceStatus, type StorageStatus, type SyncRun, type SyncSchedule, type Tag, type TagLink, type TagTargetType, type TagWrite, type TimelineEvent, type TimelineKind } from "./api";
import "./data-management.css";
import "./privacy.css";

const nav = ["关系记忆", "待办事项", "全局搜索", "时间线", "标签管理", "设置"];
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
const timelineKindLabels: Record<TimelineKind, string> = {
  message: "原文消息",
  fact: "已确认事实",
  profile: "联系人资料",
  knowledge_card: "本地知识卡",
  action_item: "手动待办",
};
const emptyFact = (): FactWrite => ({ kind: "company", content: "", message_ids: [] });
const emptyProfile = (): ContactProfileWrite => ({ remark_name: "", confirmed_real_name: "", company: "", role: "" });
const emptyKnowledgeCard = (): KnowledgeCardWrite => ({ card_type: "note", title: "", content: "", message_ids: [] });
const emptyActionItem = (): ActionItemWrite => ({ content: "", status: "open", due_at: null, message_ids: [] });
const emptyTag = (): TagWrite => ({ name: "", color: "#1677ff" });

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

function syncResultCopy(run: SyncRun, mode: "initial" | "incremental") {
  const action = mode === "initial" ? "首次归档" : "立即同步";
  const counts = run.inserted_count === 0
    ? `没有新消息，已跳过重复 ${run.duplicate_count} 条。`
    : `新增 ${run.inserted_count} 条，已跳过重复 ${run.duplicate_count} 条。`;
  if (run.status === "completed") return `${action}完成：${counts}`;
  if (run.status === "completed_with_warning") return `${action}已完成，但数据质量警告（${run.error_code ?? "unknown"}）：${counts}`;
  return `${action}未完成（${run.error_code ?? "unknown"}）。`;
}

function syncRunSummary(run: SyncRun) {
  if (run.status === "completed") return `已完成 · 新增 ${run.inserted_count} · 重复 ${run.duplicate_count}`;
  if (run.status === "completed_with_warning") return `需关注（${run.error_code ?? "unknown"}）· 新增 ${run.inserted_count} · 重复 ${run.duplicate_count}`;
  return `未完成（${run.error_code ?? "unknown"}）`;
}

export function App() {
  const [source, setSource] = useState<SourceStatus | null>(null);
  const [privacy, setPrivacy] = useState<PrivacySettings | null>(null);
  const [privacyAcknowledgement, setPrivacyAcknowledgement] = useState(false);
  const [privacySaving, setPrivacySaving] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [query, setQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFilters, setSearchFilters] = useState<MessageSearchFilters>({});
  const [results, setResults] = useState<Message[]>([]);
  const [searchState, setSearchState] = useState<"idle" | "loading" | "complete" | "error">("idle");
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
  const [knowledgeCards, setKnowledgeCards] = useState<KnowledgeCard[]>([]);
  const [knowledgeDraft, setKnowledgeDraft] = useState<KnowledgeCardWrite | null>(null);
  const [editingKnowledgeCardId, setEditingKnowledgeCardId] = useState<string | null>(null);
  const [knowledgeHistory, setKnowledgeHistory] = useState<KnowledgeCardHistoryEvent[]>([]);
  const [knowledgeHistoryCardId, setKnowledgeHistoryCardId] = useState<string | null>(null);
  const [storage, setStorage] = useState<StorageStatus | null>(null);
  const [backupManifest, setBackupManifest] = useState<BackupManifest | null>(null);
  const [ftsIndexStatus, setFtsIndexStatus] = useState<FtsIndexStatus | null>(null);
  const [ftsRebuilding, setFtsRebuilding] = useState(false);
  const [deletionRequest, setDeletionRequest] = useState<AccountDeletionRequest | null>(null);
  const [deletionConfirmation, setDeletionConfirmation] = useState("");
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [actionDraft, setActionDraft] = useState<ActionItemWrite | null>(null);
  const [actionHistory, setActionHistory] = useState<ActionItemHistoryEvent[]>([]);
  const [actionHistoryItemId, setActionHistoryItemId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<"relationships" | "actions" | "search" | "timeline" | "tags" | "settings">("relationships");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineKinds, setTimelineKinds] = useState<TimelineKind[]>(["message", "fact", "profile", "knowledge_card", "action_item"]);
  const [timelineContactOnly, setTimelineContactOnly] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagDraft, setTagDraft] = useState<TagWrite | null>(null);
  const [editingTagId, setEditingTagId] = useState<string | null>(null);
  const [tagAssignmentId, setTagAssignmentId] = useState("");
  const [tagTargetType, setTagTargetType] = useState<TagTargetType>("contact");
  const [tagTargetId, setTagTargetId] = useState("");
  const [tagLinks, setTagLinks] = useState<TagLink[]>([]);
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
  const contextRef = useRef<HTMLElement | null>(null);

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
    let active = true;
    api.privacySettings().then((payload) => {
      if (!active) return;
      setPrivacy(payload);
      setPrivacyAcknowledgement(payload.local_processing_acknowledged);
      if (!payload.local_processing_acknowledged) setLoading(false);
    }).catch(() => {
      if (active) {
        setNotice("本地安全设置读取失败。请确认本地 API 已启动。");
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!privacy?.local_processing_acknowledged) return;
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
  }, [privacy?.local_processing_acknowledged]);

  useEffect(() => {
    if (!privacy?.local_processing_acknowledged) return;
    Promise.resolve(api.syncSchedule()).then((payload) => payload && setSchedule(payload)).catch(() => setNotice("自动同步状态读取失败。"));
  }, [privacy?.local_processing_acknowledged]);

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
    Promise.resolve(api.syncRuns(accountId)).then((items) => active && setSyncRuns(items ?? [])).catch(() => active && setNotice("同步记录读取失败。"));
    return () => { active = false; };
  }, [accountId]);

  useEffect(() => {
    if (!accountId) { setActionItems([]); setActionHistory([]); setActionHistoryItemId(null); return; }
    Promise.resolve(api.actionItems(accountId)).then((items) => items && setActionItems(items)).catch(() => setNotice("待办读取失败。"));
  }, [accountId]);

  useEffect(() => {
    if (!accountId) { setStorage(null); setBackupManifest(null); setFtsIndexStatus(null); setDeletionRequest(null); setDeletionConfirmation(""); return; }
    Promise.resolve(api.storageStatus(accountId)).then((value) => value && setStorage(value)).catch(() => setNotice("存储状态读取失败。"));
    Promise.resolve(api.ftsIndexStatus(accountId)).then((value) => value && setFtsIndexStatus(value)).catch(() => setNotice("全文索引状态读取失败。"));
  }, [accountId]);

  useEffect(() => {
    if (!accountId) { setKnowledgeCards([]); return; }
    let active = true;
    Promise.resolve(api.knowledgeCards(accountId)).then((items) => active && setKnowledgeCards(items ?? [])).catch(() => active && setNotice("知识卡读取失败。"));
    return () => { active = false; };
  }, [accountId]);

  useEffect(() => {
    if (!accountId) { setTags([]); setTagAssignmentId(""); return; }
    api.tags(accountId).then((items) => {
      setTags(items);
      setTagAssignmentId((current) => items.some((tag) => tag.id === current) ? current : items[0]?.id ?? "");
    }).catch(() => setNotice("标签读取失败。"));
  }, [accountId]);

  useEffect(() => {
    if (workspace !== "tags" || !accountId || !tagTargetId) { setTagLinks([]); return; }
    let active = true;
    api.tagLinks(accountId, tagTargetType, tagTargetId).then((items) => active && setTagLinks(items)).catch(() => active && setNotice("标签关联读取失败。"));
    return () => { active = false; };
  }, [accountId, tagTargetId, tagTargetType, workspace]);

  useEffect(() => {
    if (workspace !== "timeline" || !accountId) {
      if (!accountId) setTimeline([]);
      return;
    }
    let active = true;
    setTimelineLoading(true);
    api.timeline(accountId, { kinds: timelineKinds, contact_id: timelineContactOnly ? selected?.id : undefined })
      .then((items) => active && setTimeline(items))
      .catch(() => active && setNotice("时间线读取失败。"))
      .finally(() => active && setTimelineLoading(false));
    return () => { active = false; };
  }, [accountId, selected?.id, timelineContactOnly, timelineKinds, workspace]);

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
    if (!context) return;
    contextRef.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [context]);

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
      setNotice(syncResultCopy(run, mode));
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
    setSearchState("loading");
    setResults([]);
    try {
      setResults(await api.search(accountId, searchQuery.trim(), searchFilters));
      setSearchState("complete");
    } catch {
      setSearchState("error");
      setNotice("搜索失败；请先完成首次归档。");
    }
  }

  async function showContext(message: Message) {
    if (!accountId) return;
    setContextLoading(true);
    try { setContext(await api.messageContext(message.id, accountId)); }
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
    if (tagTargetType === "contact") setTagTargetId(contact.id);
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
    setWorkspace("relationships");
    setActiveTab("overview");
    setEditingFactId(null);
    setFactDraft({ ...emptyFact(), message_ids: message ? [message.id] : [] });
  }

  function beginActionItem(message?: Message) {
    setWorkspace("actions");
    setActionDraft({ ...emptyActionItem(), message_ids: message ? [message.id] : [] });
  }

  function openGlobalSearch() {
    setWorkspace("search");
    setSearchFilters((current) => ({ ...current, contact_id: undefined }));
  }

  function openTimeline() {
    setWorkspace("timeline");
  }

  function openTags() {
    setWorkspace("tags");
    setTagTargetType("contact");
    setTagTargetId(selected?.id ?? contacts[0]?.id ?? "");
  }

  function toggleTimelineKind(kind: TimelineKind) {
    setTimelineKinds((current) => current.includes(kind) ? (current.length === 1 ? current : current.filter((value) => value !== kind)) : [...current, kind]);
  }

  function tagTargetOptions(type: TagTargetType) {
    if (type === "contact") return contacts.map((item) => ({ id: item.id, label: item.display_name }));
    if (type === "fact") return facts.map((item) => ({ id: item.id, label: `${factKindLabels[item.kind]} · ${item.content.slice(0, 36)}` }));
    if (type === "knowledge_card") return knowledgeCards.map((item) => ({ id: item.id, label: item.title }));
    return actionItems.map((item) => ({ id: item.id, label: item.content.slice(0, 42) }));
  }

  function changeTagTargetType(type: TagTargetType) {
    const options = tagTargetOptions(type);
    setTagTargetType(type);
    setTagTargetId(options[0]?.id ?? "");
  }

  async function saveTag() {
    if (!accountId || !tagDraft?.name.trim()) return;
    try {
      const payload = { name: tagDraft.name.trim(), color: tagDraft.color };
      const saved = editingTagId ? await api.updateTag(editingTagId, accountId, payload) : await api.createTag(accountId, payload);
      setTags((current) => editingTagId ? current.map((item) => item.id === saved.id ? saved : item) : [...current, saved].sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN")));
      setTagAssignmentId((current) => current || saved.id);
      setTagDraft(null);
      setEditingTagId(null);
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `标签未保存（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查标签名称。"}` : "标签未保存。 ");
    }
  }

  async function removeTag(tagId: string) {
    if (!accountId) return;
    try {
      await api.deleteTag(tagId, accountId);
      const remaining = tags.filter((tag) => tag.id !== tagId);
      setTags(remaining);
      if (tagAssignmentId === tagId) setTagAssignmentId(remaining[0]?.id ?? "");
      setTagLinks((current) => current.filter((link) => link.tag.id !== tagId));
      if (editingTagId === tagId) { setEditingTagId(null); setTagDraft(null); }
    } catch { setNotice("标签未删除。 "); }
  }

  async function addTagLink() {
    if (!accountId || !tagAssignmentId || !tagTargetId) return;
    try {
      const link = await api.createTagLink(accountId, tagAssignmentId, tagTargetType, tagTargetId);
      setTagLinks((current) => current.some((item) => item.id === link.id) ? current : [...current, link]);
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `标签关联未保存（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查目标对象。"}` : "标签关联未保存。 ");
    }
  }

  async function removeTagLink(tagId: string) {
    if (!accountId || !tagTargetId) return;
    try {
      await api.deleteTagLink(tagId, accountId, tagTargetType, tagTargetId);
      setTagLinks((current) => current.filter((link) => link.tag.id !== tagId));
    } catch { setNotice("标签关联未移除。 "); }
  }

  async function loadBackupManifest() {
    if (!accountId) return;
    try {
      setBackupManifest(await api.backupManifest(accountId));
    } catch { setNotice("备份前清单读取失败。 "); }
  }

  async function rebuildFtsIndex() {
    if (!accountId) return;
    setFtsRebuilding(true);
    try {
      const rebuilt = await api.rebuildFtsIndex(accountId);
      setFtsIndexStatus(rebuilt);
      setNotice(`全文索引已重建：${rebuilt.indexed_message_count} 条本地消息已索引，原始消息未被修改。`);
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `全文索引未重建（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请稍后重试。"}` : "全文索引未重建。");
    } finally {
      setFtsRebuilding(false);
    }
  }

  async function requestAccountDeletion() {
    if (!accountId) return;
    try {
      setDeletionRequest(await api.createAccountDeletionRequest(accountId));
      setDeletionConfirmation("");
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `删除请求未创建（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查当前账号。"}` : "删除请求未创建。 ");
    }
  }

  async function savePrivacyAcknowledgement() {
    if (!privacyAcknowledgement) return;
    setPrivacySaving(true);
    try {
      const saved = await api.updatePrivacySettings(true);
      setPrivacy(saved);
      setNotice("已确认本地处理边界。数据源检测仍不会安装或执行 wx-cli。");
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `本地安全设置未保存（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查本地 API。"}` : "本地安全设置未保存。");
    } finally {
      setPrivacySaving(false);
    }
  }

  async function confirmAccountDeletion() {
    if (!accountId || !deletionRequest || deletionConfirmation !== deletionRequest.confirmation_phrase) return;
    try {
      await api.deleteAccountData(accountId, deletionRequest.id, deletionConfirmation);
      setAccountId("");
      setContacts([]);
      setSelected(null);
      setStorage(null);
      setBackupManifest(null);
      setDeletionRequest(null);
      setDeletionConfirmation("");
      setNotice("当前账号的本地归档数据已删除。数据源检测不会被修改。");
    } catch (error) {
      setNotice(error instanceof LocalApiError ? `本地数据未删除（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请重新创建删除请求。"}` : "本地数据未删除。 ");
    }
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
    if (!window.confirm("确定删除这条已确认事实吗？删除后当前列表不再显示，但本地事实历史会保留此操作记录。")) return;
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

  async function saveKnowledgeCard() {
    if (!accountId || !knowledgeDraft || !knowledgeDraft.title.trim() || !knowledgeDraft.content.trim()) return;
    try {
      const payload = { ...knowledgeDraft, title: knowledgeDraft.title.trim(), content: knowledgeDraft.content.trim() };
      const saved = editingKnowledgeCardId ? await api.updateKnowledgeCard(editingKnowledgeCardId, accountId, payload) : await api.createKnowledgeCard(accountId, payload);
      setKnowledgeCards((current) => editingKnowledgeCardId ? current.map((item) => item.id === saved.id ? saved : item) : [saved, ...current]);
      setKnowledgeDraft(null); setEditingKnowledgeCardId(null);
    } catch { setNotice("知识卡未保存，请检查本地证据。 "); }
  }

  async function removeKnowledgeCard(cardId: string) {
    if (!accountId) return;
    try { await api.deleteKnowledgeCard(cardId, accountId); setKnowledgeCards((current) => current.filter((item) => item.id !== cardId)); }
    catch { setNotice("知识卡未删除。 "); }
  }

  async function saveActionItem() {
    if (!accountId || !actionDraft?.content.trim()) return;
    try { const saved = await api.createActionItem(accountId, { ...actionDraft, content: actionDraft.content.trim() }); setActionItems((current) => [saved, ...current]); setActionDraft(null); }
    catch (error) { setNotice(error instanceof LocalApiError ? `待办未保存（${error.status} · ${error.errorCode ?? "unknown"}）：${error.reason ?? "请检查原文证据。"}` : "待办未保存。 "); }
  }

  async function toggleActionItem(item: ActionItem) {
    if (!accountId) return;
    try { const saved = await api.updateActionItem(item.id, accountId, { content: item.content, status: item.status === "open" ? "done" : "open", due_at: item.due_at, message_ids: item.evidence.map((message) => message.id) }); setActionItems((current) => current.map((entry) => entry.id === saved.id ? saved : entry)); }
    catch { setNotice("待办状态未更新。 "); }
  }

  async function removeActionItem(itemId: string) {
    if (!accountId) return;
    try { await api.deleteActionItem(itemId, accountId); setActionItems((current) => current.filter((item) => item.id !== itemId)); await showActionHistory(itemId); }
    catch { setNotice("待办未删除。 "); }
  }

  function toggleKnowledgeEvidence(messageId: string) {
    setKnowledgeDraft((current) => current ? { ...current, message_ids: current.message_ids.includes(messageId) ? current.message_ids.filter((id) => id !== messageId) : [...current.message_ids, messageId] } : current);
  }

  async function showKnowledgeHistory(cardId: string) {
    if (!accountId) return;
    if (knowledgeHistoryCardId === cardId) { setKnowledgeHistoryCardId(null); setKnowledgeHistory([]); return; }
    try { setKnowledgeHistory(await api.knowledgeCardHistory(cardId, accountId)); setKnowledgeHistoryCardId(cardId); }
    catch { setNotice("知识卡历史读取失败。 "); }
  }

  async function showActionHistory(itemId: string) {
    if (!accountId) return;
    if (actionHistoryItemId === itemId) { setActionHistoryItemId(null); setActionHistory([]); return; }
    try { setActionHistory(await api.actionItemHistory(itemId, accountId)); setActionHistoryItemId(itemId); }
    catch { setNotice("待办历史读取失败。 "); }
  }

  const messageRows = (items: Message[], emptyCopy: string, canUseForFact = false) => {
    if (!items.length && !evidenceLoading) return <p className="empty-message">{emptyCopy}</p>;
    return items.map((item) => <article className="message-row" key={item.id}>
      <div><strong>{item.conversation_name}</strong><span>{item.sender_display_name} · {item.conversation_type === "group" ? "群聊" : "私聊"} · {item.message_type}</span></div>
      <p>{item.text_content}</p>{item.attachments?.length ? <aside className="attachment-list">{item.attachments.map((attachment, index) => <span key={`${attachment.name ?? "attachment"}-${index}`}>{attachment.name ?? "附件"}{attachment.mime_type ? ` · ${attachment.mime_type}` : ""}{attachment.size_bytes !== undefined && attachment.size_bytes !== null ? ` · ${attachment.size_bytes} B` : ""}</span>)}</aside> : null}
      <footer><time>{formatMessageTime(item.sent_at)}</time><span><button className="link" onClick={() => showContext(item)}>查看上下文</button><button className="link" onClick={() => beginActionItem(item)}>用于新待办</button>{canUseForFact && <button className="link" onClick={() => beginFact(item)}>用于新事实</button>}</span></footer>
    </article>);
  };

  const dataManagementPanel = <section className="card data-management">
    <header><strong>本地数据管理</strong><span>仅影响当前明确选择的账号</span></header>
    {!accountId ? <p>请选择本地账号后查看清单或准备删除。</p> : <>
      <div className="data-management-actions">
        <button type="button" className="secondary" onClick={() => void loadBackupManifest()}>生成备份前清单</button>
        <button type="button" className="secondary" disabled={ftsRebuilding} onClick={() => void rebuildFtsIndex()}>{ftsRebuilding ? "正在重建全文索引…" : "重建全文索引"}</button>
        <button type="button" className="link danger" onClick={() => void requestAccountDeletion()}>准备删除当前账号数据</button>
      </div>
      {backupManifest && <p className="backup-manifest">清单生成于 {formatMessageTime(backupManifest.generated_at)}：完整性 {backupManifest.integrity_check === "ok" ? "正常" : backupManifest.integrity_check}；消息 {backupManifest.counts.messages ?? 0}，联系人 {backupManifest.counts.contacts ?? 0}，事实 {backupManifest.counts.facts ?? 0}，知识卡 {backupManifest.counts.knowledge_cards ?? 0}，待办 {backupManifest.counts.action_items ?? 0}，标签 {backupManifest.counts.tags ?? 0}。</p>}
      {ftsIndexStatus && <p className={ftsIndexStatus.status === "ready" ? "index-status" : "index-status warning"}>全文索引：{ftsIndexStatus.status === "ready" ? "正常" : ftsIndexStatus.status === "needs_rebuild" ? "需要重建" : "不可用"}；原始消息 {ftsIndexStatus.message_count}，已索引 {ftsIndexStatus.indexed_message_count}。</p>}
      {deletionRequest && <div className="deletion-confirmation">
        <p>删除请求将在 {formatMessageTime(deletionRequest.expires_at)} 失效。此操作只删除当前账号的本地归档和用户本地记录，不能恢复。</p>
        <code>{deletionRequest.confirmation_phrase}</code>
        <label>确认短语<input value={deletionConfirmation} onChange={(event) => setDeletionConfirmation(event.target.value)} placeholder="输入上方确认短语" /></label>
        <button type="button" className="danger-action" disabled={deletionConfirmation !== deletionRequest.confirmation_phrase} onClick={() => void confirmAccountDeletion()}>删除当前账号数据</button>
      </div>}
    </>}
  </section>;

  const globalSearchPanel = <section className="card global-search-card">
    <header className="card-heading"><h2><MagnifyingGlass weight="bold" />全局搜索</h2><span className="search-scope">当前账号全部已归档消息</span></header>
    <p>只搜索本机已归档的原文。默认跨联系人；勾选后才限制为当前联系人。</p>
    <div className="search-results">
      <label className="inline-search"><input value={searchQuery} onChange={(event) => { setSearchQuery(event.target.value); setResults([]); setSearchState("idle"); }} onKeyDown={(event) => event.key === "Enter" && search()} placeholder="输入关键词后按 Enter" /><button className="link" onClick={search} disabled={!accountId || !searchQuery.trim() || searchState === "loading"}>{searchState === "loading" ? "搜索中…" : "搜索"}</button></label>
      <div className="search-filters"><label>消息类型<select value={searchFilters.message_type ?? ""} onChange={(event) => setSearchFilters({ ...searchFilters, message_type: event.target.value || undefined })}><option value="">全部</option><option value="text">文本</option><option value="file">文件</option><option value="link">链接</option><option value="image">图片</option><option value="voice">语音</option></select></label><label>开始日期<input type="date" value={searchFilters.date_from ?? ""} onChange={(event) => setSearchFilters({ ...searchFilters, date_from: event.target.value || undefined })} /></label><label>结束日期<input type="date" value={searchFilters.date_to ?? ""} onChange={(event) => setSearchFilters({ ...searchFilters, date_to: event.target.value || undefined })} /></label><label className="search-check"><input type="checkbox" checked={Boolean(searchFilters.contact_id)} disabled={!selected} onChange={(event) => setSearchFilters({ ...searchFilters, contact_id: event.target.checked ? selected?.id : undefined })} />当前联系人</label><label className="search-check"><input type="checkbox" checked={Boolean(searchFilters.has_attachment)} onChange={(event) => setSearchFilters({ ...searchFilters, has_attachment: event.target.checked || undefined })} />仅含附件</label></div>
      {!accountId ? <p className="empty-message">请先明确选择本地账号，再搜索已归档原文。</p> : searchState === "loading" ? <p className="empty-message" role="status">正在搜索已归档原文…</p> : searchState === "error" ? <p className="empty-message" role="status">搜索失败，请确认本地服务状态后重试。</p> : searchState === "complete" && !results.length ? <p className="empty-message" role="status">未找到包含“{searchQuery.trim()}”的已归档原文。</p> : messageRows(results, "输入关键词后可查看跨会话原文命中与上下文。", Boolean(searchFilters.contact_id))}
    </div>
  </section>;

  const timelinePanel = <section className="card timeline-card">
    <header className="card-heading"><h2><ChatCircleDots weight="fill" />本地时间线</h2><span className="search-scope">只读聚合已归档原文与用户操作</span></header>
    <p>按发生时间倒序显示，不从聊天自动生成任何结论。</p>
    <div className="timeline-filters">{(Object.keys(timelineKindLabels) as TimelineKind[]).map((kind) => <label key={kind}><input type="checkbox" checked={timelineKinds.includes(kind)} onChange={() => toggleTimelineKind(kind)} />{timelineKindLabels[kind]}</label>)}<label className="search-check"><input type="checkbox" checked={timelineContactOnly} disabled={!selected} onChange={(event) => setTimelineContactOnly(event.target.checked)} />当前联系人</label></div>
    {!accountId ? <p className="empty-message">请先明确选择本地账号，再查看本地时间线。</p> : timelineLoading ? <p className="empty-message">正在读取时间线…</p> : !timeline.length ? <p className="empty-message">当前筛选条件下暂无已归档消息或用户操作。</p> : <div className="timeline-list">{timeline.map((event) => { const source = event.message ?? event.evidence[0]; return <article className="timeline-row" key={`${event.kind}-${event.id}`}><div><strong>{timelineKindLabels[event.kind]} · {event.title}</strong><time>{formatMessageTime(event.occurred_at)}</time></div>{event.contact_display_name && <small>{event.contact_display_name}</small>}<p>{event.content}</p><footer>{source ? <button className="link" onClick={() => showContext(source)}>查看上下文</button> : <span className="manual-source">用户操作记录</span>}<span>{event.event_type}</span></footer></article>; })}</div>}
  </section>;

  const tagOptions = tagTargetOptions(tagTargetType);
  const tagPanel = <section className="card tag-card">
    <header className="card-heading"><h2><LinkSimple weight="fill" />标签管理</h2><button className="link" onClick={() => { setTagDraft(emptyTag()); setEditingTagId(null); }}>新建标签</button></header>
    <p>标签只由用户手动维护；不会从聊天、同步或资料中自动推断。</p>
    {tagDraft && <form className="tag-editor" onSubmit={(event) => { event.preventDefault(); void saveTag(); }}><label>名称<input value={tagDraft.name} onChange={(event) => setTagDraft({ ...tagDraft, name: event.target.value })} maxLength={64} required /></label><label>颜色<input type="color" value={tagDraft.color} onChange={(event) => setTagDraft({ ...tagDraft, color: event.target.value })} /></label><footer><button type="button" className="link" onClick={() => { setTagDraft(null); setEditingTagId(null); }}>取消</button><button className="primary" type="submit">{editingTagId ? "保存修改" : "保存标签"}</button></footer></form>}
    {!tags.length ? <p className="empty-message">尚无本地标签。</p> : <div className="tag-list">{tags.map((tag) => <article key={tag.id}><span className="tag-swatch" style={{ backgroundColor: tag.color }} /><strong>{tag.name}</strong><small>{formatMessageTime(tag.updated_at)}</small><span><button className="link" onClick={() => { setEditingTagId(tag.id); setTagDraft({ name: tag.name, color: tag.color }); }}>编辑</button><button className="link danger" onClick={() => void removeTag(tag.id)}>删除</button></span></article>)}</div>}
    <section className="tag-links"><h3>关联本地对象</h3>{!tags.length ? <p className="empty-message">先创建标签，再关联本地对象。</p> : <><div className="tag-link-form"><label>标签<select value={tagAssignmentId} onChange={(event) => setTagAssignmentId(event.target.value)}>{tags.map((tag) => <option value={tag.id} key={tag.id}>{tag.name}</option>)}</select></label><label>对象类型<select value={tagTargetType} onChange={(event) => changeTagTargetType(event.target.value as TagTargetType)}><option value="contact">联系人</option><option value="fact">已确认事实</option><option value="knowledge_card">本地知识卡</option><option value="action_item">手动待办</option></select></label><label>对象<select value={tagTargetId} onChange={(event) => setTagTargetId(event.target.value)} disabled={!tagOptions.length}><option value="">{tagOptions.length ? "请选择对象" : "当前无可关联对象"}</option>{tagOptions.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}</select></label><button className="primary" type="button" disabled={!tagAssignmentId || !tagTargetId} onClick={() => void addTagLink()}>添加关联</button></div>{!tagTargetId ? <p className="empty-message">选择一个本地对象后可查看已有标签。</p> : !tagLinks.length ? <p className="empty-message">该对象尚未关联标签。</p> : <div className="tag-link-list">{tagLinks.map((link) => <span key={link.id}><i className="tag-swatch" style={{ backgroundColor: link.tag.color }} />{link.tag.name}<button className="link danger" onClick={() => void removeTagLink(link.tag.id)}>移除</button></span>)}</div>}</>}</section>
  </section>;

  const settingsPanel = <section className="card privacy-settings">
    <header className="card-heading"><h2><Database weight="fill" />安全设置</h2><span className="search-scope">本地安全模式</span></header>
    <p>本应用只提供本机数据工作流。安全模式不会安装或执行 wx-cli，也不会读取、解密、导入或上传真实微信聊天数据。</p>
    <dl>
      <div><dt>本地处理边界</dt><dd>{privacy?.local_processing_acknowledged ? "已确认" : "尚未确认"}{privacy?.updated_at && <small>更新于 {formatMessageTime(privacy.updated_at)}</small>}</dd></div>
      <div><dt>真实采集</dt><dd>未获 Go/No-Go 授权</dd></div>
      <div><dt>AI 与云端处理</dt><dd>已关闭</dd></div>
    </dl>
  </section>;

  if (!privacy?.local_processing_acknowledged) return <main className="privacy-onboarding">
    <section>
      <span className="privacy-mark"><Database weight="fill" /></span>
      <p className="privacy-eyebrow">本地安全模式</p>
      <h1>先确认数据处理边界</h1>
      <p>本应用仅处理本机已归档的合成数据。本确认不会安装、执行或接入 wx-cli；不会读取、解密、导入或上传任何真实微信聊天数据。</p>
      {privacy ? <label className="privacy-check"><input type="checkbox" checked={privacyAcknowledgement} onChange={(event) => setPrivacyAcknowledgement(event.target.checked)} />我已了解本地处理边界与真实采集需要单独 Go/No-Go 授权。</label> : <p className="privacy-error">{notice || "正在读取本地安全设置…"}</p>}
      <button className="primary" disabled={!privacy || !privacyAcknowledgement || privacySaving} onClick={() => void savePrivacyAcknowledgement()}>{privacySaving ? "保存中…" : "继续以本地安全模式使用"}</button>
    </section>
  </main>;

  return <div className="app-shell">
    <aside className="nav">
      <div><div className="brand"><span><LinkSimple weight="bold" /></span>微信关系记忆</div><nav>{nav.map((item) => { const target = item === "关系记忆" ? "relationships" : item === "待办事项" ? "actions" : item === "全局搜索" ? "search" : item === "时间线" ? "timeline" : item === "标签管理" ? "tags" : item === "设置" ? "settings" : null; return <button className={target === workspace ? "active" : ""} key={item} disabled={!target} title={target ? undefined : `${item}正在开发中`} onClick={() => target === "search" ? openGlobalSearch() : target === "timeline" ? openTimeline() : target === "tags" ? openTags() : target && setWorkspace(target)}><UsersThree size={18} />{item}{!target && <small>开发中</small>}</button>; })}</nav></div>
      <div className="local"><Database size={17} /><span>本地关系工作台<small>数据仅存本机</small></span></div>
    </aside>
    <section className="contacts">
      <label className="search"><MagnifyingGlass size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索联系人、公司或角色" /></label>
      <div className="pane-title"><strong>全部联系人</strong><span>{contacts.length}</span></div>
      <p className="sort-hint">按最后消息时间排序，最新在前</p>
      <div className="contact-list">{contacts.map((contact) => <button key={contact.id} className={selected?.id === contact.id ? "selected" : ""} onClick={() => selectContact(contact)}><i>{avatar(contact)}</i><span><strong>{contact.display_name}</strong><small>{contactSummary(contact)}</small><time>最后消息：{formatMessageTime(contact.last_message_at)}</time></span></button>)}{!loading && !contacts.length && <p className="empty">首次归档完成后，联系人会显示在这里。</p>}</div>
    </section>
    <main style={{ gridTemplateRows: workspace === "relationships" ? "34px auto 48px 1fr" : "34px auto 1fr" }}>
      <header className="status"><div className="source-status"><span className={sourceReady ? "ok" : "warn"}>{sourceReady ? <CloudCheck weight="fill" /> : <WarningCircle weight="fill" />}{statusCopy}</span>{coverageWarning && <span className="coverage-warning"><WarningCircle weight="fill" />{coverageWarning}</span>}</div><button disabled={!canSync || syncing} onClick={() => sync("incremental")}>{syncing ? <CircleNotch className="spin" /> : <ArrowClockwise />}立即同步</button></header>
      <section className="hero"><div className="profile-avatar">{selected ? avatar(selected) : <UsersThree />}</div><div><h1>{workspace === "search" ? "搜索本地已归档原文" : workspace === "timeline" ? "查看本地时间线" : workspace === "tags" ? "管理本地标签" : selected?.display_name ?? "开始建立本地关系记忆"}</h1><p>{workspace === "search" ? "跨会话搜索仅在当前本地账号的已归档数据中进行。" : workspace === "timeline" ? "只读查看已归档原文与本地用户操作，所有内容均可追溯。" : workspace === "tags" ? "标签由用户维护，只关联当前账号的明确本地对象。" : selected ? contactSummary(selected) : accountSelectionRequired ? "请先明确选择本地账号；系统不会按目录、昵称或头像猜测。" : "先选择一个已确认的数据源账号，再开始首次归档。"}</p><div className="chips"><span>本地优先</span><span>原文可追溯</span><span>身份稳定</span></div></div><div className="hero-actions" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}><button className="secondary" onClick={() => sync("initial")} disabled={!canSync || syncing}>首次归档</button><button className="primary" onClick={openGlobalSearch}><MagnifyingGlass />搜索聊天记录</button>{(syncing || notice) && <p role="status" aria-live="polite" style={{ flexBasis: "100%", margin: 0, color: "#2469b0", fontSize: "10px", lineHeight: 1.4, textAlign: "right" }}>{syncing ? "正在归档本地合成数据…" : notice}</p>}</div></section>
      {workspace === "relationships" && <div className="tabs"><button className={activeTab === "overview" ? "active" : ""} aria-selected={activeTab === "overview"} onClick={() => setActiveTab("overview")}>关系总览</button><button className={activeTab === "evidence" ? "active" : ""} aria-selected={activeTab === "evidence"} onClick={() => setActiveTab("evidence")}>聊天证据</button><button disabled>待办事项</button><button disabled>标签与备注</button></div>}
      <div className="content">{workspace === "actions" && <section className="card evidence-card"><header className="card-heading"><h2>手动待办事项</h2><button className="link" onClick={() => beginActionItem()}>添加待办</button></header><p>仅由用户手动创建，不从聊天自动推断。</p>{actionDraft && <form className="fact-editor" onSubmit={(event) => { event.preventDefault(); void saveActionItem(); }}><label>内容<textarea value={actionDraft.content} onChange={(event) => setActionDraft({ ...actionDraft, content: event.target.value })} required /></label><fieldset><legend>原文证据（可选）</legend>{evidence.length ? evidence.map((message) => <label className="fact-evidence-choice" key={message.id}><input type="checkbox" checked={actionDraft.message_ids.includes(message.id)} onChange={() => setActionDraft((current) => current ? { ...current, message_ids: current.message_ids.includes(message.id) ? current.message_ids.filter((id) => id !== message.id) : [...current.message_ids, message.id] } : current)} />{message.conversation_name} · {formatMessageTime(message.sent_at)} · {message.text_content}</label>) : <p>可从原文搜索结果或聊天证据添加原文关联。</p>}</fieldset><footer><button type="button" className="link" onClick={() => setActionDraft(null)}>取消</button><button className="primary" type="submit">保存待办</button></footer></form>}{!actionItems.length ? <p className="empty-message">尚无手动待办。</p> : <div className="fact-list">{actionItems.map((item) => <article className="fact-row" key={item.id}><div><strong>{item.status === "done" ? "已完成" : "待处理"}</strong><time>{formatMessageTime(item.updated_at)}</time></div><p>{item.content}</p><footer>{item.evidence.length ? <button className="link" onClick={() => showContext(item.evidence[0])}>原文证据 {item.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span><button className="link" onClick={() => void showActionHistory(item.id)}>历史</button><button className="link" onClick={() => void toggleActionItem(item)}>{item.status === "done" ? "恢复待处理" : "标记完成"}</button><button className="link danger" onClick={() => void removeActionItem(item.id)}>删除</button></span></footer></article>)}</div>}{actionHistoryItemId && <section className="fact-history"><h3>待办历史</h3>{!actionHistory.length ? <p className="empty-message">当前待办尚无操作历史。</p> : <div className="fact-list">{actionHistory.map((event) => <article className="fact-row history-row" key={event.id}><div><strong>{event.event_type === "created" ? "已创建" : event.event_type === "updated" ? "已更新" : "已删除"} · {event.status === "done" ? "已完成" : "待处理"}</strong><time>{formatMessageTime(event.occurred_at)}</time></div><p>{event.content}</p><footer>{event.evidence.length ? <button className="link" onClick={() => showContext(event.evidence[0])}>原文证据 {event.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span className="history-source">用户操作记录</span></footer></article>)}</div>}</section>}</section>}
        {workspace === "search" && globalSearchPanel}
        {workspace === "timeline" && timelinePanel}
        {workspace === "tags" && tagPanel}
        {workspace === "settings" && settingsPanel}
        {workspace === "relationships" && activeTab === "overview" && <>
          <section className="card profile-card"><header className="card-heading"><h2><UsersThree weight="fill" />联系人档案</h2><span><button className="link" disabled={!selected} onClick={() => setProfileHistoryOpen((current) => !current)}>资料历史</button><button className="link" disabled={!selected} onClick={beginProfileEdit}>编辑资料</button></span></header>{selected ? <><p>用户维护资料只保存在本机，不会被同步覆盖，也不会由聊天自动推断。</p><dl className="profile-fields"><div><dt>备注</dt><dd>{selected.user_remark_name ?? selected.remark_name ?? "暂无"}<small>{selected.user_remark_name ? "用户维护" : "采集资料"}</small></dd></div><div><dt>确认实名</dt><dd>{selected.user_confirmed_real_name ?? selected.confirmed_real_name ?? "暂无"}<small>{selected.user_confirmed_real_name ? "用户维护" : "采集资料"}</small></dd></div><div><dt>公司</dt><dd>{selected.effective_company ?? selected.company ?? "暂无"}<small>{selected.user_company ? "用户维护" : "采集资料"}</small></dd></div><div><dt>角色</dt><dd>{selected.effective_role ?? selected.role ?? "暂无"}<small>{selected.user_role ? "用户维护" : "采集资料"}</small></dd></div></dl>{profileDraft && <form className="profile-editor" onSubmit={(event) => { event.preventDefault(); void saveProfile(profileDraft); }}><label>备注<input value={profileDraft.remark_name ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, remark_name: event.target.value })} maxLength={255} /></label><label>确认实名<input value={profileDraft.confirmed_real_name ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, confirmed_real_name: event.target.value })} maxLength={255} /></label><label>公司<input value={profileDraft.company ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, company: event.target.value })} maxLength={255} /></label><label>角色<input value={profileDraft.role ?? ""} onChange={(event) => setProfileDraft({ ...profileDraft, role: event.target.value })} maxLength={255} /></label><footer><button type="button" className="link" onClick={() => setProfileDraft(null)}>取消</button><button className="primary" type="submit" disabled={profileSaving}>{profileSaving ? "保存中…" : "保存资料"}</button></footer></form>}{!profileDraft && <button className="link clear-profile" disabled={profileSaving || ![selected.user_remark_name, selected.user_confirmed_real_name, selected.user_company, selected.user_role].some(Boolean)} onClick={() => void saveProfile(emptyProfile())}>清除用户维护</button>}{profileHistoryOpen && <section className="profile-history"><h3>资料历史</h3>{profileHistoryLoading ? <p className="empty-message">正在读取资料历史…</p> : !profileHistory.length ? <p className="empty-message">当前联系人尚无资料操作历史。</p> : <div className="profile-history-list">{profileHistory.map((event) => <article key={event.id}><strong>{profileSnapshot(event)}</strong><time>{formatMessageTime(event.occurred_at)}</time><span>用户操作记录</span></article>)}</div>}</section>}</> : <p className="empty-message">选择联系人后可维护本地资料。</p>}</section>
          <section className="card confirmed"><header className="card-heading"><h2><CheckCircle weight="fill" />已确认的事实</h2><span><button className="link" disabled={!selected} onClick={() => setHistoryOpen((current) => !current)}>事实历史</button><button className="link" disabled={!selected} onClick={() => beginFact()}>添加事实</button></span></header><p>仅由用户手动记录或确认；系统不会从聊天自动推断事实。</p>{factDraft && <form className="fact-editor" onSubmit={(event) => { event.preventDefault(); void saveFact(); }}><label>类型<select value={factDraft.kind} onChange={(event) => setFactDraft({ ...factDraft, kind: event.target.value as FactKind })}>{Object.entries(factKindLabels).map(([kind, label]) => <option value={kind} key={kind}>{label}</option>)}</select></label><label>内容<textarea value={factDraft.content} onChange={(event) => setFactDraft({ ...factDraft, content: event.target.value })} placeholder="输入用户确认的内容" maxLength={2000} required /></label><fieldset><legend>原文证据（可选）</legend>{evidence.length ? evidence.map((message) => <label className="fact-evidence-choice" key={message.id}><input type="checkbox" checked={factDraft.message_ids.includes(message.id)} onChange={() => toggleFactEvidence(message.id)} />{message.conversation_name} · {formatMessageTime(message.sent_at)} · {message.text_content}</label>) : <p>无原文证据时将标记为“用户手动记录”。</p>}</fieldset><footer><button type="button" className="link" onClick={() => { setFactDraft(null); setEditingFactId(null); }}>取消</button><button className="primary" type="submit" disabled={factSaving || !factDraft.content.trim()}>{factSaving ? "保存中…" : editingFactId ? "保存修改" : "保存事实"}</button></footer></form>}{factsLoading ? <p className="empty-message">正在读取已确认事实…</p> : !facts.length ? <p className="empty-message">尚无已确认事实。可手动记录，或从聊天证据添加原文关联。</p> : <div className="fact-list">{facts.map((fact) => <article className="fact-row" key={fact.id}><div><strong>{factKindLabels[fact.kind]}</strong><time>更新于 {formatMessageTime(fact.updated_at)}</time></div><p>{fact.content}</p><footer>{fact.evidence.length ? <button className="link" onClick={() => showContext(fact.evidence[0])}>原文证据 {fact.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span><button className="link" onClick={() => editFact(fact)}>编辑</button><button className="link danger" onClick={() => void removeFact(fact.id)}>删除</button></span></footer></article>)}</div>}{historyOpen && <section className="fact-history"><h3>事实历史</h3>{historyLoading ? <p className="empty-message">正在读取事实历史…</p> : !factHistory.length ? <p className="empty-message">当前联系人尚无事实操作历史。</p> : <div className="fact-list">{factHistory.map((event) => <article className="fact-row history-row" key={event.id}><div><strong>{factHistoryLabels[event.event_type]} · {factKindLabels[event.kind]}</strong><time>{formatMessageTime(event.occurred_at)}</time></div><p>{event.content}</p><footer>{event.evidence.length ? <button className="link" onClick={() => showContext(event.evidence[0])}>原文证据 {event.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span className="history-source">用户操作记录</span></footer></article>)}</div>}</section>}</section>
          <section className="card ai"><h2><ChatCircleDots weight="fill" />原文搜索</h2><div className="search-results"><label className="inline-search"><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && search()} placeholder="输入关键词后按 Enter" /><button className="link" onClick={search}>搜索</button></label><div className="search-filters"><label>消息类型<select value={searchFilters.message_type ?? ""} onChange={(event) => setSearchFilters({ ...searchFilters, message_type: event.target.value || undefined })}><option value="">全部</option><option value="text">文本</option><option value="file">文件</option><option value="link">链接</option><option value="image">图片</option><option value="voice">语音</option></select></label><label>开始日期<input type="date" value={searchFilters.date_from ?? ""} onChange={(event) => setSearchFilters({ ...searchFilters, date_from: event.target.value || undefined })} /></label><label>结束日期<input type="date" value={searchFilters.date_to ?? ""} onChange={(event) => setSearchFilters({ ...searchFilters, date_to: event.target.value || undefined })} /></label><label className="search-check"><input type="checkbox" checked={Boolean(searchFilters.contact_id)} disabled={!selected} onChange={(event) => setSearchFilters({ ...searchFilters, contact_id: event.target.checked ? selected?.id : undefined })} />当前联系人</label><label className="search-check"><input type="checkbox" checked={Boolean(searchFilters.has_attachment)} onChange={(event) => setSearchFilters({ ...searchFilters, has_attachment: event.target.checked || undefined })} />仅含附件</label></div>{messageRows(results, "输入关键词后可查看原文命中与上下文。")}</div></section>
          <section className="card knowledge-card"><header className="card-heading"><h2><LinkSimple weight="fill" />本地知识卡</h2><button className="link" onClick={() => { setKnowledgeDraft(emptyKnowledgeCard()); setEditingKnowledgeCardId(null); }}>新建知识卡</button></header><p>仅由用户手动整理，原文证据可选；不会由 AI 或同步自动生成。</p>{knowledgeDraft && <form className="fact-editor" onSubmit={(event) => { event.preventDefault(); void saveKnowledgeCard(); }}><label>类型<select value={knowledgeDraft.card_type} onChange={(event) => setKnowledgeDraft({ ...knowledgeDraft, card_type: event.target.value as KnowledgeCardType })}><option value="note">笔记</option><option value="contact">联系人</option><option value="project">项目</option><option value="decision">决策</option></select></label><label>标题<input value={knowledgeDraft.title} onChange={(event) => setKnowledgeDraft({ ...knowledgeDraft, title: event.target.value })} required /></label><label>内容<textarea value={knowledgeDraft.content} onChange={(event) => setKnowledgeDraft({ ...knowledgeDraft, content: event.target.value })} required /></label><fieldset><legend>当前联系人原文证据（可选）</legend>{evidence.map((message) => <label className="fact-evidence-choice" key={message.id}><input type="checkbox" checked={knowledgeDraft.message_ids.includes(message.id)} onChange={() => toggleKnowledgeEvidence(message.id)} />{message.conversation_name} · {message.text_content}</label>)}</fieldset><footer><button type="button" className="link" onClick={() => setKnowledgeDraft(null)}>取消</button><button className="primary" type="submit">保存知识卡</button></footer></form>}{!knowledgeCards.length ? <p className="empty-message">尚无本地知识卡。</p> : <div className="fact-list">{knowledgeCards.map((card) => <article className="fact-row" key={card.id}><div><strong>{card.title}</strong><time>{formatMessageTime(card.updated_at)}</time></div><p>{card.content}</p><footer>{card.evidence.length ? <button className="link" onClick={() => showContext(card.evidence[0])}>原文证据 {card.evidence.length} 条</button> : <span className="manual-source">用户手动记录</span>}<span><button className="link" onClick={() => void showKnowledgeHistory(card.id)}>历史</button><button className="link" onClick={() => { setEditingKnowledgeCardId(card.id); setKnowledgeDraft({ card_type: card.card_type, title: card.title, content: card.content, message_ids: card.evidence.map((item) => item.id) }); }}>编辑</button><button className="link danger" onClick={() => void removeKnowledgeCard(card.id)}>删除</button></span></footer>{knowledgeHistoryCardId === card.id && <div className="profile-history-list">{knowledgeHistory.map((event) => <article key={event.id}><strong>{event.event_type} · {event.title}</strong><time>{formatMessageTime(event.occurred_at)}</time><span>{event.content}</span></article>)}</div>}</article>)}</div>}</section>
        </>}
        {workspace === "relationships" && activeTab === "evidence" && <section className="card evidence-card"><h2><ChatCircleDots weight="fill" />{selected ? `${selected.display_name} 的聊天证据` : "聊天证据"}</h2><p>包含与该联系人的私聊，以及该联系人在已归档群聊中的发言。</p><div className="evidence-list">{evidenceLoading ? <p className="empty-message">正在读取聊天证据…</p> : messageRows(evidence, "当前联系人尚无可追溯聊天证据。", true)}</div></section>}
        {context && <section className="card context-card" ref={contextRef}><h2>消息上下文</h2><div className="context-list">{context.messages.map((item) => <article className={item.id === context.anchor_id ? "context-message anchor" : "context-message"} key={item.id}><strong>{item.sender_display_name} · {formatMessageTime(item.sent_at)}</strong><p>{item.text_content}</p></article>)}</div></section>}
        <section className="card needs"><h2>同步状态与下一步</h2>{source && (accountSelectionRequired || source.accounts.length > 1) && <label className="account-picker">{accountSelectionRequired ? "请选择本地账号" : "当前本地账号"}<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="" disabled>请选择一个已探测账号</option>{source.accounts.map((account) => <option value={account.id} key={account.id}>{account.display_name}</option>)}</select></label>}{schedule && <div className="schedule-state"><strong>{schedule.enabled ? `自动增量同步已启用（每 ${Math.round(schedule.interval_seconds / 60)} 分钟）` : "自动增量同步未启用"}</strong><span>{schedule.enabled ? "仅对已首次归档的合成账号生效。" : schedule.reason}</span></div>}{storage && <div className="recent-sync"><strong>本地存储 · {storage.integrity_check === "ok" ? "完整性正常" : storage.integrity_check}</strong><span>消息 {storage.messages} · 联系人 {storage.contacts} · 事实 {storage.facts} · 知识卡 {storage.knowledge_cards}</span></div>}{syncRuns.length > 0 && <div className="recent-sync"><strong>最近同步</strong>{syncRuns.slice(0, 3).map((run) => <span key={run.id}>{syncRunSummary(run)}</span>)}</div>}<p>{contextLoading ? "正在读取消息上下文…" : "查看聊天证据可核对联系人消息来源与前后文。真实微信连接仍需通过只读 Go/No-Go。"}</p></section>
        {dataManagementPanel}
      </div>
    </main>
  </div>;
}
