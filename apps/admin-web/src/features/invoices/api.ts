import { apiFetch } from "@/lib/api/client";

import type { InvoiceDetail, InvoiceQuery, PaginatedResponse } from "./types";

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
