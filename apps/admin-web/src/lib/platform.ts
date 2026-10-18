export const PLATFORM_CAPABILITIES = {
  provisionTenant: "organization.provision_tenant",
  viewTenantProvisioning: "organization.view_tenant_provisioning",
  viewTenantDirectory: "organization.view_platform_tenant_directory",
  viewPlanCatalog: "subscriptions.view_plan_catalog",
  managePlanCatalog: "subscriptions.manage_plan_catalog",
  viewSubscriptions: "subscriptions.view_commercial_subscriptions",
  manageSubscriptions: "subscriptions.manage_commercial_subscriptions",
} as const;

export function hasPlatformCapability(
  capabilities: readonly string[],
  capability: string,
) {
  return capabilities.includes(capability);
}
