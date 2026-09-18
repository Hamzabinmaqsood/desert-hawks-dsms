import { apiFetch } from "@/lib/api/client";
import type {
  PayableBill,
  PaymentAccount,
  VendorPayment,
  VendorPaymentPage,
} from "./types";

export const listVendorPayments = (query: Record<string, string>) =>
  apiFetch<VendorPaymentPage>("/api/vendor-payments", { query });
export const getVendorPayment = (id: string) =>
  apiFetch<VendorPayment>(`/api/vendor-payments/${encodeURIComponent(id)}`);
export const createVendorPayment = (body: Record<string, unknown>) =>
  apiFetch<VendorPayment>("/api/vendor-payments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const runVendorPaymentAction = (
  id: string,
  action: "submit" | "approve" | "reject",
  reason = "",
) =>
  apiFetch<VendorPayment>(
    `/api/vendor-payments/${encodeURIComponent(id)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action === "reject" ? { reason } : {}),
    },
  );
export const payVendorPayment = (
  id: string,
  payment_account: string,
  payment_reference: string,
) =>
  apiFetch<VendorPayment>(
    `/api/vendor-payments/${encodeURIComponent(id)}/pay`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payment_account, payment_reference }),
    },
  );
export const listPayableBills = () =>
  apiFetch<PayableBill[]>("/api/reference/payable-bills");
export const listPaymentAccounts = () =>
  apiFetch<PaymentAccount[]>("/api/reference/payment-accounts");
