import { apiFetch } from "@/lib/api/client";
import type { Vendor, VendorPage, VendorPayableAccount } from "./types";

export const listVendors = (query: Record<string, string>) =>
  apiFetch<VendorPage>("/api/vendors", { query });

export const getVendor = (id: string) =>
  apiFetch<Vendor>(`/api/vendors/${encodeURIComponent(id)}`);

export const createVendor = (body: Record<string, unknown>) =>
  apiFetch<Vendor>("/api/vendors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const updateVendor = (id: string, body: Record<string, unknown>) =>
  apiFetch<Vendor>(`/api/vendors/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export async function listVendorPayableAccounts() {
  const body = await apiFetch<VendorPayableAccount[]>(
    "/api/reference/vendor-payable-accounts",
  );
  return Array.isArray(body) ? body : [];
}
