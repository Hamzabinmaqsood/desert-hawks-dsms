import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sessionMocks = vi.hoisted(() => ({
  backend: vi.fn(),
  load: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({
  authenticatedBackendRequest: sessionMocks.backend,
  loadSession: sessionMocks.load,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/assets",
}));

import {
  GET as assetGet,
  PATCH as assetPatch,
} from "@/app/api/assets/[...segments]/route";
import { GET as billingSummaryGet } from "@/app/api/billing-summary/route";
import {
  GET as procurementGet,
  POST as procurementPost,
} from "@/app/api/procurement/[...segments]/route";
import { visibleNavigationGroups } from "@/components/layout/sidebar";
import { AssetListPage } from "@/features/assets/pages";
import { AuthProvider } from "@/features/auth/auth-context";
import { RequisitionListPage } from "@/features/procurement/pages";
import type { SessionData } from "@/lib/auth/types";

const company = {
  id: "10000000-0000-0000-0000-000000000001",
  code: "ACME",
  display_name: "Acme Services",
  legal_name: "Acme Services Limited",
  is_active: true,
};
const permissions = [
  "finance.view_vendor",
  "finance.view_purchaserequisition",
  "finance.add_purchaserequisition",
  "finance.view_purchaseorder",
  "finance.view_purchasereceipt",
  "assets.view_asset",
  "assets.register_asset",
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
    effective_modules: ["procurement_payables", "asset_management"],
    entitlement_revision: 1,
  },
};
const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const context = (segments: string[]) => ({
  params: Promise.resolve({ segments }),
});
function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Origin", "http://admin.test");
  headers.set("Host", "admin.test");
  const { signal, ...rest } = init;
  return new NextRequest(`http://admin.test${path}`, {
    ...rest,
    headers,
    signal: signal ?? undefined,
  });
}

describe("SaaS-5C.4 Procurement and Asset workspaces", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionMocks.load.mockResolvedValue({ status: 200, session });
    sessionMocks.backend.mockResolvedValue({
      ok: true,
      status: 200,
      data: { count: 0, results: [] },
    });
  });
  afterEach(() => cleanup());

  it("shows module- and permission-gated Procurement and Asset navigation", () => {
    const groups = visibleNavigationGroups(
      permissions,
      ["procurement_payables", "asset_management"],
      false,
    );
    expect(groups.find((group) => group.id === "finance")?.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "Purchase Requisitions" }),
        expect.objectContaining({ label: "Purchase Orders" }),
        expect.objectContaining({ label: "Purchase Receipts" }),
      ]),
    );
    expect(groups.find((group) => group.id === "operations")?.items).toEqual([
      expect.objectContaining({ label: "Assets" }),
    ]);
    expect(
      visibleNavigationGroups(permissions, [], false).some((group) =>
        group.items.some((item) => item.href.startsWith("/purchase-")),
      ),
    ).toBe(false);
  });

  it("injects selected Company and strips server-owned Procurement fields", async () => {
    const id = "20000000-0000-0000-0000-000000000001";
    await procurementGet(
      request(
        "/api/procurement/purchase-orders?status=APPROVED&company=foreign",
      ),
      context(["purchase-orders"]),
    );
    expect(sessionMocks.backend.mock.calls[0]?.[2]).toContain(
      `company=${company.id}`,
    );
    await procurementPost(
      request(`/api/procurement/purchase-orders/${id}/submit`, {
        method: "POST",
        body: JSON.stringify({ status: "APPROVED", company: "foreign" }),
      }),
      context(["purchase-orders", id, "submit"]),
    );
    expect(
      JSON.parse(String(sessionMocks.backend.mock.calls[1]?.[3]?.body)),
    ).toEqual({});
  });

  it("keeps Asset updates metadata-only and rejects non-allowlisted paths", async () => {
    const id = "30000000-0000-0000-0000-000000000001";
    await assetPatch(
      request(`/api/assets/assets/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          notes: "Inspected",
          status: "DISPOSED",
          current_employee: "foreign",
        }),
      }),
      context(["assets", id]),
    );
    expect(
      JSON.parse(String(sessionMocks.backend.mock.calls[0]?.[3]?.body)),
    ).toEqual({
      notes: "Inspected",
    });
    const response = await assetGet(
      request("/api/assets/private-ledger"),
      context(["private-ledger"]),
    );
    expect(response.status).toBe(404);
    expect(sessionMocks.backend).toHaveBeenCalledOnce();
  });

  it("derives the AR summary from selected Company authority", async () => {
    sessionMocks.backend.mockResolvedValueOnce({
      ok: true,
      status: 200,
      data: { ageing: { CURRENT: "10.00", "1-30": "5.00" } },
    });
    const response = await billingSummaryGet(request("/api/billing-summary"));
    expect(response.status).toBe(200);
    expect(sessionMocks.backend.mock.calls[0]?.[2]).toBe(
      `billing/dashboard/?company=${company.id}`,
    );
  });

  it("renders server-backed Procurement and Asset lists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("purchase-requisitions"))
          return json(
            page([
              {
                id: "pr",
                requisition_number: "PR-100",
                required_date: "2026-11-01",
                purpose: "Office equipment",
                status: "APPROVED",
                total_estimated_amount: "2000.00",
                lines: [],
              },
            ]),
          );
        return json(
          page([
            {
              id: "asset",
              asset_number: "AST-100",
              serial_number: "SERIAL-100",
              item_code: "LAPTOP",
              item_name: "Laptop",
              category_name: "IT equipment",
              status: "AVAILABLE",
              condition: "GOOD",
              current_custody_type: "WAREHOUSE",
              current_warehouse_name: "Main Store",
            },
          ]),
        );
      }),
    );
    const { unmount } = render(
      <AuthProvider session={session}>
        <RequisitionListPage searchParams={{}} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("PR-100")).toBeTruthy());
    unmount();
    render(
      <AuthProvider session={session}>
        <AssetListPage searchParams={{}} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("AST-100")).toBeTruthy());
    expect(screen.getByText("Main Store")).toBeTruthy();
  });
});
