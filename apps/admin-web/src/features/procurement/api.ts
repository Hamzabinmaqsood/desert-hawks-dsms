import { apiFetch } from "@/lib/api/client";
import type {
  ExpenseAccount,
  Page,
  PurchaseOrder,
  PurchaseReceipt,
  PurchaseRequisition,
  VendorOption,
} from "./types";

const base = "/api/procurement";
const id = (value: string) => encodeURIComponent(value);
const resource = {
  requisition: "purchase-requisitions",
  order: "purchase-orders",
  receipt: "purchase-receipts",
} as const;

const list = <T>(name: string, query: Record<string, string>) =>
  apiFetch<Page<T>>(`${base}/${name}`, { query });
const get = <T>(name: string, value: string) =>
  apiFetch<T>(`${base}/${name}/${id(value)}`);
const save = <T>(
  name: string,
  value: string | null,
  body: Record<string, unknown>,
) =>
  apiFetch<T>(`${base}/${name}${value ? `/${id(value)}` : ""}`, {
    method: value ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const listRequisitions = (query: Record<string, string>) =>
  list<PurchaseRequisition>(resource.requisition, query);
export const getRequisition = (value: string) =>
  get<PurchaseRequisition>(resource.requisition, value);
export const saveRequisition = (
  value: string | null,
  body: Record<string, unknown>,
) => save<PurchaseRequisition>(resource.requisition, value, body);

export const listOrders = (query: Record<string, string>) =>
  list<PurchaseOrder>(resource.order, query);
export const getOrder = (value: string) =>
  get<PurchaseOrder>(resource.order, value);
export const saveOrder = (
  value: string | null,
  body: Record<string, unknown>,
) => save<PurchaseOrder>(resource.order, value, body);

export const listReceipts = (query: Record<string, string>) =>
  list<PurchaseReceipt>(resource.receipt, query);
export const getReceipt = (value: string) =>
  get<PurchaseReceipt>(resource.receipt, value);
export const saveReceipt = (
  value: string | null,
  body: Record<string, unknown>,
) => save<PurchaseReceipt>(resource.receipt, value, body);

export const procurementAction = <T>(
  name: string,
  value: string,
  action: "submit" | "approve" | "reject" | "confirm",
  reason = "",
) =>
  apiFetch<T>(`${base}/${name}/${id(value)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(action === "reject" ? { reason } : {}),
  });

export async function listExpenseAccounts() {
  const value = await apiFetch<ExpenseAccount[]>(
    "/api/reference/vendor-bill-accounts",
  );
  return Array.isArray(value) ? value : [];
}

export async function listProcurementVendors() {
  const value = await apiFetch<Page<VendorOption>>("/api/vendors", {
    query: { is_active: "true" },
  });
  return value.results;
}
