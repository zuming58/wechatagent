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
export type Contact = { id: string; display_name: string; company?: string | null; role?: string | null; avatar_ref?: string | null; last_message_at?: string | null };
export type Message = { id: string; conversation_id: string; conversation_name: string; sender_display_name: string; sent_at: string; message_type: string; text_content: string; snippet: string };
export type SyncRun = { id: string; status: string; inserted_count: number; duplicate_count: number; error_code?: string | null };

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
  return response.json() as Promise<T>;
}

export const api = {
  sourceStatus: () => request<SourceStatus>("/source/status"),
  contacts: (accountId: string, query = "") => request<Contact[]>(`/contacts?account_id=${encodeURIComponent(accountId)}&query=${encodeURIComponent(query)}`),
  search: (accountId: string, query: string) => request<Message[]>(`/messages/search?account_id=${encodeURIComponent(accountId)}&q=${encodeURIComponent(query)}`),
  sync: (accountId: string, mode: "initial" | "incremental" = "incremental") => request<SyncRun>("/sync", { method: "POST", body: JSON.stringify({ account_id: accountId, mode }) }),
};
