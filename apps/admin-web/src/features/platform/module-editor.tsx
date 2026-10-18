"use client";

import type { ModuleId } from "@/lib/modules";

import type { ModuleCatalogItem, SubscriptionOverride } from "./types";

const GROUPS = [
  {
    label: "People",
    ids: [
      "people",
      "recruitment",
      "leave",
      "learning",
      "performance",
      "hr_case_management",
      "payroll",
    ],
  },
  {
    label: "Commercial / Clients",
    ids: ["client_contracts", "billing_receivables", "client_portal"],
  },
  {
    label: "Finance & Operations",
    ids: [
      "finance_core",
      "procurement_payables",
      "asset_management",
      "analytics",
    ],
  },
  {
    label: "Workforce Operations",
    ids: ["workforce_scheduling", "attendance"],
  },
  {
    label: "Security Operations",
    ids: [
      "security_operations",
      "security_patrol",
      "security_supervision",
      "security_incidents",
    ],
  },
] satisfies { label: string; ids: ModuleId[] }[];

export function dependencyIssues(
  catalog: ModuleCatalogItem[],
  enabledIds: readonly ModuleId[],
) {
  const enabled = new Set(enabledIds);
  return catalog.flatMap((module) =>
    enabled.has(module.id)
      ? module.hard_dependencies
          .filter((dependency) => !enabled.has(dependency))
          .map(
            (dependency) =>
              `${module.display_name} requires ${catalog.find((item) => item.id === dependency)?.display_name ?? dependency}.`,
          )
      : [],
  );
}

export function PlanModuleEditor({
  catalog,
  enabledIds,
  onChange,
  disabled = false,
}: {
  catalog: ModuleCatalogItem[];
  enabledIds: ModuleId[];
  onChange: (moduleIds: ModuleId[]) => void;
  disabled?: boolean;
}) {
  const enabled = new Set(enabledIds);
  const toggle = (moduleId: ModuleId) => {
    const next = new Set(enabled);
    if (next.has(moduleId)) next.delete(moduleId);
    else next.add(moduleId);
    onChange(
      catalog.filter((item) => next.has(item.id)).map((item) => item.id),
    );
  };
  return (
    <div className="module-groups">
      {GROUPS.map((group) => (
        <fieldset className="module-group" key={group.label}>
          <legend>{group.label}</legend>
          {group.ids.map((moduleId) => {
            const catalogItem = catalog.find((item) => item.id === moduleId);
            if (!catalogItem) return null;
            return (
              <label className="module-row" key={catalogItem.id}>
                <input
                  type="checkbox"
                  checked={enabled.has(catalogItem.id)}
                  disabled={disabled}
                  onChange={() => toggle(catalogItem.id)}
                />
                <span>
                  <strong>{catalogItem.display_name}</strong>
                  <small>
                    {catalogItem.hard_dependencies.length
                      ? `Requires: ${catalogItem.hard_dependencies
                          .map(
                            (id) =>
                              catalog.find((item) => item.id === id)
                                ?.display_name ?? id,
                          )
                          .join(", ")}`
                      : "No hard dependencies"}
                  </small>
                </span>
              </label>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}

export function SubscriptionModuleEditor({
  catalog,
  snapshotIds,
  overrides,
  onChange,
  disabled = false,
}: {
  catalog: ModuleCatalogItem[];
  snapshotIds: ModuleId[];
  overrides: SubscriptionOverride[];
  onChange: (overrides: SubscriptionOverride[]) => void;
  disabled?: boolean;
}) {
  const overrideMap = new Map(
    overrides.map((item) => [item.module_id, item.state]),
  );
  const setState = (moduleId: ModuleId, state: string) => {
    const next = new Map(overrideMap);
    if (state === "INHERITED") next.delete(moduleId);
    else next.set(moduleId, state as "ENABLED" | "DISABLED");
    onChange(
      catalog.flatMap((item) => {
        const value = next.get(item.id);
        return value ? [{ module_id: item.id, state: value }] : [];
      }),
    );
  };
  return (
    <div className="module-groups">
      {GROUPS.map((group) => (
        <fieldset className="module-group" key={group.label}>
          <legend>{group.label}</legend>
          {group.ids.map((moduleId) => {
            const catalogItem = catalog.find((item) => item.id === moduleId);
            if (!catalogItem) return null;
            const inherited = snapshotIds.includes(moduleId);
            const state = overrideMap.get(moduleId) ?? "INHERITED";
            return (
              <label
                className="module-row module-row-select"
                key={catalogItem.id}
              >
                <span>
                  <strong>{catalogItem.display_name}</strong>
                  <small>
                    Snapshot: {inherited ? "Enabled" : "Disabled"}
                    {catalogItem.hard_dependencies.length
                      ? ` · Requires ${catalogItem.hard_dependencies.join(", ")}`
                      : ""}
                  </small>
                </span>
                <select
                  aria-label={`${catalogItem.display_name} source`}
                  value={state}
                  disabled={disabled}
                  onChange={(event) =>
                    setState(catalogItem.id, event.target.value)
                  }
                >
                  <option value="INHERITED">Inherited from snapshot</option>
                  <option value="ENABLED">Override enabled</option>
                  <option value="DISABLED">Override disabled</option>
                </select>
              </label>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}

export function effectiveFromDraft(
  catalog: ModuleCatalogItem[],
  snapshotIds: ModuleId[],
  overrides: SubscriptionOverride[],
) {
  const enabled = new Set(snapshotIds);
  for (const override of overrides) {
    if (override.state === "ENABLED") enabled.add(override.module_id);
    else enabled.delete(override.module_id);
  }
  return catalog.filter((item) => enabled.has(item.id)).map((item) => item.id);
}
