import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/app-shell";
import { AuthProvider } from "@/features/auth/auth-context";
import { DashboardContent } from "@/features/auth/dashboard-content";
import {
  DashboardWidgetBoard,
  type DashboardWidgetDefinition,
} from "@/features/auth/dashboard-widgets";
import type { SessionData } from "@/lib/auth/types";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace, refresh }),
}));

const companyA = {
  id: "company-a",
  code: "A",
  display_name: "Northstar Alpha",
  legal_name: "Northstar Alpha Limited",
  is_active: true,
};
const companyB = {
  id: "company-b",
  code: "B",
  display_name: "Northstar Bravo",
  legal_name: "Northstar Bravo Limited",
  is_active: true,
};

function session(
  overrides: Partial<SessionData> = {},
  selectedCompany = companyA,
): SessionData {
  return {
    authenticated: true,
    user: {
      id: "user-1",
      email: "operator@example.test",
      first_name: "Operations",
      last_name: "User",
      is_active: true,
      is_staff: false,
      is_superuser: false,
      last_login: null,
      date_joined: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    permissions: [
      "billing.view_clientinvoice",
      "billing.add_clientinvoice",
      "finance.view_vendor",
      "finance.add_vendor",
    ],
    scopes: {
      is_superuser: false,
      accessible_company_ids: [companyA.id, companyB.id],
      accessible_region_ids: [],
      accessible_branch_ids: [],
      accessible_department_ids: [],
      accessible_operational_zone_ids: [],
      assignments: [],
    },
    platform_capabilities: {
      capabilities: [],
      can_access_platform_admin: false,
    },
    company_context: {
      companies: [companyA, companyB],
      selected_company: selectedCompany,
      selection_required: false,
      effective_modules: ["billing_receivables", "procurement_payables"],
      entitlement_revision: 1,
    },
    ...overrides,
  };
}

function withSession(node: React.ReactNode, value = session()) {
  return render(<AuthProvider session={value}>{node}</AuthProvider>);
}

describe("product shell and dashboard foundation", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("renders customer-facing core widgets and only real authorized actions", () => {
    withSession(<DashboardContent />);
    expect(
      screen.getByRole("heading", { name: "Workspace overview" }),
    ).toBeTruthy();
    expect(screen.getByText("Northstar Alpha")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Review Company settings" }),
    ).toHaveProperty("href", "http://localhost:3000/settings/company");
    expect(
      screen.getByRole("link", { name: "Configure Company branding" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Create an invoice" }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Add a vendor" })).toBeTruthy();
    expect(document.body.textContent).not.toContain("workspace is ready");
    expect(document.body.textContent).not.toContain("Permission codes");
  });

  it("does not load disabled or permission-denied widgets", () => {
    const load = vi.fn(async () => "loaded");
    const widget: DashboardWidgetDefinition = {
      id: "billing-summary",
      title: "Billing summary",
      order: 1,
      moduleId: "billing_receivables",
      permissions: ["billing.view_clientinvoice"],
      load,
      render: (_context, data) => <p>{String(data)}</p>,
    };
    const noBilling = session({
      company_context: {
        ...session().company_context,
        effective_modules: ["procurement_payables"],
      },
    });
    const first = withSession(
      <DashboardWidgetBoard widgets={[widget]} />,
      noBilling,
    );
    expect(load).not.toHaveBeenCalled();
    first.unmount();
    withSession(
      <DashboardWidgetBoard widgets={[widget]} />,
      session({ permissions: [] }),
    );
    expect(load).not.toHaveBeenCalled();
  });

  it("renders an allowed async widget without letting one failure break another", async () => {
    const widgets: DashboardWidgetDefinition[] = [
      {
        id: "allowed",
        title: "Allowed widget",
        order: 1,
        load: async () => "Current Company result",
        render: (_context, data) => <p>{String(data)}</p>,
      },
      {
        id: "failed",
        title: "Failed widget",
        order: 2,
        load: async () => {
          throw new Error("private backend detail");
        },
        render: () => null,
      },
    ];
    withSession(<DashboardWidgetBoard widgets={widgets} />);
    expect(await screen.findByText("Current Company result")).toBeTruthy();
    expect(
      await screen.findByRole("heading", { name: "Failed widget unavailable" }),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain("private backend detail");
  });

  it("ignores an old Company widget result after context changes", async () => {
    const resolvers = new Map<string, (value: unknown) => void>();
    const widget: DashboardWidgetDefinition = {
      id: "switch-safe",
      title: "Switch-safe widget",
      order: 1,
      load: ({ companyId }) =>
        new Promise((resolve) => resolvers.set(companyId, resolve)),
      render: (_context, data) => <p>{String(data)}</p>,
    };
    const view = (value: SessionData) => (
      <AuthProvider session={value}>
        <DashboardWidgetBoard widgets={[widget]} />
      </AuthProvider>
    );
    const rendered = render(view(session()));
    await waitFor(() => expect(resolvers.has(companyA.id)).toBe(true));
    rendered.rerender(view(session({}, companyB)));
    await waitFor(() => expect(resolvers.has(companyB.id)).toBe(true));
    await act(async () => resolvers.get(companyB.id)?.("Bravo result"));
    expect(await screen.findByText("Bravo result")).toBeTruthy();
    await act(async () => resolvers.get(companyA.id)?.("Stale Alpha result"));
    expect(screen.queryByText("Stale Alpha result")).toBeNull();
  });

  it("supports an accessible mobile menu, Escape focus return, and active route", () => {
    withSession(
      <AppShell>
        <p>Dashboard body</p>
      </AppShell>,
    );
    const menu = screen.getByRole("button", { name: "Menu" });
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(menu);
    expect(
      screen
        .getByRole("button", { name: "Close menu" })
        .getAttribute("aria-expanded"),
    ).toBe("true");
    expect(
      screen
        .getByRole("link", { name: "Dashboard" })
        .getAttribute("aria-current"),
    ).toBe("page");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(menu);
    fireEvent.click(menu);
    const invoiceLink = screen.getByRole("link", { name: "Invoices" });
    invoiceLink.addEventListener("click", (event) => event.preventDefault(), {
      once: true,
    });
    fireEvent.click(invoiceLink);
    expect(menu.getAttribute("aria-expanded")).toBe("false");
  });
});
