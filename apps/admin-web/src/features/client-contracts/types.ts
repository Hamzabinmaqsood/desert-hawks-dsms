export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Industry {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}

export interface Client {
  id: string;
  company: string;
  client_code: string;
  legal_name: string;
  trade_name: string;
  industry: string;
  industry_name: string;
  registration_number: string;
  tax_number: string;
  website: string;
  main_email: string;
  main_phone: string;
  billing_address: string;
  head_office_address: string;
  city: string;
  province_or_state: string;
  country_code: string;
  status: string;
  notes: string;
  account_manager: string | null;
  account_manager_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientContact {
  id: string;
  client: string;
  name: string;
  designation: string;
  department: string;
  email: string;
  mobile_number: string;
  office_phone: string;
  contact_type: string;
  is_primary: boolean;
  notes: string;
  is_active: boolean;
}

export interface Contract {
  id: string;
  company: string;
  client: string;
  client_name: string;
  contract_number: string;
  contract_type: string;
  title: string;
  description: string;
  signed_date: string | null;
  start_date: string;
  end_date: string | null;
  notice_period_days: number | null;
  auto_renew: boolean;
  currency: string;
  status: string;
  client_reference: string;
  purchase_order_reference: string;
  internal_reference: string;
  primary_client_contact: string | null;
  primary_client_contact_name: string | null;
  account_manager: string | null;
  account_manager_name: string | null;
  approved_at: string | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContractService {
  id: string;
  contract: string;
  service_type: string;
  name: string;
  description: string;
  start_date: string | null;
  end_date: string | null;
  is_active: boolean;
}

export interface CommercialTerms {
  id: string;
  contract: string;
  billing_frequency: string;
  agreed_contract_value: string | null;
  monthly_service_value: string | null;
  payment_terms_days: number | null;
  security_deposit: string | null;
  notes: string;
}

export interface Amendment {
  id: string;
  amendment_number: number;
  effective_date: string;
  title: string;
  description: string;
  change_type: string;
  revised_end_date: string | null;
  revised_value: string | null;
  approved_at: string;
}

export interface ServiceLevel {
  id: string;
  contract: string;
  site: null;
  sla_type: string;
  name: string;
  description: string;
  target_value: string | null;
  target_unit: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}
