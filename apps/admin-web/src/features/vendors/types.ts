export interface Vendor {
  id: string;
  code: string;
  name: string;
  tax_number: string;
  email: string;
  phone: string;
  payment_terms_days: number;
  payable_account: string;
  payable_account_code: string;
  payable_account_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: Vendor[];
}

export interface VendorPayableAccount {
  id: string;
  code: string;
  name: string;
}

export const VENDOR_WRITE_FIELDS = [
  "code",
  "name",
  "tax_number",
  "email",
  "phone",
  "payment_terms_days",
  "payable_account",
  "is_active",
] as const;
