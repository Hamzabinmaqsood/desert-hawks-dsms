import { apiFetch } from "@/lib/api/client";

import type {
  InvoiceCreateInput,
  InvoiceDetail,
  InvoiceDraftUpdateInput,
  InvoiceLineWriteInput,
  InvoiceQuery,
  PaginatedResponse,
} from "./types";

export function listInvoices(query: InvoiceQuery = {}) {
  return apiFetch<PaginatedResponse<InvoiceDetail>>("/api/invoices", { query });
}

export function getInvoice(id: string) {
  return apiFetch<InvoiceDetail>(`/api/invoices/${encodeURIComponent(id)}`);
}

export async function downloadInvoice(id: string) {
  return apiFetch<Response>(
    `/api/invoices/${encodeURIComponent(id)}/download`,
    { responseType: "response" },
  );
}

export function createInvoice(input: InvoiceCreateInput) {
  return apiFetch<InvoiceDetail>("/api/invoices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateInvoiceDraft(id: string, input: InvoiceDraftUpdateInput) {
  return apiFetch<InvoiceDetail>(`/api/invoices/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function addInvoiceLine(id: string, input: InvoiceLineWriteInput) {
  return apiFetch<unknown>(`/api/invoices/${encodeURIComponent(id)}/lines`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateInvoiceLine(
  id: string,
  lineId: string,
  input: Partial<InvoiceLineWriteInput>,
) {
  return apiFetch<unknown>(
    `/api/invoices/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function deleteInvoiceLine(id: string, lineId: string) {
  return apiFetch<unknown>(
    `/api/invoices/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}`,
    { method: "DELETE" },
  );
}
