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
import { BrandingSettings } from "@/features/branding/branding-settings";
import type { CompanyBranding, SessionData } from "@/lib/auth/types";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  usePathname: () => "/settings/branding",
}));

const alphaBranding: CompanyBranding = {
  display_name: "Alpha Shield",
  tagline: "Alpha operations",
  primary_color: "#123456",
  accent_color: "#ABCDEF",
  can_manage: true,
};

function session(branding: CompanyBranding = alphaBranding): SessionData {
  const company = {
    id: "company-a",
    code: "A",
    display_name: "Company A",
    legal_name: "Company A Limited",
    is_active: true,
    branding,
  };
  return {
    authenticated: true,
    user: {
      id: "user-1",
      email: "admin@example.test",
      first_name: "Brand",
      last_name: "Admin",
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
      accessible_company_ids: [company.id],
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
      effective_modules: [],
      entitlement_revision: 0,
      companies: [company],
      selected_company: company,
      selection_required: false,
    },
  };
}

describe("Company branding", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders selected Company branding and a tenant-aware document title", async () => {
    const { container } = render(
      <AuthProvider session={session()}>
        <AppShell>
          <p>Tenant content</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(screen.getByText("Alpha Shield")).toBeTruthy();
    expect(screen.getByText("Alpha operations")).toBeTruthy();
    expect(
      container.querySelector(".app-shell")?.getAttribute("style"),
    ).toContain("--tenant-brand: #123456");
    await waitFor(() => expect(document.title).toBe("Alpha Shield — DSMS"));
  });

  it("uses stable product colors and tagline when legacy context lacks branding", () => {
    const fallback = session();
    delete fallback.company_context.selected_company?.branding;
    const { container } = render(
      <AuthProvider session={fallback}>
        <AppShell>
          <p>Tenant content</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(screen.getByText("Company A")).toBeTruthy();
    expect(screen.getByText("Digital Transformation System")).toBeTruthy();
    expect(
      container.querySelector(".app-shell")?.getAttribute("style"),
    ).toContain("--tenant-brand: #174D34");
  });

  it("is read-only without Company-scoped branding permission", () => {
    render(
      <AuthProvider session={session({ ...alphaBranding, can_manage: false })}>
        <BrandingSettings />
      </AuthProvider>,
    );
    expect(screen.getByRole("status").textContent).toContain(
      "do not have permission",
    );
    expect(
      (screen.getByLabelText("Display name") as HTMLInputElement).disabled,
    ).toBe(true);
    expect(screen.queryByRole("button", { name: "Save branding" })).toBeNull();
  });

  it("rejects unsafe colors client-side without making a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AuthProvider session={session()}>
        <BrandingSettings />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByLabelText("Primary color (#RRGGBB)"), {
      target: { value: "url(evil)" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save branding" }));
    expect(
      await screen.findByText("Enter a color in #RRGGBB format."),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("normalizes and saves the explicit field allowlist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(alphaBranding), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    render(
      <AuthProvider session={session()}>
        <BrandingSettings />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "  Updated Alpha  " },
    });
    fireEvent.change(screen.getByLabelText("Primary color (#RRGGBB)"), {
      target: { value: "#a1b2c3" },
    });
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Save branding" })),
    );
    const fetchMock = vi.mocked(fetch);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      display_name: "Updated Alpha",
      primary_color: "#A1B2C3",
    });
    expect(await screen.findByText("Company branding saved.")).toBeTruthy();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("replaces A branding with B after a validated Company switch", async () => {
    const companyB = {
      id: "company-b",
      code: "B",
      display_name: "Company B",
      legal_name: "Company B Limited",
      is_active: true,
      branding: {
        ...alphaBranding,
        display_name: "Bravo Guard",
        tagline: "Bravo operations",
        primary_color: "#654321",
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              companies: [...session().company_context.companies, companyB],
              selected_company: companyB,
              selection_required: false,
              effective_modules: [],
              entitlement_revision: 1,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    const multi = session();
    multi.company_context.companies.push(companyB);
    render(
      <AuthProvider session={multi}>
        <AppShell>
          <p>Tenant content</p>
        </AppShell>
      </AuthProvider>,
    );
    expect(screen.getByText("Alpha Shield")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Active Company"), {
      target: { value: "company-b" },
    });
    await waitFor(() => expect(screen.getByText("Bravo Guard")).toBeTruthy());
    expect(screen.queryByText("Alpha Shield")).toBeNull();
    expect(screen.getByText("Bravo operations")).toBeTruthy();
  });

  it("removes stale branding when the server revokes Company context", () => {
    const view = (current: SessionData) => (
      <AuthProvider session={current}>
        <AppShell>
          <p>Tenant content</p>
        </AppShell>
      </AuthProvider>
    );
    const { rerender } = render(view(session()));
    expect(screen.getByText("Alpha Shield")).toBeTruthy();
    rerender(
      view({
        ...session(),
        company_context: {
          effective_modules: [],
          entitlement_revision: 0,
          companies: [],
          selected_company: null,
          selection_required: false,
        },
      }),
    );
    expect(screen.queryByText("Alpha Shield")).toBeNull();
    expect(
      screen.getByRole("heading", { name: "No Company access" }),
    ).toBeTruthy();
  });
});
