export type Account = { id: string; display_name: string; selected: boolean };
export type SourceStatus = {
  status: string;
  wechat_version?: string | null;
  connector_version?: string | null;
  accounts: Account[];
  reason?: string | null;
  requires_elevation: boolean;
  unknown_shards: string[];
};
export type Contact = {
  id: string;
  display_name: string;
  remark_name?: string | null;
  nickname?: string | null;
  confirmed_real_name?: string | null;
  company?: string | null;
  role?: string | null;
  user_remark_name?: string | null;
  user_confirmed_real_name?: string | null;
  user_company?: string | null;
  user_role?: string | null;
  effective_company?: string | null;
  effective_role?: string | null;
  avatar_ref?: string | null;
  last_message_at?: string | null;
};
export type Attachment = { name?: string | null; mime_type?: string | null; size_bytes?: number | null };
export type Message = { id: string; conversation_id: string; conversation_name: string; conversation_type: string; sender_display_name: string; sent_at: string; message_type: string; text_content: string; snippet: string; attachments?: Attachment[] };
export type MessageSearchFilters = { conversation_id?: string; contact_id?: string; message_type?: string; date_from?: string; date_to?: string; has_attachment?: boolean };
export type MessageContext = { anchor_id: string; messages: Message[] };
export type TimelineKind = "message" | "fact" | "profile" | "knowledge_card" | "action_item";
export type TimelineEvent = { id: string; account_id: string; kind: TimelineKind; event_type: string; occurred_at: string; title: string; content: string; contact_id?: string | null; contact_display_name?: string | null; message?: Message | null; evidence: Message[] };
export type TimelineFilters = { kinds?: TimelineKind[]; contact_id?: string; date_from?: string; date_to?: string; limit?: number };
export type SyncRun = { id: string; status: string; inserted_count: number; duplicate_count: number; error_code?: string | null };
export type SyncSchedule = {
  enabled: boolean;
  interval_seconds: number;
  reason?: string | null;
  last_cycle_at?: string | null;
  next_run_at?: string | null;
};
export type FactKind = "company" | "role" | "need" | "concern" | "commitment";
export type Fact = {
  id: string;
  account_id: string;
  contact_id: string;
  kind: FactKind;
  content: string;
  created_at: string;
  updated_at: string;
  evidence: Message[];
};
export type FactWrite = { kind: FactKind; content: string; message_ids: string[] };
export type FactHistoryEvent = {
  id: string;
  account_id: string;
  contact_id: string;
  fact_id: string;
  event_type: "created" | "updated" | "deleted";
  kind: FactKind;
  content: string;
  occurred_at: string;
  evidence: Message[];
};
export type ContactProfileWrite = { remark_name?: string | null; confirmed_real_name?: string | null; company?: string | null; role?: string | null };
export type ContactProfileHistoryEvent = {
  id: string;
  account_id: string;
  contact_id: string;
  user_remark_name?: string | null;
  user_confirmed_real_name?: string | null;
  user_company?: string | null;
  user_role?: string | null;
  occurred_at: string;
};
export type KnowledgeCardType = "contact" | "project" | "decision" | "note";
export type KnowledgeCardWrite = { card_type: KnowledgeCardType; title: string; content: string; message_ids: string[] };
export type KnowledgeCard = { id: string; account_id: string; card_type: KnowledgeCardType; title: string; content: string; created_at: string; updated_at: string; evidence: Message[] };
export type KnowledgeCardHistoryEvent = { id: string; account_id: string; card_id: string; event_type: "created" | "updated" | "deleted"; card_type: KnowledgeCardType; title: string; content: string; occurred_at: string; evidence: Message[] };
export type StorageStatus = { account_id: string; contacts: number; conversations: number; messages: number; facts: number; knowledge_cards: number; integrity_check: string };
export type ActionItem = { id: string; account_id: string; content: string; status: "open" | "done"; due_at?: string | null; created_at: string; updated_at: string; evidence: Message[] };
export type ActionItemWrite = { content: string; status: "open" | "done"; due_at?: string | null; message_ids: string[] };
export type ActionItemHistoryEvent = { id: string; account_id: string; action_item_id: string; event_type: "created" | "updated" | "deleted"; content: string; status: "open" | "done"; due_at?: string | null; occurred_at: string; evidence: Message[] };

export class LocalApiError extends Error {
  constructor(public readonly status: number, public readonly errorCode?: string, public readonly reason?: string) {
    super(reason ?? errorCode ?? `Local API request failed with ${status}`);
  }
}

const base = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: { error_code?: string; reason?: string } } | null;
    throw new LocalApiError(response.status, payload?.detail?.error_code, payload?.detail?.reason);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  sourceStatus: () => request<SourceStatus>("/source/status"),
  contacts: (accountId: string, query = "") => request<Contact[]>(`/contacts?account_id=${encodeURIComponent(accountId)}&query=${encodeURIComponent(query)}`),
  contactMessages: (contactId: string, accountId: string) => request<Message[]>(`/contacts/${encodeURIComponent(contactId)}/messages?account_id=${encodeURIComponent(accountId)}`),
  facts: (contactId: string, accountId: string) => request<Fact[]>(`/contacts/${encodeURIComponent(contactId)}/facts?account_id=${encodeURIComponent(accountId)}`),
  factHistory: (contactId: string, accountId: string) => request<FactHistoryEvent[]>(`/contacts/${encodeURIComponent(contactId)}/fact-history?account_id=${encodeURIComponent(accountId)}`),
  updateContactProfile: (contactId: string, accountId: string, payload: ContactProfileWrite) => request<Contact>(`/contacts/${encodeURIComponent(contactId)}/profile?account_id=${encodeURIComponent(accountId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  contactProfileHistory: (contactId: string, accountId: string) => request<ContactProfileHistoryEvent[]>(`/contacts/${encodeURIComponent(contactId)}/profile-history?account_id=${encodeURIComponent(accountId)}`),
  createFact: (contactId: string, accountId: string, payload: FactWrite) => request<Fact>(`/contacts/${encodeURIComponent(contactId)}/facts?account_id=${encodeURIComponent(accountId)}`, { method: "POST", body: JSON.stringify(payload) }),
  updateFact: (factId: string, accountId: string, payload: FactWrite) => request<Fact>(`/facts/${encodeURIComponent(factId)}?account_id=${encodeURIComponent(accountId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteFact: (factId: string, accountId: string) => request<void>(`/facts/${encodeURIComponent(factId)}?account_id=${encodeURIComponent(accountId)}`, { method: "DELETE" }),
  knowledgeCards: (accountId: string) => request<KnowledgeCard[]>(`/knowledge-cards?account_id=${encodeURIComponent(accountId)}`),
  createKnowledgeCard: (accountId: string, payload: KnowledgeCardWrite) => request<KnowledgeCard>(`/knowledge-cards?account_id=${encodeURIComponent(accountId)}`, { method: "POST", body: JSON.stringify(payload) }),
  updateKnowledgeCard: (cardId: string, accountId: string, payload: KnowledgeCardWrite) => request<KnowledgeCard>(`/knowledge-cards/${encodeURIComponent(cardId)}?account_id=${encodeURIComponent(accountId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteKnowledgeCard: (cardId: string, accountId: string) => request<void>(`/knowledge-cards/${encodeURIComponent(cardId)}?account_id=${encodeURIComponent(accountId)}`, { method: "DELETE" }),
  knowledgeCardHistory: (cardId: string, accountId: string) => request<KnowledgeCardHistoryEvent[]>(`/knowledge-cards/${encodeURIComponent(cardId)}/history?account_id=${encodeURIComponent(accountId)}`),
  storageStatus: (accountId: string) => request<StorageStatus>(`/storage/status?account_id=${encodeURIComponent(accountId)}`),
  actionItems: (accountId: string, status?: "open" | "done") => request<ActionItem[]>(`/action-items?account_id=${encodeURIComponent(accountId)}${status ? `&status=${status}` : ""}`),
  createActionItem: (accountId: string, payload: ActionItemWrite) => request<ActionItem>(`/action-items?account_id=${encodeURIComponent(accountId)}`, { method: "POST", body: JSON.stringify(payload) }),
  updateActionItem: (itemId: string, accountId: string, payload: ActionItemWrite) => request<ActionItem>(`/action-items/${encodeURIComponent(itemId)}?account_id=${encodeURIComponent(accountId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteActionItem: (itemId: string, accountId: string) => request<void>(`/action-items/${encodeURIComponent(itemId)}?account_id=${encodeURIComponent(accountId)}`, { method: "DELETE" }),
  actionItemHistory: (itemId: string, accountId: string) => request<ActionItemHistoryEvent[]>(`/action-items/${encodeURIComponent(itemId)}/history?account_id=${encodeURIComponent(accountId)}`),
  timeline: (accountId: string, filters: TimelineFilters = {}) => {
    const params = new URLSearchParams({ account_id: accountId });
    for (const kind of filters.kinds ?? []) params.append("kind", kind);
    if (filters.contact_id) params.set("contact_id", filters.contact_id);
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    if (filters.limit) params.set("limit", String(filters.limit));
    return request<TimelineEvent[]>(`/timeline?${params.toString()}`);
  },
  search: (accountId: string, query: string, filters?: MessageSearchFilters) => {
    const params = new URLSearchParams({ account_id: accountId, q: query });
    for (const [key, value] of Object.entries(filters ?? {})) if (value !== undefined && value !== "" && value !== false) params.set(key, String(value));
    return request<Message[]>(`/messages/search?${params.toString()}`);
  },
  messageContext: (messageId: string) => request<MessageContext>(`/messages/${encodeURIComponent(messageId)}/context`),
  sync: (accountId: string, mode: "initial" | "incremental" = "incremental") => request<SyncRun>("/sync", { method: "POST", body: JSON.stringify({ account_id: accountId, mode }) }),
  syncRuns: (accountId: string) => request<SyncRun[]>(`/sync/runs?account_id=${encodeURIComponent(accountId)}`),
  syncSchedule: () => request<SyncSchedule>("/sync/schedule"),
};
