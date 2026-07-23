import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    api: {
      sourceStatus: vi.fn(),
      contacts: vi.fn(),
      search: vi.fn(),
      sync: vi.fn(),
    },
  };
});

import { App } from "./App";
import { api, LocalApiError, type SourceStatus } from "./api";

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

function renderWithSource(source: SourceStatus) {
  mockedApi.sourceStatus.mockResolvedValue(source);
  mockedApi.contacts.mockResolvedValue([]);
  mockedApi.search.mockResolvedValue([]);
  mockedApi.sync.mockResolvedValue({ id: "synthetic-run", status: "completed", inserted_count: 0, duplicate_count: 0 });
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
});
