import { apiFetch } from "@/lib/api/client";
import type { ModuleId } from "@/lib/modules";

import type {
  ModuleCatalogItem,
  PlanEntitlements,
  PlatformCompany,
  PlatformPlan,
  PlatformSubscription,
  ProvisioningResult,
  SubscriptionEntitlements,
} from "./types";

const json = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listModules = () =>
  apiFetch<ModuleCatalogItem[]>("/api/platform/modules");
export const listPlans = () => apiFetch<PlatformPlan[]>("/api/platform/plans");
export const listSubscriptions = () =>
  apiFetch<PlatformSubscription[]>("/api/platform/subscriptions");
export const listCompanies = () =>
  apiFetch<PlatformCompany[]>("/api/platform/tenants");

export const createPlan = (payload: {
  code: string;
  name: string;
  description: string;
}) =>
  apiFetch<PlatformPlan>("/api/platform/plans", {
    method: "POST",
    ...json(payload),
  });

export const getPlanEntitlements = (planId: string) =>
  apiFetch<PlanEntitlements>(`/api/platform/plans/${planId}/entitlements`);
export const updatePlanEntitlements = (
  planId: string,
  enabledModuleIds: ModuleId[],
  reason: string,
) =>
  apiFetch<PlanEntitlements>(`/api/platform/plans/${planId}/entitlements`, {
    method: "PUT",
    ...json({ enabled_module_ids: enabledModuleIds, reason }),
  });

export const createSubscription = (payload: {
  company_id: string;
  plan_id: string;
  status: "ACTIVE" | "TRIAL";
  trial_ends_at?: string;
  reason: string;
}) =>
  apiFetch<PlatformSubscription>("/api/platform/subscriptions", {
    method: "POST",
    ...json(payload),
  });

export const getSubscriptionEntitlements = (subscriptionId: string) =>
  apiFetch<SubscriptionEntitlements>(
    `/api/platform/subscriptions/${subscriptionId}/entitlements`,
  );

export const replaceOverrides = (
  subscriptionId: string,
  enabledModuleIds: ModuleId[],
  disabledModuleIds: ModuleId[],
  reason: string,
) =>
  apiFetch<SubscriptionEntitlements>(
    `/api/platform/subscriptions/${subscriptionId}/overrides`,
    {
      method: "PUT",
      ...json({
        enabled_module_ids: enabledModuleIds,
        disabled_module_ids: disabledModuleIds,
        reason,
      }),
    },
  );

export const applyPlanRevision = (subscriptionId: string, reason: string) =>
  apiFetch<SubscriptionEntitlements>(
    `/api/platform/subscriptions/${subscriptionId}/apply-plan-revision`,
    { method: "POST", ...json({ reason }) },
  );

export const activateEntitlements = (
  subscriptionId: string,
  enabledModuleIds: ModuleId[],
  disabledModuleIds: ModuleId[],
  reason: string,
) =>
  apiFetch<SubscriptionEntitlements>(
    `/api/platform/subscriptions/${subscriptionId}/activate-entitlements`,
    {
      method: "POST",
      ...json({
        enabled_module_ids: enabledModuleIds,
        disabled_module_ids: disabledModuleIds,
        reason,
      }),
    },
  );

export const provisionCompany = (payload: {
  idempotency_key: string;
  company: {
    code: string;
    legal_name: string;
    country_code: string;
    timezone: string;
    default_currency: string;
  };
  initial_admin: { email: string };
}) =>
  apiFetch<ProvisioningResult>("/api/platform/provisioning", {
    method: "POST",
    ...json(payload),
  });
