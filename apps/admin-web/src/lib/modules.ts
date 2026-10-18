export const MODULE_IDS = [
  "people",
  "recruitment",
  "leave",
  "learning",
  "performance",
  "hr_case_management",
  "client_contracts",
  "finance_core",
  "billing_receivables",
  "procurement_payables",
  "payroll",
  "asset_management",
  "client_portal",
  "analytics",
  "workforce_scheduling",
  "attendance",
  "security_operations",
  "security_patrol",
  "security_supervision",
  "security_incidents",
] as const;

export type ModuleId = (typeof MODULE_IDS)[number];

export function hasModule(
  effectiveModules: readonly ModuleId[],
  moduleId: ModuleId,
) {
  return effectiveModules.includes(moduleId);
}

export function hasAllModules(
  effectiveModules: readonly ModuleId[],
  ...moduleIds: ModuleId[]
) {
  return moduleIds.every((moduleId) => hasModule(effectiveModules, moduleId));
}

export const MODULE_DISABLED_MESSAGE =
  "This module is not enabled for this Company.";
