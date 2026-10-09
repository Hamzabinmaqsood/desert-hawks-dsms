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
import { CompanyBusinessSettings } from "@/features/company-settings/company-business-settings";
import type {
  CompanyBusinessSettings as Settings,
  SessionData,
} from "@/lib/auth/types";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  usePathname: () => "/settings/company",
}));

const alpha: Settings = {
  default_currency: "USD",
  timezone: "America/New_York",
  invoice_number_prefix: "AINV",
  receipt_number_prefix: "AREC",
  credit_note_number_prefix: "ACN",
  debit_note_number_prefix: "ADN",
  can_manage: true,
};

function session(): SessionData {
  const companyA = {
    id: "company-a",
    code: "A",
    display_name: "Company A",
    legal_name: "Company A Limited",
    is_active: true,
  };
  return {
    authenticated: true,
    user: {
      id: "user-1",
      email: "admin@example.test",
      first_name: "Company",
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
      accessible_company_ids: [companyA.id],
      accessible_region_ids: [],
      accessible_branch_ids: [],
      accessible_department_ids: [],
      accessible_operational_zone_ids: [],
      assignments: [],
    },
    company_context: {
      companies: [companyA],
      selected_company: companyA,
      selection_required: false,
    },
  };
}

function renderSettings(current = session()) {
  return render(
    <AuthProvider session={current}>
      <CompanyBusinessSettings />
    </AuthProvider>,
  );
}

describe("Company business settings", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads the selected Company settings in read-only mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ ...alpha, can_manage: false })),
    );
    renderSettings();
    expect(await screen.findByDisplayValue("USD")).toBeTruthy();
    expect(screen.getByDisplayValue("AINV")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain(
      "do not have permission",
    );
    expect(
      (screen.getByLabelText("Default currency") as HTMLInputElement).disabled,
    ).toBe(true);
    expect(
      screen.queryByRole("button", { name: "Save business settings" }),
    ).toBeNull();
  });

  it("rejects invalid currency and prefix values before PATCH", async () => {
    const fetchMock = vi.fn(async () => Response.json(alpha));
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();
    await screen.findByDisplayValue("USD");
    fireEvent.change(screen.getByLabelText("Default currency"), {
      target: { value: "US" },
    });
    fireEvent.change(screen.getByLabelText("Invoice prefix"), {
      target: { value: "../INV" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save business settings" }),
    );
    expect(
      await screen.findByText("Enter a three-letter currency code."),
    ).toBeTruthy();
    expect(
      screen.getByText("Enter a valid 1-10 character prefix."),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects duplicate document-family prefixes before PATCH", async () => {
    const fetchMock = vi.fn(async () => Response.json(alpha));
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();
    await screen.findByDisplayValue("AINV");
    fireEvent.change(screen.getByLabelText("Receipt prefix"), {
      target: { value: "ainv" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save business settings" }),
    );
    expect(
      await screen.findAllByText(
        "Use a unique prefix for each document family.",
      ),
    ).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("normalizes and saves the explicit settings allowlist", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json(alpha))
      .mockResolvedValueOnce(
        Response.json({
          ...alpha,
          default_currency: "AED",
          invoice_number_prefix: "A-INV",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();
    await screen.findByDisplayValue("USD");
    fireEvent.change(screen.getByLabelText("Default currency"), {
      target: { value: "aed" },
    });
    fireEvent.change(screen.getByLabelText("Invoice prefix"), {
      target: { value: "a-inv" },
    });
    await act(async () =>
      fireEvent.click(
        screen.getByRole("button", { name: "Save business settings" }),
      ),
    );
    const request = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      default_currency: "AED",
      invoice_number_prefix: "A-INV",
    });
    expect(
      await screen.findByText("Company business settings saved."),
    ).toBeTruthy();
  });

  it("shows backend field validation without losing the current Company", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json(alpha))
      .mockResolvedValueOnce(
        Response.json(
          {
            message: "Review the business settings and try again.",
            fieldErrors: { timezone: ["Enter a valid IANA timezone name."] },
          },
          { status: 400 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();
    await screen.findByDisplayValue("America/New_York");
    fireEvent.change(screen.getByLabelText("Timezone"), {
      target: { value: "Invalid/Zone" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save business settings" }),
    );
    expect(
      await screen.findByText("Enter a valid IANA timezone name."),
    ).toBeTruthy();
    expect(screen.getByText(/Company A/)).toBeTruthy();
  });

  it("replaces A settings with B after the validated Company switch", async () => {
    const current = session();
    const companyB = {
      id: "company-b",
      code: "B",
      display_name: "Company B",
      legal_name: "Company B Limited",
      is_active: true,
    };
    current.company_context.companies.push(companyB);
    const bravo = {
      ...alpha,
      default_currency: "GBP",
      timezone: "Europe/London",
      invoice_number_prefix: "BINV",
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (
          String(input) === "/api/auth/company-context" &&
          init?.method === "PUT"
        )
          return Response.json({
            companies: current.company_context.companies,
            selected_company: companyB,
            selection_required: false,
          });
        const settingsGets = fetchMock.mock.calls.filter(
          ([url]) => String(url) === "/api/auth/company-business-settings",
        ).length;
        return Response.json(settingsGets > 1 ? bravo : alpha);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AuthProvider session={current}>
        <AppShell>
          <CompanyBusinessSettings />
        </AppShell>
      </AuthProvider>,
    );
    await screen.findByDisplayValue("USD");
    fireEvent.change(screen.getByLabelText("Active Company"), {
      target: { value: "company-b" },
    });
    await waitFor(() => expect(screen.getByDisplayValue("GBP")).toBeTruthy());
    expect(screen.getByDisplayValue("BINV")).toBeTruthy();
    expect(screen.queryByDisplayValue("AINV")).toBeNull();
  });
});
