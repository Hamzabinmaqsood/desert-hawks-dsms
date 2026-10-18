import type { ModuleId } from "@/lib/modules";

export interface CurrentUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  last_login: string | null;
  date_joined: string;
  created_at: string;
  updated_at: string;
}

export interface AccessScopeAssignment {
  id: string;
  role_code: string;
  role_name: string;
  scope_type: string;
  company_id: string | null;
  region_id: string | null;
  branch_id: string | null;
  department_id: string | null;
  operational_zone_id: string | null;
}

export interface AccessScopes {
  is_superuser: boolean;
  accessible_company_ids: string[];
  accessible_region_ids: string[];
  accessible_branch_ids: string[];
  accessible_department_ids: string[];
  accessible_operational_zone_ids: string[];
  assignments: AccessScopeAssignment[];
}

export interface SelectableCompany {
  id: string;
  code: string;
  display_name: string;
  legal_name: string;
  is_active: boolean;
}

export interface CompanyBranding {
  display_name: string;
  tagline: string;
  primary_color: string;
  accent_color: string;
  can_manage: boolean;
}

export interface CompanyBusinessSettings {
  default_currency: string;
  timezone: string;
  invoice_number_prefix: string;
  receipt_number_prefix: string;
  credit_note_number_prefix: string;
  debit_note_number_prefix: string;
  can_manage: boolean;
}

export interface SelectedCompany extends SelectableCompany {
  branding?: CompanyBranding;
}

export interface CompanyContext {
  companies: SelectableCompany[];
  selected_company: SelectedCompany | null;
  selection_required: boolean;
  effective_modules: ModuleId[];
  entitlement_revision: number;
}

export interface CompanyContextBootstrap extends CompanyContext {
  user: CurrentUser;
}

export interface SessionData {
  authenticated: true;
  user: CurrentUser;
  permissions: string[];
  scopes: AccessScopes;
  platform_capabilities: PlatformCapabilities;
  company_context: CompanyContext;
}

export interface PlatformCapabilities {
  capabilities: string[];
  can_access_platform_admin: boolean;
}

export interface UnauthenticatedSession {
  authenticated: false;
}

export type SessionResponse = SessionData | UnauthenticatedSession;
