import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const api = vi.hoisted(() => ({
  deleteReceiptHistory: vi.fn(),
  downloadReceiptWorkbook: vi.fn(),
  getReceiptHistory: vi.fn(),
  getSavedApiToken: vi.fn(() => "test-token"),
  processReceiptImages: vi.fn(),
  renameReceiptHistory: vi.fn(),
  saveApiToken: vi.fn(),
  saveReceiptManual: vi.fn(),
}));

vi.mock("../api/client", () => api);

import { ReceiptExtractorPage } from "./receipt-extractor-page";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  vi.spyOn(window, "alert").mockImplementation(() => undefined);
});

test("manual entries typed during OCR survive a stale history refresh", async () => {
  const processing = deferred<{ job_id: string; columns: string[]; rows: Array<Record<string, string>>; duplicate_count: number; duplicate_files: string[] }>();
  const refreshedHistory = deferred<Array<Record<string, unknown>>>();
  const save = deferred<void>();
  api.processReceiptImages.mockReturnValue(processing.promise);
  api.saveReceiptManual.mockReturnValue(save.promise);
  api.getReceiptHistory
    .mockResolvedValueOnce([{ job_id: "old-job", created_at: "2026-09-01T00:00:00Z", title: "旧批次", total: 1, columns: ["付款金额"], rows: [] }])
    .mockReturnValueOnce(refreshedHistory.promise);

  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  const { container } = render(
    <QueryClientProvider client={queryClient}>
      <ReceiptExtractorPage />
    </QueryClientProvider>,
  );

  await screen.findByText("旧批次");
  const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
  expect(fileInput).not.toBeNull();
  fireEvent.change(fileInput!, { target: { files: [new File(["image"], "receipt.jpg", { type: "image/jpeg" })] } });
  fireEvent.click(screen.getByRole("button", { name: "开始提取" }));
  fireEvent.change(screen.getByPlaceholderText(/支持简写/), { target: { value: "出差餐补320" } });
  fireEvent.click(screen.getByRole("button", { name: "批量添加" }));
  expect(screen.getByText("320.00")).toBeInTheDocument();

  await act(async () => {
    processing.resolve({ job_id: "new-job", columns: ["付款金额", "是否有发票"], rows: [], duplicate_count: 0, duplicate_files: [] });
  });
  await waitFor(() => expect(api.saveReceiptManual).toHaveBeenCalledWith("new-job", [expect.objectContaining({ 金额: "320.00", 用途: "出差餐补" })], ""));
  await act(async () => {
    refreshedHistory.resolve([
      { job_id: "new-job", created_at: "2026-09-08T00:00:00Z", title: "新批次", total: 1, columns: ["付款金额", "是否有发票"], rows: [], manual_entries: [], manual_draft: "" },
      { job_id: "old-job", created_at: "2026-09-01T00:00:00Z", title: "旧批次", total: 1, columns: ["付款金额"], rows: [] },
    ]);
  });
  const oldRow = screen.getByText("旧批次").closest("tr");
  const newRow = await screen.findByText("新批次").then((cell) => cell.closest("tr"));
  expect(oldRow).not.toBeNull();
  expect(newRow).not.toBeNull();
  fireEvent.click(within(oldRow!).getByRole("button", { name: "查看" }));
  fireEvent.click(within(newRow!).getByRole("button", { name: "查看" }));

  expect(screen.getByText("320.00")).toBeInTheDocument();
  save.resolve();
});
