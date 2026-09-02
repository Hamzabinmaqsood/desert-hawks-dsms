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

export interface SessionData {
  authenticated: true;
  user: CurrentUser;
  permissions: string[];
  scopes: AccessScopes;
}

export interface UnauthenticatedSession {
  authenticated: false;
}

export type SessionResponse = SessionData | UnauthenticatedSession;
