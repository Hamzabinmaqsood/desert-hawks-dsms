import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  GET as clientContractGet,
  POST as clientContractPost,
} from "@/app/api/client-contracts/[...segments]/route";
import {
  GET as peopleGet,
  POST as peoplePost,
} from "@/app/api/people/[...segments]/route";
import { visibleNavigationGroups } from "@/components/layout/sidebar";
import { AuthProvider } from "@/features/auth/auth-context";
import {
  ClientListPage,
  ContractDetailPage,
} from "@/features/client-contracts/pages";
import { EmployeeCreatePage, EmployeeListPage } from "@/features/people/pages";
import type { SessionData } from "@/lib/auth/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/employees",
}));

const company = {
  id: "company-a",
  code: "A",
  display_name: "Company A",
  legal_name: "Company A Limited",
  is_active: true,
};
const permissions = [
  "workforce.view_employee",
  "workforce.add_employee",
  "workforce.change_employee",
  "contracts.view_client",
  "contracts.add_client",
  "contracts.change_client",
  "contracts.view_servicecontract",
  "contracts.add_servicecontract",
  "contracts.change_servicecontract",
  "contracts.view_contractservice",
  "contracts.view_contractcommercialterms",
  "contracts.view_contractamendment",
  "contracts.view_servicelevelagreement",
];
const session: SessionData = {
  authenticated: true,
  user: {
    id: "user",
    email: "tenant@example.test",
    first_name: "Tenant",
    last_name: "Admin",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    last_login: null,
    date_joined: "",
    created_at: "",
    updated_at: "",
  },
  permissions,
  scopes: {
    is_superuser: false,
    accessible_company_ids: [company.id],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
  platform_capabilities: { capabilities: [], can_access_platform_admin: false },
  company_context: {
    companies: [company],
    selected_company: company,
    selection_required: false,
    effective_modules: ["people", "client_contracts"],
    entitlement_revision: 1,
  },
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});
const withAuth = (node: React.ReactNode, value = session) =>
  render(<AuthProvider session={value}>{node}</AuthProvider>);

describe("SaaS-5C.3 tenant workspaces", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("renders server-backed employee results and Company-scoped filters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/branches"))
          return json(page([{ id: "b", name: "Head office" }]));
        if (url.includes("/departments"))
          return json(page([{ id: "d", name: "Operations" }]));
        return json(
          page([
            {
              id: "e",
              employee_number: "EMP-1",
              full_name: "Amina Khan",
              employee_type: "OFFICE_STAFF",
              employment_status: "ACTIVE",
              branch: "b",
              branch_name: "Head office",
              department: "d",
              department_name: "Operations",
              designation: null,
              designation_name: null,
              mobile_number: "0300",
              is_active: true,
            },
          ]),
        );
      }),
    );
    withAuth(
      <EmployeeListPage
        searchParams={{ search: "Amina", employment_status: "ACTIVE" }}
      />,
    );
    expect(
      await screen.findByRole("link", { name: "Amina Khan" }),
    ).toBeTruthy();
    expect((screen.getByLabelText("Search") as HTMLInputElement).value).toBe(
      "Amina",
    );
    expect(screen.getByRole("link", { name: "Add employee" })).toBeTruthy();
  });

  it("does not offer the security-only employee type without its module", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(page([]))),
    );
    withAuth(<EmployeeCreatePage />);
    await waitFor(() =>
      expect(screen.getByLabelText("Employee type")).toBeTruthy(),
    );
    expect(screen.queryByRole("option", { name: "Security guard" })).toBeNull();
    expect(screen.getByRole("option", { name: "Office staff" })).toBeTruthy();

    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/branches") || url.includes("/departments"))
          return json(page([]));
        return json(
          page([
            {
              id: "legacy-specialist",
              employee_number: "EMP-2",
              full_name: "Legacy Specialist",
              employee_type: "SECURITY_GUARD",
              employment_status: "ACTIVE",
              branch: null,
              branch_name: null,
              department: null,
              department_name: null,
              designation: null,
              designation_name: null,
              mobile_number: "0301",
              is_active: true,
            },
          ]),
        );
      }),
    );
    withAuth(<EmployeeListPage searchParams={{}} />);
    expect(
      await screen.findByText("Existing employee classification"),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/security guard/i);
  });

  it("renders generic clients without security terminology", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("industries")
          ? json(
              page([
                {
                  id: "i",
                  code: "PRO",
                  name: "Professional services",
                  is_active: true,
                },
              ]),
            )
          : json(
              page([
                {
                  id: "c",
                  client_code: "CLI-1",
                  legal_name: "Acme Advisory",
                  trade_name: "",
                  industry: "i",
                  industry_name: "Professional services",
                  main_email: "hello@acme.test",
                  main_phone: "",
                  city: "Karachi",
                  country_code: "PK",
                  status: "ACTIVE",
                },
              ]),
            ),
      ),
    );
    withAuth(<ClientListPage searchParams={{}} />);
    expect(
      await screen.findByRole("link", { name: "Acme Advisory" }),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /Security Site|Security Post|guard strength/i,
    );
  });

  it("shows only generic contract panels and site-independent service levels", async () => {
    const contract = {
      id: "k",
      company: company.id,
      client: "c",
      client_name: "Acme Advisory",
      contract_number: "CTR-1",
      contract_type: "PROJECT",
      title: "Advisory agreement",
      description: "General advisory services",
      signed_date: null,
      start_date: "2026-10-01",
      end_date: null,
      notice_period_days: null,
      auto_renew: false,
      currency: "PKR",
      status: "ACTIVE",
      client_reference: "",
      purchase_order_reference: "",
      internal_reference: "",
      primary_client_contact: null,
      primary_client_contact_name: null,
      account_manager: null,
      account_manager_name: null,
      approved_at: null,
      activated_at: null,
      created_at: "",
      updated_at: "",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (/\/contracts\/k$/.test(url)) return json(contract);
        if (url.includes("contract-services"))
          return json(
            page([
              {
                id: "s",
                contract: "k",
                service_type: "CONSULTANCY",
                name: "Advisory",
                description: "",
                start_date: null,
                end_date: null,
                is_active: true,
              },
            ]),
          );
        if (url.includes("commercial-terms")) return json(page([]));
        if (url.includes("contract-amendments")) return json(page([]));
        if (url.includes("slas"))
          return json(
            page([
              {
                id: "l",
                contract: "k",
                site: null,
                sla_type: "OTHER",
                name: "Response target",
                description: "",
                target_value: "4",
                target_unit: "hours",
                effective_from: "2026-10-01",
                effective_to: null,
                is_active: true,
              },
            ]),
          );
        return json({ detail: "not found" }, 404);
      }),
    );
    withAuth(<ContractDetailPage id="k" />);
    expect(
      await screen.findByRole("heading", { name: "Advisory agreement" }),
    ).toBeTruthy();
    expect(await screen.findByText("Response target")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /Security Site|Security Post|staffing requirement/i,
    );
  });

  it("requires both modules and RBAC for the new navigation groups", () => {
    const groups = visibleNavigationGroups(
      permissions,
      ["people", "client_contracts"],
      false,
    );
    expect(
      groups
        .find((group) => group.id === "people")
        ?.items.map((item) => item.label),
    ).toEqual(["Employees"]);
    expect(
      groups
        .find((group) => group.id === "clients")
        ?.items.map((item) => item.label),
    ).toEqual(["Clients", "Contracts"]);
    expect(
      visibleNavigationGroups(permissions, [], false).some((group) =>
        ["people", "clients"].includes(group.id),
      ),
    ).toBe(false);
    expect(
      visibleNavigationGroups([], ["people", "client_contracts"], false).some(
        (group) => ["people", "clients"].includes(group.id),
      ),
    ).toBe(false);
  });

  it("blocks security routes and rejects cross-origin mutations before proxying", async () => {
    const security = await clientContractGet(
      new NextRequest("http://admin.test/api/client-contracts/sites"),
      { params: Promise.resolve({ segments: ["sites"] }) },
    );
    expect(security.status).toBe(404);
    const peopleSecurity = await peopleGet(
      new NextRequest("http://admin.test/api/people/readiness/guards"),
      { params: Promise.resolve({ segments: ["readiness", "guards"] }) },
    );
    expect(peopleSecurity.status).toBe(404);
    const evil = {
      method: "POST",
      headers: { Origin: "https://evil.test", Host: "admin.test" },
      body: "{}",
    };
    expect(
      (
        await peoplePost(
          new NextRequest("http://admin.test/api/people/employees", evil),
          { params: Promise.resolve({ segments: ["employees"] }) },
        )
      ).status,
    ).toBe(403);
    expect(
      (
        await clientContractPost(
          new NextRequest(
            "http://admin.test/api/client-contracts/clients",
            evil,
          ),
          { params: Promise.resolve({ segments: ["clients"] }) },
        )
      ).status,
    ).toBe(403);
  });
});
