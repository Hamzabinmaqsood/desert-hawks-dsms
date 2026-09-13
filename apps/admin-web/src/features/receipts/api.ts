import { apiFetch } from "@/lib/api/client";

import type {
  EligibleInvoice,
  Receipt,
  ReceiptBankAccount,
  ReceiptClient,
  ReceiptPage,
} from "./types";

export function listReceipts(query: Record<string, string>) {
  return apiFetch<ReceiptPage>("/api/receipts", { query });
}

export function getReceipt(id: string) {
  return apiFetch<Receipt>(`/api/receipts/${encodeURIComponent(id)}`);
}

export function createReceipt(input: Record<string, unknown>) {
  return apiFetch<Receipt>("/api/receipts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function confirmReceipt(id: string) {
  return apiFetch<Receipt>(`/api/receipts/${encodeURIComponent(id)}/confirm`, {
    method: "POST",
  });
}

export function allocateReceipt(id: string, invoice: string, amount: string) {
  return apiFetch(`/api/receipts/${encodeURIComponent(id)}/allocate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invoice, amount }),
  });
}

export function listEligibleInvoices(id: string) {
  return apiFetch<EligibleInvoice[]>(
    `/api/receipts/${encodeURIComponent(id)}/eligible-invoices`,
  );
}

export async function listReceiptBankAccounts() {
  const body = await apiFetch<
    { results?: ReceiptBankAccount[] } | ReceiptBankAccount[]
  >("/api/reference/receipt-bank-accounts");
  return Array.isArray(body) ? body : (body.results ?? []);
}

export async function listReceiptClients() {
  const body = await apiFetch<{ results?: ReceiptClient[] } | ReceiptClient[]>(
    "/api/reference/receipt-clients",
  );
  return Array.isArray(body) ? body : (body.results ?? []);
}
