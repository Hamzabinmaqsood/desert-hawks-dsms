import type { ModuleId } from "@/lib/modules";

export interface ModuleCatalogItem {
  id: ModuleId;
  display_name: string;
  classification:
    "GENERAL_BUSINESS" | "SHARED_OPERATIONAL" | "SECURITY_VERTICAL";
  hard_dependencies: ModuleId[];
  legacy_default: boolean;
}

export interface PlatformPlan {
  id: string;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PlanEntitlements {
  plan_id: string;
  plan_code: string;
  plan_name: string;
  entitlement_revision: number;
  enabled_module_ids: ModuleId[];
  snapshot_notice: string;
}

export interface PlatformCompany {
  id: string;
  code: string;
  legal_name: string;
  trade_name: string;
  is_active: boolean;
  country_code: string;
  timezone: string;
  default_currency: string;
  operational_status: string;
  blocker_count: number;
  blocker_codes: string[];
  created_at: string;
}

export interface SubscriptionCompany {
  id: string;
  code: string;
  legal_name: string;
  trade_name: string;
  is_active: boolean;
}

export interface PlatformSubscription {
  id: string;
  company: SubscriptionCompany;
  plan: PlatformPlan;
  status: string;
  policy_mode: "LEGACY_FULL" | "SUBSCRIPTION";
  effective_module_count: number;
  entitlement_revision: number;
  starts_at: string;
  trial_ends_at: string | null;
  grace_ends_at: string | null;
  suspended_at: string | null;
  terminated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionOverride {
  module_id: ModuleId;
  state: "ENABLED" | "DISABLED";
}

export interface SubscriptionEntitlements {
  subscription_id: string;
  subscription_status: string;
  company: SubscriptionCompany;
  plan: PlatformPlan;
  policy_mode: "LEGACY_FULL" | "SUBSCRIPTION";
  plan_entitlement_revision: number;
  snapshot_plan_entitlement_revision: number | null;
  entitlement_revision: number;
  snapshot_initialized: boolean;
  plan_module_ids: ModuleId[];
  snapshot_module_ids: ModuleId[];
  overrides: SubscriptionOverride[];
  effective_module_ids: ModuleId[];
}

export interface ProvisioningResult {
  id: string;
  status: string;
  company: PlatformCompany | null;
  initial_admin: { id: string; email: string } | null;
}
