import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlatformRouteGuard } from "@/components/auth/platform-route-guard";
import { AuthProvider } from "@/features/auth/auth-context";
import {
  CompanyListPage,
  PlanDetailPage,
  SubscriptionDetailPage,
} from "@/features/platform/pages";
import type {
  ModuleCatalogItem,
  SubscriptionEntitlements,
} from "@/features/platform/types";
import type { SessionData } from "@/lib/auth/types";
import { PLATFORM_CAPABILITIES } from "@/lib/platform";

const api = vi.hoisted(() => ({
  activateEntitlements: vi.fn(),
  applyPlanRevision: vi.fn(),
  createPlan: vi.fn(),
  createSubscription: vi.fn(),
  getPlanEntitlements: vi.fn(),
  getSubscriptionEntitlements: vi.fn(),
  listCompanies: vi.fn(),
  listModules: vi.fn(),
  listPlans: vi.fn(),
  listSubscriptions: vi.fn(),
  provisionCompany: vi.fn(),
  replaceOverrides: vi.fn(),
  updatePlanEntitlements: vi.fn(),
}));

vi.mock("@/features/platform/api", () => api);
vi.mock("next/navigation", () => ({
  usePathname: () => "/platform/plans/plan-1",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

const catalog: ModuleCatalogItem[] = [
  {
    id: "people",
    display_name: "People & Employee Records",
    classification: "GENERAL_BUSINESS",
    hard_dependencies: [],
    legacy_default: true,
  },
  {
    id: "client_contracts",
    display_name: "Clients & Contracts",
    classification: "GENERAL_BUSINESS",
    hard_dependencies: [],
    legacy_default: true,
  },
  {
    id: "finance_core",
    display_name: "Finance & Accounting",
    classification: "GENERAL_BUSINESS",
    hard_dependencies: [],
    legacy_default: true,
  },
  {
    id: "billing_receivables",
    display_name: "Billing & Receivables",
    classification: "GENERAL_BUSINESS",
    hard_dependencies: ["client_contracts", "finance_core"],
    legacy_default: true,
  },
  {
    id: "security_operations",
    display_name: "Security Operations",
    classification: "SECURITY_VERTICAL",
    hard_dependencies: ["people", "client_contracts"],
    legacy_default: true,
  },
];

const company = {
  id: "company-1",
  code: "ACME",
  legal_name: "Acme Limited",
  trade_name: "Acme",
  is_active: true,
};
const plan = {
  id: "plan-1",
  code: "GROWTH",
  name: "Growth",
  description: "",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const subscriptionState: SubscriptionEntitlements = {
  subscription_id: "subscription-1",
  subscription_status: "ACTIVE",
  company,
  plan,
  policy_mode: "SUBSCRIPTION",
  plan_entitlement_revision: 4,
  snapshot_plan_entitlement_revision: 3,
  entitlement_revision: 8,
  snapshot_initialized: true,
  plan_module_ids: [
    "people",
    "client_contracts",
    "finance_core",
    "billing_receivables",
  ],
  snapshot_module_ids: [
    "people",
    "client_contracts",
    "finance_core",
    "billing_receivables",
  ],
  overrides: [{ module_id: "billing_receivables", state: "ENABLED" }],
  effective_module_ids: [
    "people",
    "client_contracts",
    "finance_core",
    "billing_receivables",
  ],
};

const platformSession: SessionData = {
  authenticated: true,
  user: {
    id: "operator-1",
    email: "operator@example.test",
    first_name: "Platform",
    last_name: "Operator",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    last_login: null,
    date_joined: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  permissions: [],
  scopes: {
    is_superuser: false,
    accessible_company_ids: [],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
  platform_capabilities: {
    capabilities: Object.values(PLATFORM_CAPABILITIES),
    can_access_platform_admin: true,
  },
  company_context: {
    companies: [],
    selected_company: null,
    selection_required: false,
    effective_modules: [],
    entitlement_revision: 0,
  },
};

function withAuth(node: React.ReactNode, session = platformSession) {
  return render(<AuthProvider session={session}>{node}</AuthProvider>);
}

describe("platform module administration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listModules.mockResolvedValue(catalog);
    api.getPlanEntitlements.mockResolvedValue({
      plan_id: plan.id,
      plan_code: plan.code,
      plan_name: plan.name,
      entitlement_revision: 4,
      enabled_module_ids: [
        "people",
        "client_contracts",
        "finance_core",
        "billing_receivables",
      ],
      snapshot_notice:
        "Plan updated; existing subscriptions retain their current snapshot until explicitly updated.",
    });
    api.getSubscriptionEntitlements.mockResolvedValue(subscriptionState);
    api.listCompanies.mockResolvedValue([
      {
        ...company,
        country_code: "PK",
        timezone: "Asia/Karachi",
        default_currency: "PKR",
        operational_status: "READY",
        blocker_count: 0,
        blocker_codes: [],
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    api.listSubscriptions.mockResolvedValue([
      {
        id: subscriptionState.subscription_id,
        company,
        plan,
        status: "ACTIVE",
        policy_mode: "SUBSCRIPTION",
        effective_module_count: 4,
        entitlement_revision: 8,
        starts_at: "2026-01-01T00:00:00Z",
        trial_ends_at: null,
        grace_ends_at: null,
        suspended_at: null,
        terminated_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
  });
  afterEach(() => cleanup());

  it("denies direct platform rendering without an explicit platform capability", () => {
    withAuth(
      <PlatformRouteGuard>
        <p>Commercial data</p>
      </PlatformRouteGuard>,
      {
        ...platformSession,
        platform_capabilities: {
          capabilities: [],
          can_access_platform_admin: false,
        },
      },
    );
    expect(
      screen.getByRole("heading", {
        name: "Platform administration unavailable",
      }),
    ).toBeTruthy();
    expect(screen.queryByText("Commercial data")).toBeNull();
  });

  it("renders the Company directory with Plan and lifecycle state", async () => {
    withAuth(<CompanyListPage />);
    expect(await screen.findByText("Acme")).toBeTruthy();
    expect(screen.getByText("Growth")).toBeTruthy();
    expect(screen.getByText("ACTIVE")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Open" }).getAttribute("href"),
    ).toBe("/platform/companies/company-1");
  });

  it("shows Plan snapshot safety and prevents an invalid dependency draft", async () => {
    withAuth(<PlanDetailPage planId={plan.id} />);
    expect(
      await screen.findByText(
        /does not update existing Subscription snapshots/,
      ),
    ).toBeTruthy();
    fireEvent.click(
      screen
        .getByText("Finance & Accounting", { selector: "strong" })
        .closest("label")!
        .querySelector("input")!,
    );
    expect(
      await screen.findByText(
        "Billing & Receivables requires Finance & Accounting.",
      ),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Save Plan modules",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("shows override provenance and a Plan revision mismatch", async () => {
    withAuth(<SubscriptionDetailPage subscriptionId="subscription-1" />);
    expect(await screen.findByText("Plan update available")).toBeTruthy();
    expect(
      (
        screen.getByLabelText(
          "Billing & Receivables source",
        ) as HTMLSelectElement
      ).value,
    ).toBe("ENABLED");
    expect(
      screen.getByRole("button", { name: "Apply latest Plan configuration" }),
    ).toBeTruthy();
  });

  it("presents LEGACY_FULL activation explicitly without auto-conversion", async () => {
    api.getSubscriptionEntitlements.mockResolvedValue({
      ...subscriptionState,
      policy_mode: "LEGACY_FULL",
      snapshot_plan_entitlement_revision: null,
      snapshot_initialized: false,
      snapshot_module_ids: [],
      overrides: [],
      entitlement_revision: 0,
    });
    withAuth(<SubscriptionDetailPage subscriptionId="subscription-1" />);
    expect(await screen.findByText("Legacy full access")).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "Activate module-based subscription access",
      }),
    ).toBeTruthy();
    expect(api.activateEntitlements).not.toHaveBeenCalled();
  });
});
