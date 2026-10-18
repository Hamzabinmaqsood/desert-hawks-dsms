import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { AppShell } from "@/components/layout/app-shell";
import LoginPage, { metadata as loginMetadata } from "@/app/(auth)/login/page";
import { metadata as rootMetadata } from "@/app/layout";
import { AuthProvider } from "@/features/auth/auth-context";
import type { SessionData } from "@/lib/auth/types";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  usePathname: () => "/dashboard",
}));

const session: SessionData = {
  authenticated: true,
  user: {
    id: "user-1",
    email: "employee@example.test",
    first_name: "Test",
    last_name: "Employee",
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
    capabilities: [],
    can_access_platform_admin: false,
  },
  company_context: {
    effective_modules: ["billing_receivables"],
    entitlement_revision: 0,
    companies: [
      {
        id: "company-a",
        code: "A",
        display_name: "Company A",
        legal_name: "Company A Limited",
        is_active: true,
      },
    ],
    selected_company: {
      id: "company-a",
      code: "A",
      display_name: "Company A",
      legal_name: "Company A Limited",
      is_active: true,
    },
    selection_required: false,
  },
};

describe("authentication components", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("renders neutral platform identity on the login page", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("img", { name: "DSMS platform mark" }),
    ).toBeTruthy();
    expect(screen.getByText("Security Management Platform")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Desert Hawks");
    expect(loginMetadata.title).toBe("Sign in | DSMS");
    expect(rootMetadata.title).toBe("DSMS — Security Management Platform");
  });

  it("renders an accessible login form and disables it while submitting", async () => {
    let finish: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    render(<LoginForm />);
    expect(screen.getByLabelText("Work email")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Work email"), {
      target: { value: "employee@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Sign in" }).closest("form")!,
    );
    expect(
      (screen.getByRole("button", { name: "Signing in…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await act(async () =>
      finish?.(
        new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    expect(replace).toHaveBeenCalledWith("/dashboard");
  });

  it("shows a stable authentication error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ message: "Email or password is incorrect." }),
            { status: 401, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Work email"), {
      target: { value: "employee@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    await act(async () =>
      fireEvent.submit(
        screen.getByRole("button", { name: "Sign in" }).closest("form")!,
      ),
    );
    expect(screen.getByRole("alert").textContent).toContain("incorrect");
  });

  it("renders the authenticated shell, user, and permitted navigation", () => {
    render(
      <AuthProvider session={session}>
        <AppShell>
          <p>Protected content</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(screen.getByText("Test Employee")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(screen.getByText("Protected content")).toBeTruthy();
    expect(
      screen.getByRole("img", { name: "DSMS platform mark" }),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Invoices" })).toBeNull();
    expect(
      (screen.getByLabelText("Active Company") as HTMLSelectElement).value,
    ).toBe("company-a");
    expect(
      (screen.getByLabelText("Active Company") as HTMLSelectElement).disabled,
    ).toBe(true);
  });

  it("adopts server context changes after membership is revoked", async () => {
    const view = (currentSession: SessionData) => (
      <AuthProvider session={currentSession}>
        <AppShell>
          <p>Company A content</p>
        </AppShell>
      </AuthProvider>
    );
    const { rerender } = render(view(session));
    expect(screen.getByText("Company A content")).toBeTruthy();

    rerender(
      view({
        ...session,
        company_context: {
          effective_modules: [],
          entitlement_revision: 0,
          companies: [],
          selected_company: null,
          selection_required: false,
        },
      }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "No Company access" }),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("Company A content")).toBeNull();
  });

  it("shows Invoice navigation only with Invoice view permission", () => {
    render(
      <AuthProvider
        session={{ ...session, permissions: ["billing.view_clientinvoice"] }}
      >
        <AppShell>
          <p>Protected content</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(
      screen.getByRole("link", { name: "Invoices" }).getAttribute("href"),
    ).toBe("/invoices");
  });

  it("requires an explicit multi-company selection and refreshes at a neutral route", async () => {
    const companyB = {
      id: "company-b",
      code: "B",
      display_name: "Company B",
      legal_name: "Company B Limited",
      is_active: true,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              companies: [...session.company_context.companies, companyB],
              selected_company: companyB,
              selection_required: false,
              effective_modules: ["procurement_payables"],
              entitlement_revision: 2,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    render(
      <AuthProvider
        session={{
          ...session,
          company_context: {
            effective_modules: [],
            entitlement_revision: 0,
            companies: [...session.company_context.companies, companyB],
            selected_company: null,
            selection_required: true,
          },
        }}
      >
        <AppShell>
          <p>Tenant A data</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(
      screen.getByRole("heading", { name: "Select a Company" }),
    ).toBeTruthy();
    expect(screen.queryByText("Tenant A data")).toBeNull();

    fireEvent.change(screen.getByLabelText("Active Company"), {
      target: { value: "company-b" },
    });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(refresh).toHaveBeenCalledOnce();
    expect(
      (screen.getByLabelText("Active Company") as HTMLSelectElement).value,
    ).toBe("company-b");
  });

  it("disables switching while pending and preserves context on failure", async () => {
    const companyB = {
      id: "company-b",
      code: "B",
      display_name: "Company B",
      legal_name: "Company B Limited",
      is_active: true,
    };
    let finish: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    render(
      <AuthProvider
        session={{
          ...session,
          company_context: {
            effective_modules: session.company_context.effective_modules,
            entitlement_revision: session.company_context.entitlement_revision,
            companies: [...session.company_context.companies, companyB],
            selected_company: session.company_context.selected_company,
            selection_required: false,
          },
        }}
      >
        <AppShell>
          <p>Company A content</p>
        </AppShell>
      </AuthProvider>,
    );
    fireEvent.change(screen.getByLabelText("Active Company"), {
      target: { value: "company-b" },
    });
    expect(
      (screen.getByLabelText("Active Company") as HTMLSelectElement).disabled,
    ).toBe(true);
    await act(async () =>
      finish?.(
        new Response(JSON.stringify({ message: "Company is unavailable." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    expect(screen.getByRole("alert").textContent).toContain("unavailable");
    expect(
      (screen.getByLabelText("Active Company") as HTMLSelectElement).value,
    ).toBe("company-a");
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows a safe no-company state without inventing tenant options", () => {
    render(
      <AuthProvider
        session={{
          ...session,
          company_context: {
            effective_modules: [],
            entitlement_revision: 0,
            companies: [],
            selected_company: null,
            selection_required: false,
          },
        }}
      >
        <AppShell>
          <p>Hidden tenant content</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(
      screen.getByRole("heading", { name: "No Company access" }),
    ).toBeTruthy();
    expect(screen.queryByText("Hidden tenant content")).toBeNull();
    expect(screen.queryByText("Company B")).toBeNull();
  });
});
