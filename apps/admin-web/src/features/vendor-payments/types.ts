export interface VendorPayment {
  id: string;
  vendor_bill: string;
  bill_number: string;
  vendor_name: string;
  voucher_number: string;
  payment_date: string;
  amount: string;
  status: string;
  payment_status: string;
  payment_reference: string;
}

export interface VendorPaymentPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: VendorPayment[];
}

export interface PayableBill {
  id: string;
  bill_number: string;
  vendor_invoice_number: string;
  vendor_name: string;
  total_amount: string;
  paid_amount: string;
  outstanding_amount: string;
  status: string;
}

export interface PaymentAccount {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export const VENDOR_PAYMENT_FIELDS = [
  "vendor_bill",
  "voucher_number",
  "payment_date",
  "amount",
  "payment_reference",
] as const;
