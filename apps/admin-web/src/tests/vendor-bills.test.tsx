import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/features/auth/auth-context";
import {
  VendorBillCreatePage,
  VendorBillDetailPage,
  VendorBillEditPage,
  VendorBillListPage,
} from "@/features/vendor-bills/pages";
import type { SessionData } from "@/lib/auth/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/vendor-bills",
}));
const permissions = [
  "finance.view_vendorbill",
  "finance.add_vendorbill",
  "finance.change_vendorbill",
  "finance.add_vendorbillline",
  "finance.change_vendorbillline",
  "finance.delete_vendorbillline",
  "finance.view_vendor",
];
const session: SessionData = {
  authenticated: true,
  user: {
    id: "u",
    email: "ap@test",
    first_name: "AP",
    last_name: "User",
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
    accessible_company_ids: ["c"],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
};
const vendor = { id: "v", code: "V-1", name: "Desert Supply", is_active: true };
const line = {
  id: "l",
  purchase_order_line: null,
  receipt_line: null,
  description: "Fuel",
  quantity: "2.0000",
  unit_price: "100.00",
  tax_amount: "20.00",
  line_total: "220.00",
  expense_account: "a",
  expense_account_code: "5000",
  expense_account_name: "Supplies",
};
const bill = {
  id: "b",
  bill_number: "B-1",
  vendor_invoice_number: "SUP-1",
  vendor: "v",
  vendor_code: "V-1",
  vendor_name: "Desert Supply",
  bill_date: "2026-09-17",
  due_date: "2026-10-17",
  status: "DRAFT",
  total_amount: "220.00",
  paid_amount: "0.00",
  outstanding_amount: "220.00",
  purchase_order: null,
  match_type: "TWO_WAY",
  subtotal: "200.00",
  tax_amount: "20.00",
  match_exception: "",
  lines: [line],
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const withAuth = (node: React.ReactNode, perms = permissions) =>
  render(
    <AuthProvider session={{ ...session, permissions: perms }}>
      {node}
    </AuthProvider>,
  );

describe("Vendor Bill screens", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    push.mockReset();
  });
  afterEach(() => cleanup());
  it("renders server-filtered list, values, pagination and permission-aware actions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) =>
        String(url).includes("/api/vendors")
          ? json({ results: [vendor] })
          : json({ count: 2, next: "next", previous: null, results: [bill] }),
      ),
    );
    withAuth(
      <VendorBillListPage searchParams={{ search: "SUP", status: "DRAFT" }} />,
    );
    expect(await screen.findByRole("link", { name: "B-1" })).toBeTruthy();
    expect(screen.getAllByText("220.00")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "New Vendor Bill" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Next" })).toBeTruthy();
  });
  it("creates a draft with explicit fields and displays duplicate errors", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ results: [vendor] }))
      .mockResolvedValueOnce(
        json(
          {
            vendor_invoice_number: [
              "This supplier invoice is already recorded.",
            ],
          },
          400,
        ),
      );
    vi.stubGlobal("fetch", backend);
    withAuth(<VendorBillCreatePage />);
    await screen.findByRole("option", { name: /V-1.*Desert Supply/ });
    fireEvent.change(screen.getByLabelText("Vendor"), {
      target: { value: "v" },
    });
    fireEvent.change(screen.getByLabelText("Internal Bill Reference"), {
      target: { value: "B-1" },
    });
    fireEvent.change(screen.getByLabelText("Supplier Invoice Number"), {
      target: { value: "SUP-1" },
    });
    fireEvent.change(screen.getByLabelText("Bill date"), {
      target: { value: "2026-09-17" },
    });
    fireEvent.change(screen.getByLabelText("Due date"), {
      target: { value: "2026-10-17" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(
      await screen.findByText("This supplier invoice is already recorded."),
    ).toBeTruthy();
  });
  it("renders draft line controls and hides all editing for a non-draft Bill", async () => {
    const backend = vi.fn(async (url: RequestInfo | URL) =>
      String(url).includes("/api/vendors")
        ? json({ results: [vendor] })
        : String(url).includes("vendor-bill-accounts")
          ? json([
              {
                id: "a",
                code: "5000",
                name: "Supplies",
                account_type: "EXPENSE",
              },
            ])
          : json(bill),
    );
    vi.stubGlobal("fetch", backend);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    withAuth(<VendorBillEditPage id="b" />);
    expect(await screen.findByRole("button", { name: "Edit" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add line" })).toBeTruthy();
    expect(screen.getByText("200.00")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Quantity"), {
      target: { value: "3.0000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save line" }));
    await waitFor(() =>
      expect(backend.mock.calls.length).toBeGreaterThanOrEqual(4),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(backend.mock.calls.length).toBeGreaterThanOrEqual(6),
    );
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ ...bill, status: "POSTED" })),
    );
    withAuth(<VendorBillEditPage id="b" />);
    expect(
      await screen.findByText("This Vendor Bill can no longer be edited."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add line" })).toBeNull();
  });
  it("shows read-only detail and removes edit action without permission", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(bill)),
    );
    withAuth(<VendorBillDetailPage id="b" />, ["finance.view_vendorbill"]);
    expect(await screen.findByText("SUP-1")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit Vendor Bill" })).toBeNull();
    expect(screen.getByText("Outstanding")).toBeTruthy();
  });
});
