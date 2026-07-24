import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    api: {
      sourceStatus: vi.fn(),
      contacts: vi.fn(),
      contactMessages: vi.fn(),
      facts: vi.fn(),
      factHistory: vi.fn(),
      updateContactProfile: vi.fn(),
      contactProfileHistory: vi.fn(),
      createFact: vi.fn(),
      updateFact: vi.fn(),
      deleteFact: vi.fn(),
      search: vi.fn(),
      messageContext: vi.fn(),
      sync: vi.fn(),
      syncRuns: vi.fn(),
      syncSchedule: vi.fn(),
      knowledgeCards: vi.fn(),
      createKnowledgeCard: vi.fn(),
      updateKnowledgeCard: vi.fn(),
      deleteKnowledgeCard: vi.fn(),
      knowledgeCardHistory: vi.fn(),
      storageStatus: vi.fn(),
      backupManifest: vi.fn(),
      createAccountDeletionRequest: vi.fn(),
      deleteAccountData: vi.fn(),
      actionItems: vi.fn(),
      createActionItem: vi.fn(),
      updateActionItem: vi.fn(),
      deleteActionItem: vi.fn(),
      actionItemHistory: vi.fn(),
      timeline: vi.fn(),
      tags: vi.fn(),
      createTag: vi.fn(),
      updateTag: vi.fn(),
      deleteTag: vi.fn(),
      tagLinks: vi.fn(),
      createTagLink: vi.fn(),
      deleteTagLink: vi.fn(),
    },
  };
});

import { App } from "./App";
import { api, LocalApiError, type ActionItem, type ActionItemHistoryEvent, type Contact, type ContactProfileHistoryEvent, type Fact, type FactHistoryEvent, type Message, type MessageContext, type SourceStatus, type Tag, type TagLink, type TimelineEvent } from "./api";

const mockedApi = vi.mocked(api);

function sourceStatus(overrides: Partial<SourceStatus> = {}): SourceStatus {
  return {
    status: "ready",
    accounts: [],
    requires_elevation: false,
    unknown_shards: [],
    ...overrides,
  };
}

function renderWithSource(source: SourceStatus, data: {
  contacts?: Contact[];
  evidence?: Message[];
  facts?: Fact[];
  history?: FactHistoryEvent[];
  profileHistory?: ContactProfileHistoryEvent[];
  actionItems?: ActionItem[];
  actionHistory?: ActionItemHistoryEvent[];
  search?: Message[];
  context?: MessageContext;
  timeline?: TimelineEvent[];
  tags?: Tag[];
  tagLinks?: TagLink[];
} = {}) {
  mockedApi.sourceStatus.mockResolvedValue(source);
  mockedApi.contacts.mockResolvedValue(data.contacts ?? []);
  mockedApi.contactMessages.mockResolvedValue(data.evidence ?? []);
  mockedApi.facts.mockResolvedValue(data.facts ?? []);
  mockedApi.factHistory.mockResolvedValue(data.history ?? []);
  mockedApi.contactProfileHistory.mockResolvedValue(data.profileHistory ?? []);
  mockedApi.updateContactProfile.mockImplementation(async (contactId, _accountId, payload) => ({ id: contactId, display_name: payload.remark_name || "Synthetic Contact", remark_name: "Source Remark", nickname: "Source Nickname", company: "Source Company", role: "Source Role", user_remark_name: payload.remark_name || null, user_confirmed_real_name: payload.confirmed_real_name || null, user_company: payload.company || null, user_role: payload.role || null, effective_company: payload.company || "Source Company", effective_role: payload.role || "Source Role", last_message_at: null }));
  mockedApi.createFact.mockImplementation(async (_contactId, accountId, payload) => ({ id: "new-fact", account_id: accountId, contact_id: "contact-zhang", created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z", evidence: (data.evidence ?? []).filter((message) => payload.message_ids.includes(message.id)), ...payload }));
  mockedApi.updateFact.mockImplementation(async (factId, accountId, payload) => ({ id: factId, account_id: accountId, contact_id: "contact-zhang", created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:01:00Z", evidence: (data.evidence ?? []).filter((message) => payload.message_ids.includes(message.id)), ...payload }));
  mockedApi.deleteFact.mockResolvedValue(undefined);
  mockedApi.search.mockResolvedValue(data.search ?? []);
  mockedApi.messageContext.mockResolvedValue(data.context ?? { anchor_id: "synthetic-message", messages: [] });
  mockedApi.sync.mockResolvedValue({ id: "synthetic-run", status: "completed", inserted_count: 0, duplicate_count: 0 });
  mockedApi.syncRuns.mockResolvedValue([]);
  mockedApi.syncSchedule.mockResolvedValue({ enabled: true, interval_seconds: 300 });
  mockedApi.knowledgeCards.mockResolvedValue([]);
  mockedApi.storageStatus.mockResolvedValue({ account_id: "account-b", contacts: 0, conversations: 0, messages: 0, facts: 0, knowledge_cards: 0, integrity_check: "ok" });
  mockedApi.backupManifest.mockResolvedValue({ account_id: "account-b", generated_at: "2026-07-24T12:00:00Z", integrity_check: "ok", counts: { contacts: 2, conversations: 1, messages: 4, facts: 1, knowledge_cards: 1, action_items: 1, tags: 1 } });
  mockedApi.createAccountDeletionRequest.mockResolvedValue({ id: "deletion-request", account_id: "account-b", confirmation_phrase: "DELETE account-b", expires_at: "2026-07-24T12:10:00Z" });
  mockedApi.deleteAccountData.mockResolvedValue(undefined);
  mockedApi.actionItems.mockResolvedValue([]);
  mockedApi.createActionItem.mockImplementation(async (accountId, payload) => ({ id: "new-action", account_id: accountId, created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z", evidence: (data.evidence ?? []).filter((message) => payload.message_ids.includes(message.id)), ...payload }));
  mockedApi.updateActionItem.mockImplementation(async (itemId, accountId, payload) => ({ id: itemId, account_id: accountId, created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:01:00Z", evidence: (data.evidence ?? []).filter((message) => payload.message_ids.includes(message.id)), ...payload }));
  mockedApi.deleteActionItem.mockResolvedValue(undefined);
  mockedApi.actionItems.mockResolvedValue(data.actionItems ?? []);
  mockedApi.actionItemHistory.mockResolvedValue(data.actionHistory ?? []);
  mockedApi.timeline.mockResolvedValue(data.timeline ?? []);
  mockedApi.tags.mockResolvedValue(data.tags ?? []);
  mockedApi.createTag.mockImplementation(async (accountId, payload) => ({ id: "new-tag", account_id: accountId, created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z", ...payload }));
  mockedApi.updateTag.mockImplementation(async (tagId, accountId, payload) => ({ id: tagId, account_id: accountId, created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:01:00Z", ...payload }));
  mockedApi.deleteTag.mockResolvedValue(undefined);
  mockedApi.tagLinks.mockResolvedValue(data.tagLinks ?? []);
  mockedApi.createTagLink.mockImplementation(async (accountId, tagId, targetType, targetId) => ({ id: "new-tag-link", account_id: accountId, tag: (data.tags ?? []).find((tag) => tag.id === tagId) ?? { id: tagId, account_id: accountId, name: "Tag", color: "#1677ff", created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z" }, target_type: targetType, target_id: targetId, created_at: "2026-07-23T12:00:00Z" }));
  mockedApi.deleteTagLink.mockResolvedValue(undefined);
  return render(<App />);
}

function syncButtons() {
  return [
    screen.getByRole("button", { name: "首次归档" }),
    screen.getByRole("button", { name: "立即同步" }),
  ];
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedApi.contacts.mockResolvedValue([]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("multi-account sync safety gate", () => {
  it("requires an explicit account before an account-selection sync", async () => {
    renderWithSource(sourceStatus({
      status: "account_selection_required",
      reason: "Select a local account before syncing.",
      accounts: [
        { id: "account-a", display_name: "Synthetic Account A", selected: false },
        { id: "account-b", display_name: "Synthetic Account B", selected: false },
      ],
    }));

    const picker = await screen.findByLabelText("请选择本地账号");
    expect(picker).toHaveValue("");
    expect(screen.getByText("请选择本地账号后再开始同步")).toBeInTheDocument();
    for (const button of syncButtons()) expect(button).toBeDisabled();
    expect(mockedApi.sync).not.toHaveBeenCalled();

    fireEvent.change(picker, { target: { value: "account-b" } });

    await waitFor(() => expect(syncButtons()[0]).toBeEnabled());
    fireEvent.click(syncButtons()[0]);
    await waitFor(() => expect(mockedApi.sync).toHaveBeenCalledWith("account-b", "initial"));
    expect(mockedApi.sync).toHaveBeenCalledTimes(1);
  });

  it("uses the connector-selected account when the source is ready", async () => {
    renderWithSource(sourceStatus({
      accounts: [
        { id: "account-a", display_name: "Synthetic Account A", selected: false },
        { id: "account-b", display_name: "Synthetic Account B", selected: true },
      ],
    }));

    const picker = await screen.findByLabelText("当前本地账号");
    expect(picker).toHaveValue("account-b");
    for (const button of syncButtons()) expect(button).toBeEnabled();

    fireEvent.click(syncButtons()[1]);
    await waitFor(() => expect(mockedApi.sync).toHaveBeenCalledWith("account-b", "incremental"));
  });

  it.each(["connector_missing", "permission_denied", "unsupported_version", "wechat_offline", "unexpected_status"])("keeps sync disabled for %s", async (status) => {
    const reason = `Synthetic reason for ${status}`;
    renderWithSource(sourceStatus({ status, reason, accounts: [{ id: "account-a", display_name: "Synthetic Account A", selected: true }] }));

    expect(await screen.findByText(reason)).toBeInTheDocument();
    for (const button of syncButtons()) expect(button).toBeDisabled();
    fireEvent.click(syncButtons()[0]);
    fireEvent.click(syncButtons()[1]);
    expect(mockedApi.sync).not.toHaveBeenCalled();
  });

  it("shows LocalApiError status, error code, and reason", async () => {
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }));
    mockedApi.sync.mockRejectedValue(new LocalApiError(409, "account_not_available", "Choose a detected account."));

    await waitFor(() => expect(syncButtons()[0]).toBeEnabled());
    fireEvent.click(syncButtons()[0]);

    expect(await screen.findByText(/409.*account_not_available.*Choose a detected account/)).toBeInTheDocument();
  });

  it("shows an incomplete-data warning without exposing shard identifiers", async () => {
    renderWithSource(sourceStatus({
      accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }],
      unknown_shards: ["synthetic-shard-a", "synthetic-shard-b"],
    }));

    expect(await screen.findByText("数据范围不完整：有 2 个未纳入的数据分片。")).toBeInTheDocument();
    expect(screen.queryByText("synthetic-shard-a")).not.toBeInTheDocument();
    expect(syncButtons()[0]).toBeEnabled();
  });

  it("distinguishes completed-with-warning and failed sync responses", async () => {
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }));
    mockedApi.sync.mockResolvedValueOnce({ id: "warning-run", status: "completed_with_warning", inserted_count: 2, duplicate_count: 1, error_code: "possibly_stale" });
    mockedApi.sync.mockResolvedValueOnce({ id: "failed-run", status: "failed", inserted_count: 0, duplicate_count: 0, error_code: "connector_missing" });

    await waitFor(() => expect(syncButtons()[0]).toBeEnabled());
    fireEvent.click(syncButtons()[0]);
    expect(await screen.findByText(/同步已完成，但数据质量警告.*possibly_stale.*新增 2 条，重复 1 条/)).toBeInTheDocument();

    fireEvent.click(syncButtons()[0]);
    expect(await screen.findByText("同步未完成（connector_missing）。")).toBeInTheDocument();
  });

  it("shows last-message timestamps and loads private plus group evidence for the selected contact", async () => {
    const zhang = { id: "contact-zhang", display_name: "张工", last_message_at: "2026-07-23T11:55:00Z" };
    const wang = { id: "contact-wang", display_name: "王总", last_message_at: null };
    const evidence = {
      id: "message-group",
      conversation_id: "group-1",
      conversation_name: "试点群",
      conversation_type: "group",
      sender_display_name: "张工",
      sent_at: "2026-07-23T11:40:00Z",
      message_type: "text",
      text_content: "群聊中的已归档发言",
      snippet: "群聊中的已归档发言",
    };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), {
      contacts: [zhang, wang],
      evidence: [evidence],
      context: { anchor_id: evidence.id, messages: [evidence] },
    });

    expect(await screen.findByText("按最后消息时间排序，最新在前")).toBeInTheDocument();
    expect(await screen.findByText("最后消息：暂无消息")).toBeInTheDocument();
    expect(screen.getAllByText(/最后消息：/)).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "聊天证据" }));
    await waitFor(() => expect(mockedApi.contactMessages).toHaveBeenCalledWith("contact-zhang", "account-b"));
    expect(await screen.findByText("群聊中的已归档发言")).toBeInTheDocument();
    expect(screen.getByText(/张工.*群聊.*text/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看上下文" }));
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("message-group"));
    expect(await screen.findByText("消息上下文")).toBeInTheDocument();
  });

  it("opens context from a keyword search result", async () => {
    const result = {
      id: "search-message",
      conversation_id: "private-1",
      conversation_name: "张工",
      conversation_type: "private",
      sender_display_name: "张工",
      sent_at: "2026-07-23T11:55:00Z",
      message_type: "text",
      text_content: "离线部署的原文结果",
      snippet: "离线部署的原文结果",
    };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), {
      search: [result],
      context: { anchor_id: result.id, messages: [result] },
    });

    const queryInput = await screen.findByPlaceholderText("输入关键词后按 Enter");
    fireEvent.change(queryInput, { target: { value: "离线部署" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    await waitFor(() => expect(mockedApi.search).toHaveBeenCalledWith("account-b", "离线部署", {}));

    expect(await screen.findByText("离线部署的原文结果")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看上下文" }));
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("search-message"));
    expect(await screen.findByText("消息上下文")).toBeInTheDocument();
  });

  it("creates a manual fact and labels it as a user record", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact] });

    const addFact = await screen.findByRole("button", { name: "添加事实" });
    await waitFor(() => expect(addFact).toBeEnabled());
    fireEvent.click(addFact);
    fireEvent.change(screen.getByLabelText("内容"), { target: { value: "Confirmed manually" } });
    fireEvent.click(screen.getByRole("button", { name: "保存事实" }));

    await waitFor(() => expect(mockedApi.createFact).toHaveBeenCalledWith("contact-zhang", "account-b", { kind: "company", content: "Confirmed manually", message_ids: [] }));
    expect(await screen.findByText("用户手动记录")).toBeInTheDocument();
  });

  it("uses a selected evidence message for a new fact and opens its context", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    const evidence = { id: "evidence-message", conversation_id: "private-1", conversation_name: "Synthetic Contact", conversation_type: "private", sender_display_name: "Synthetic Contact", sent_at: "2026-07-23T12:00:00Z", message_type: "text", text_content: "Traceable source", snippet: "Traceable source" };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact], evidence: [evidence], context: { anchor_id: evidence.id, messages: [evidence] } });

    fireEvent.click(await screen.findByRole("button", { name: "聊天证据" }));
    fireEvent.click(await screen.findByRole("button", { name: "用于新事实" }));
    fireEvent.change(screen.getByLabelText("内容"), { target: { value: "Confirmed with evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "保存事实" }));

    await waitFor(() => expect(mockedApi.createFact).toHaveBeenCalledWith("contact-zhang", "account-b", { kind: "company", content: "Confirmed with evidence", message_ids: ["evidence-message"] }));
    fireEvent.click(await screen.findByRole("button", { name: "原文证据 1 条" }));
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("evidence-message"));
  });

  it("edits, deletes, and clears an unfinished fact when the contact changes", async () => {
    const first = { id: "contact-zhang", display_name: "First Contact", last_message_at: null };
    const second = { id: "contact-chen", display_name: "Second Contact", last_message_at: null };
    const fact: Fact = { id: "fact-1", account_id: "account-b", contact_id: first.id, kind: "need", content: "Original fact", created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z", evidence: [] };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [first, second], facts: [fact] });

    fireEvent.click(await screen.findByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("内容"), { target: { value: "Updated fact" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() => expect(mockedApi.updateFact).toHaveBeenCalledWith("fact-1", "account-b", { kind: "need", content: "Updated fact", message_ids: [] }));

    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    await waitFor(() => expect(mockedApi.deleteFact).toHaveBeenCalledWith("fact-1", "account-b"));

    fireEvent.click(screen.getByRole("button", { name: "添加事实" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Contact/ }));
    expect(screen.queryByLabelText("内容")).not.toBeInTheDocument();
  });

  it("shows local fact history, opens evidence context, and clears it for another contact", async () => {
    const first = { id: "contact-zhang", display_name: "First Contact", last_message_at: null };
    const second = { id: "contact-chen", display_name: "Second Contact", last_message_at: null };
    const evidence = { id: "history-message", conversation_id: "private-1", conversation_name: "First Contact", conversation_type: "private", sender_display_name: "First Contact", sent_at: "2026-07-23T12:00:00Z", message_type: "text", text_content: "History source", snippet: "History source" };
    const history: FactHistoryEvent[] = [{ id: "history-delete", account_id: "account-b", contact_id: first.id, fact_id: "fact-deleted", event_type: "deleted", kind: "need", content: "Deleted local fact", occurred_at: "2026-07-23T12:01:00Z", evidence: [evidence] }];
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [first, second], evidence: [evidence], history, context: { anchor_id: evidence.id, messages: [evidence] } });

    const historyButton = await screen.findByRole("button", { name: "事实历史" });
    await waitFor(() => expect(historyButton).toBeEnabled());
    fireEvent.click(historyButton);
    await waitFor(() => expect(mockedApi.factHistory).toHaveBeenCalledWith("contact-zhang", "account-b"));
    expect(await screen.findByRole("heading", { name: "事实历史" })).toBeInTheDocument();
    expect(screen.getByText("已删除 · 需求")).toBeInTheDocument();
    expect(screen.getByText("Deleted local fact")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "原文证据 1 条" }));
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("history-message"));
    fireEvent.click(screen.getByRole("button", { name: /Second Contact/ }));
    expect(screen.queryByRole("heading", { name: "事实历史" })).not.toBeInTheDocument();
  });

  it("edits user contact details, shows profile history, and clears overrides", async () => {
    const first: Contact = { id: "contact-zhang", display_name: "Source Remark", remark_name: "Source Remark", company: "Source Company", role: "Source Role", effective_company: "Source Company", effective_role: "Source Role", last_message_at: null };
    const second: Contact = { id: "contact-chen", display_name: "Second Contact", last_message_at: null };
    const profileHistory: ContactProfileHistoryEvent[] = [{ id: "profile-history-1", account_id: "account-b", contact_id: first.id, user_remark_name: "User Remark", user_company: "User Company", user_role: "User Role", occurred_at: "2026-07-23T12:01:00Z" }];
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [first, second], profileHistory });

    const edit = await screen.findByRole("button", { name: "编辑资料" });
    await waitFor(() => expect(edit).toBeEnabled());
    fireEvent.click(edit);
    fireEvent.change(screen.getByLabelText("备注"), { target: { value: "User Remark" } });
    fireEvent.change(screen.getByLabelText("公司"), { target: { value: "User Company" } });
    fireEvent.change(screen.getByLabelText("角色"), { target: { value: "User Role" } });
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));

    await waitFor(() => expect(mockedApi.updateContactProfile).toHaveBeenCalledWith("contact-zhang", "account-b", { remark_name: "User Remark", confirmed_real_name: "", company: "User Company", role: "User Role" }));
    expect(await screen.findAllByText("用户维护")).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "资料历史" }));
    await waitFor(() => expect(mockedApi.contactProfileHistory).toHaveBeenCalledWith("contact-zhang", "account-b"));
    expect(await screen.findByRole("heading", { name: "资料历史" })).toBeInTheDocument();
    expect(screen.getByText(/User Remark.*User Company.*User Role/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "清除用户维护" }));
    await waitFor(() => expect(mockedApi.updateContactProfile).toHaveBeenLastCalledWith("contact-zhang", "account-b", { remark_name: "", confirmed_real_name: "", company: "", role: "" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Contact/ }));
    expect(screen.queryByRole("heading", { name: "资料历史" })).not.toBeInTheDocument();
  });

  it("passes structured search filters and renders only safe attachment details", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    const result = { id: "file-message", conversation_id: "private-1", conversation_name: "Synthetic Contact", conversation_type: "private", sender_display_name: "Synthetic Contact", sent_at: "2026-07-23T11:55:00Z", message_type: "file", text_content: "文件已发送", snippet: "文件已发送", attachments: [{ name: "报价方案.pdf", mime_type: "application/pdf", size_bytes: 1024 }] };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact], search: [result] });

    fireEvent.change(await screen.findByPlaceholderText("输入关键词后按 Enter"), { target: { value: "报价方案" } });
    await screen.findByRole("button", { name: /Synthetic Contact/ });
    await waitFor(() => expect(screen.getByLabelText("当前联系人")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("消息类型"), { target: { value: "file" } });
    fireEvent.click(screen.getByLabelText("当前联系人"));
    fireEvent.click(screen.getByLabelText("仅含附件"));
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    await waitFor(() => expect(mockedApi.search).toHaveBeenCalledWith("account-b", "报价方案", { message_type: "file", contact_id: "contact-zhang", has_attachment: true }));
    expect(await screen.findByText(/报价方案.pdf.*application\/pdf.*1024 B/)).toBeInTheDocument();
  });

  it("creates a manual action item from source evidence and shows its local history", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    const evidence = { id: "action-message", conversation_id: "private-1", conversation_name: "Synthetic Contact", conversation_type: "private", sender_display_name: "Synthetic Contact", sent_at: "2026-07-23T12:00:00Z", message_type: "text", text_content: "Action source", snippet: "Action source" };
    const item: ActionItem = { id: "action-1", account_id: "account-b", content: "Follow up", status: "open", due_at: null, created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z", evidence: [evidence] };
    const history: ActionItemHistoryEvent[] = [{ id: "action-history-1", account_id: "account-b", action_item_id: item.id, event_type: "deleted", content: "Follow up", status: "done", due_at: null, occurred_at: "2026-07-23T12:01:00Z", evidence: [evidence] }];
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact], evidence: [evidence], actionItems: [item], actionHistory: history, context: { anchor_id: evidence.id, messages: [evidence] } });

    await screen.findByRole("button", { name: /Synthetic Contact/ });
    await waitFor(() => expect(mockedApi.contactMessages).toHaveBeenCalledWith("contact-zhang", "account-b"));
    fireEvent.click((await screen.findAllByRole("button", { name: "待办事项" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "添加待办" }));
    fireEvent.change(screen.getByLabelText("内容"), { target: { value: "Evidence-backed follow up" } });
    fireEvent.click(screen.getByLabelText(/Action source/));
    fireEvent.click(screen.getByRole("button", { name: "保存待办" }));
    await waitFor(() => expect(mockedApi.createActionItem).toHaveBeenCalledWith("account-b", { content: "Evidence-backed follow up", status: "open", due_at: null, message_ids: ["action-message"] }));

    fireEvent.click(screen.getAllByRole("button", { name: "原文证据 1 条" })[0]);
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("action-message"));
    fireEvent.click(screen.getAllByRole("button", { name: "历史" })[1]);
    await waitFor(() => expect(mockedApi.actionItemHistory).toHaveBeenCalledWith("action-1", "account-b"));
    expect(await screen.findByRole("heading", { name: "待办历史" })).toBeInTheDocument();
    expect(screen.getByText("已删除 · 已完成")).toBeInTheDocument();
  });

  it("opens a cross-contact global search workspace and keeps context traceable", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    const result = { id: "global-message", conversation_id: "group-1", conversation_name: "Synthetic Group", conversation_type: "group", sender_display_name: "Synthetic Contact", sent_at: "2026-07-23T12:00:00Z", message_type: "text", text_content: "Cross-contact source", snippet: "Cross-contact source" };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact], search: [result], context: { anchor_id: result.id, messages: [result] } });

    fireEvent.click(await screen.findByRole("button", { name: "全局搜索" }));
    expect(await screen.findByRole("heading", { name: "全局搜索" })).toBeInTheDocument();
    expect(screen.getByText("当前账号全部已归档消息")).toBeInTheDocument();
    expect(screen.getByLabelText("当前联系人")).not.toBeChecked();

    fireEvent.change(screen.getByPlaceholderText("输入关键词后按 Enter"), { target: { value: "source" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => expect(mockedApi.search).toHaveBeenCalledWith("account-b", "source", {}));
    expect(await screen.findByText("Cross-contact source")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "用于新事实" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("当前联系人"));
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => expect(mockedApi.search).toHaveBeenLastCalledWith("account-b", "source", { contact_id: "contact-zhang" }));
    expect(await screen.findByRole("button", { name: "用于新事实" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看上下文" }));
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("global-message"));
    expect(await screen.findByRole("heading", { name: "消息上下文" })).toBeInTheDocument();
  });

  it("opens the read-only timeline, filters it by the selected contact, and opens source context", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    const message = { id: "timeline-message", conversation_id: "group-1", conversation_name: "Synthetic Group", conversation_type: "group", sender_display_name: "Synthetic Contact", sent_at: "2026-07-23T12:00:00Z", message_type: "text", text_content: "Timeline source", snippet: "Timeline source" };
    const event: TimelineEvent = { id: "timeline-event", account_id: "account-b", kind: "fact", event_type: "created", occurred_at: "2026-07-23T12:01:00Z", title: "已确认事实 · need", content: "User-confirmed requirement", contact_id: contact.id, contact_display_name: contact.display_name, evidence: [message] };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact], timeline: [event], context: { anchor_id: message.id, messages: [message] } });

    await screen.findByRole("button", { name: /Synthetic Contact/ });
    fireEvent.click(screen.getByRole("button", { name: "时间线" }));
    await waitFor(() => expect(mockedApi.timeline).toHaveBeenCalledWith("account-b", { kinds: ["message", "fact", "profile", "knowledge_card", "action_item"], contact_id: undefined }));
    expect(await screen.findByRole("heading", { name: "本地时间线" })).toBeInTheDocument();
    expect(screen.getByText("User-confirmed requirement")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看上下文" }));
    await waitFor(() => expect(mockedApi.messageContext).toHaveBeenCalledWith("timeline-message"));
    fireEvent.click(screen.getByLabelText("当前联系人"));
    await waitFor(() => expect(mockedApi.timeline).toHaveBeenLastCalledWith("account-b", { kinds: ["message", "fact", "profile", "knowledge_card", "action_item"], contact_id: "contact-zhang" }));
  });

  it("manages manual tags and links a tag only to the selected local target", async () => {
    const contact = { id: "contact-zhang", display_name: "Synthetic Contact", last_message_at: null };
    const fact: Fact = { id: "fact-1", account_id: "account-b", contact_id: contact.id, kind: "need", content: "Synthetic requirement", created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z", evidence: [] };
    const tag: Tag = { id: "tag-1", account_id: "account-b", name: "Priority", color: "#1677ff", created_at: "2026-07-23T12:00:00Z", updated_at: "2026-07-23T12:00:00Z" };
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }), { contacts: [contact], facts: [fact], tags: [tag] });

    fireEvent.click(await screen.findByRole("button", { name: "标签管理" }));
    expect(await screen.findByRole("heading", { name: "标签管理" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新建标签" }));
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "Customer" } });
    fireEvent.click(screen.getByRole("button", { name: "保存标签" }));
    await waitFor(() => expect(mockedApi.createTag).toHaveBeenCalledWith("account-b", { name: "Customer", color: "#1677ff" }));

    fireEvent.change(screen.getByLabelText("对象类型"), { target: { value: "fact" } });
    await waitFor(() => expect(screen.getByLabelText("对象")).toHaveValue("fact-1"));
    fireEvent.click(screen.getByRole("button", { name: "添加关联" }));
    await waitFor(() => expect(mockedApi.createTagLink).toHaveBeenCalledWith("account-b", "tag-1", "fact", "fact-1"));
    expect(await screen.findAllByText("Priority")).not.toHaveLength(0);
  });

  it("keeps implemented workspace navigation available when the connector is unavailable", async () => {
    renderWithSource(sourceStatus({ status: "connector_missing", reason: "Synthetic connector is unavailable." }));

    expect(await screen.findByRole("button", { name: /时间线/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /标签管理/ })).toBeEnabled();
  });

  it("shows a content-free backup manifest and requires an exact second confirmation before deleting account data", async () => {
    renderWithSource(sourceStatus({ accounts: [{ id: "account-b", display_name: "Synthetic Account B", selected: true }] }));

    const manifestButton = await screen.findByRole("button", { name: "生成备份前清单" });
    expect(mockedApi.deleteAccountData).not.toHaveBeenCalled();
    fireEvent.click(manifestButton);
    await waitFor(() => expect(mockedApi.backupManifest).toHaveBeenCalledWith("account-b"));
    expect(await screen.findByText(/消息 4，联系人 2，事实 1/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "准备删除当前账号数据" }));
    await waitFor(() => expect(mockedApi.createAccountDeletionRequest).toHaveBeenCalledWith("account-b"));
    const deleteButton = await screen.findByRole("button", { name: "删除当前账号数据" });
    expect(deleteButton).toBeDisabled();
    expect(mockedApi.deleteAccountData).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("确认短语"), { target: { value: "DELETE account-b" } });
    expect(deleteButton).toBeEnabled();
    fireEvent.click(deleteButton);
    await waitFor(() => expect(mockedApi.deleteAccountData).toHaveBeenCalledWith("account-b", "deletion-request", "DELETE account-b"));
  });
});
