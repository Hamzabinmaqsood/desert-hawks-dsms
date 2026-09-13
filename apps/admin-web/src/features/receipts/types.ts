import type { PaginatedResponse } from "@/features/invoices/types";

export type ReceiptStatus =
  | "DRAFT"
  | "CONFIRMED"
  | "PARTIALLY_ALLOCATED"
  | "ALLOCATED"
  | "REVERSED"
  | "CANCELLED";

export interface ReceiptAllocation {
  id: string;
  invoice: string;
  invoice_number: string;
  amount: string;
  allocated_at: string;
}

export interface Receipt {
  id: string;
  receipt_number: string;
  company: string;
  client: string;
  client_name: string;
  received_at: string;
  value_date: string | null;
  currency: string;
  amount: string;
  payment_method: string;
  bank_account: string | null;
  cheque_reference: string;
  external_reference: string;
  status: ReceiptStatus;
  notes: string;
  allocated_amount: string;
  unallocated_amount: string;
  allocations: ReceiptAllocation[];
}

export interface EligibleInvoice {
  id: string;
  invoice_number: string;
  invoice_date: string;
  currency: string;
  total_amount: string;
  amount_paid: string;
  balance_due: string;
  status: string;
}

export interface ReceiptBankAccount {
  id: string;
  company: string;
  name: string;
  bank_name: string;
  currency: string;
}

export interface ReceiptClient {
  client: string;
  company: string;
  billing_name: string;
  currency: string;
}

export type ReceiptPage = PaginatedResponse<Receipt>;

export const RECEIPT_CREATE_FIELDS = [
  "company",
  "client",
  "received_at",
  "value_date",
  "currency",
  "amount",
  "payment_method",
  "bank_account",
  "cheque_reference",
  "external_reference",
  "notes",
] as const;

export const RECEIPT_ALLOCATION_FIELDS = ["invoice", "amount"] as const;

export const PAYMENT_METHODS = [
  ["BANK_TRANSFER", "Bank transfer"],
  ["EASYPAISA", "Easypaisa"],
  ["JAZZCASH", "JazzCash"],
  ["CHEQUE", "Cheque"],
  ["CASH", "Cash"],
  ["CARD", "Card"],
  ["ONLINE_GATEWAY", "Online gateway"],
  ["OTHER", "Other"],
] as const;
