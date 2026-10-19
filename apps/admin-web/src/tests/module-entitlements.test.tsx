import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModuleRouteGuard } from "@/components/auth/module-route-guard";
import { AppShell } from "@/components/layout/app-shell";
import {
  isNavigationItemVisible,
  navigation,
  visibleNavigationGroups,
} from "@/components/layout/sidebar";
import { AuthProvider } from "@/features/auth/auth-context";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { SessionData } from "@/lib/auth/types";
import { MODULE_IDS, hasAllModules, hasModule } from "@/lib/modules";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => "/invoices",
  useRouter: () => ({ replace, refresh }),
}));

const companyA = {
  id: "company-a",
  code: "A",
  display_name: "Company A",
  legal_name: "Company A Limited",
  is_active: true,
};
const companyB = {
  id: "company-b",
  code: "B",
  display_name: "Company B",
  legal_name: "Company B Limited",
  is_active: true,
};

const session: SessionData = {
  authenticated: true,
  user: {
    id: "user-1",
    email: "tenant@example.test",
    first_name: "Tenant",
    last_name: "User",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    last_login: null,
    date_joined: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  permissions: ["billing.view_clientinvoice", "finance.view_vendor"],
  scopes: {
    is_superuser: false,
    accessible_company_ids: [companyA.id, companyB.id],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
  platform_capabilities: { capabilities: [], can_access_platform_admin: false },
  company_context: {
    companies: [companyA, companyB],
    selected_company: companyA,
    selection_required: false,
    effective_modules: ["billing_receivables", "procurement_payables"],
    entitlement_revision: 4,
  },
};

describe("tenant module capability UX", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("uses one typed capability helper and preserves legacy full catalog behavior", () => {
    expect(hasModule(MODULE_IDS, "billing_receivables")).toBe(true);
    expect(
      hasAllModules(MODULE_IDS, "billing_receivables", "procurement_payables"),
    ).toBe(true);
    expect(hasModule(["procurement_payables"], "billing_receivables")).toBe(
      false,
    );
  });

  it("requires both module entitlement and tenant RBAC for navigation", () => {
    const invoices = navigation.find((item) => item.href === "/invoices")!;
    expect(
      isNavigationItemVisible(
        invoices,
        ["billing.view_clientinvoice"],
        ["billing_receivables"],
        false,
      ),
    ).toBe(true);
    expect(
      isNavigationItemVisible(invoices, [], ["billing_receivables"], false),
    ).toBe(false);
    expect(
      isNavigationItemVisible(
        invoices,
        ["billing.view_clientinvoice"],
        ["procurement_payables"],
        false,
      ),
    ).toBe(false);
    const apOnlyGroups = visibleNavigationGroups(
      ["finance.view_vendor"],
      ["procurement_payables"],
      false,
    );
    expect(apOnlyGroups.find((group) => group.id === "finance")?.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ label: "Vendors" })]),
    );
    expect(
      apOnlyGroups
        .find((group) => group.id === "finance")
        ?.items.some((item) => item.label === "Invoices"),
    ).toBe(false);
  });

  it("blocks a direct disabled route before module content mounts", () => {
    render(
      <AuthProvider
        session={{
          ...session,
          company_context: {
            ...session.company_context,
            effective_modules: ["procurement_payables"],
          },
        }}
      >
        <ModuleRouteGuard moduleId="billing_receivables">
          <p>Invoice secret content</p>
        </ModuleRouteGuard>
      </AuthProvider>,
    );
    expect(
      screen.getByRole("heading", { name: "Module unavailable" }),
    ).toBeTruthy();
    expect(screen.queryByText("Invoice secret content")).toBeNull();
  });

  it("replaces A capabilities with B capabilities and never unions them", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              companies: [companyA, companyB],
              selected_company: companyB,
              selection_required: false,
              effective_modules: ["procurement_payables"],
              entitlement_revision: 9,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    render(
      <AuthProvider session={session}>
        <AppShell>
          <ModuleRouteGuard moduleId="billing_receivables">
            <p>Company A invoice content</p>
          </ModuleRouteGuard>
        </AppShell>
      </AuthProvider>,
    );
    expect(screen.getByRole("link", { name: "Invoices" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Vendors" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Active Company"), {
      target: { value: companyB.id },
    });
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "Invoices" })).toBeNull(),
    );
    expect(screen.getByRole("link", { name: "Vendors" })).toBeTruthy();
    expect(screen.queryByText("Company A invoice content")).toBeNull();
    expect(
      screen.getByRole("heading", { name: "Module unavailable" }),
    ).toBeTruthy();
    expect(replace).toHaveBeenCalledWith("/dashboard");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("treats module_not_enabled as a product condition and refreshes capabilities", async () => {
    const entitlementChange = vi.fn();
    window.addEventListener("dsms:module-not-enabled", entitlementChange, {
      once: true,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              code: ["module_not_enabled"],
              non_field_errors: [
                "This module is not enabled for this Company.",
              ],
            }),
            { status: 403, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    await expect(apiFetch("/api/invoices")).rejects.toMatchObject({
      status: 403,
      code: "module_not_enabled",
      message: "This module is not enabled for this Company.",
    } satisfies Partial<ApiError>);
    expect(entitlementChange).toHaveBeenCalledOnce();
  });
});
