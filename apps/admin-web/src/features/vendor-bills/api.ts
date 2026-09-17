import { apiFetch } from "@/lib/api/client";
import type {
  AccountOption,
  VendorBill,
  VendorBillPage,
  VendorOption,
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
