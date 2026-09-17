import { apiFetch } from "@/lib/api/client";
import type {
  AccountOption,
  VendorBill,
  VendorBillPage,
  VendorOption,
  VendorBillAttachment,
} from "./types";

export const listVendorBills = (query: Record<string, string>) =>
  apiFetch<VendorBillPage>("/api/vendor-bills", { query });
export const getVendorBill = (id: string) =>
  apiFetch<VendorBill>(`/api/vendor-bills/${encodeURIComponent(id)}`);
export const createVendorBill = (body: Record<string, unknown>) =>
  apiFetch<VendorBill>("/api/vendor-bills", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const updateVendorBill = (id: string, body: Record<string, unknown>) =>
  apiFetch<VendorBill>(`/api/vendor-bills/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const addVendorBillLine = (id: string, body: Record<string, unknown>) =>
  apiFetch(`/api/vendor-bills/${encodeURIComponent(id)}/lines`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const updateVendorBillLine = (
  id: string,
  lineId: string,
  body: Record<string, unknown>,
) =>
  apiFetch(
    `/api/vendor-bills/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
export const deleteVendorBillLine = (id: string, lineId: string) =>
  apiFetch(
    `/api/vendor-bills/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}`,
    { method: "DELETE" },
  );
export const runVendorBillAction = (
  id: string,
  action: "submit" | "approve" | "reject" | "post",
  reason = "",
) =>
  apiFetch<VendorBill>(
    `/api/vendor-bills/${encodeURIComponent(id)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action === "reject" ? { reason } : {}),
    },
  );
export const listVendorBillAttachments = (id: string) =>
  apiFetch<VendorBillAttachment[]>(
    `/api/vendor-bills/${encodeURIComponent(id)}/attachments`,
  );
export const uploadVendorBillAttachment = (id: string, file: File) => {
  const body = new FormData();
  body.set("file", file);
  return apiFetch<VendorBillAttachment>(
    `/api/vendor-bills/${encodeURIComponent(id)}/attachments`,
    { method: "POST", body },
  );
};
export async function listBillVendors() {
  const page = await apiFetch<{ results: VendorOption[] }>("/api/vendors", {
    query: { is_active: "true" },
  });
  return page.results;
}
export async function listExpenseAccounts() {
  const data = await apiFetch<AccountOption[]>(
    "/api/reference/vendor-bill-accounts",
  );
  return Array.isArray(data) ? data : [];
}
