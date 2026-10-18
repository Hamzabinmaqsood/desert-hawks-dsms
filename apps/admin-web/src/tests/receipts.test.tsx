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
  ReceiptCreatePage,
  ReceiptDetailPage,
  ReceiptListPage,
} from "@/features/receipts/pages";
import type { SessionData } from "@/lib/auth/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/receipts",
}));
const session: SessionData = {
  authenticated: true,
  user: {
    id: "u",
    email: "u@test",
    first_name: "U",
    last_name: "",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    last_login: null,
    date_joined: "",
    created_at: "",
    updated_at: "",
  },
  permissions: ["billing.view_clientreceipt", "billing.allocate_receipt"],
  scopes: {
    is_superuser: false,
    accessible_company_ids: ["c"],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
  platform_capabilities: { capabilities: [], can_access_platform_admin: false },
  company_context: {
    effective_modules: ["billing_receivables"],
    entitlement_revision: 0,
    companies: [
      {
        id: "c",
        code: "C",
        display_name: "Company",
        legal_name: "Company",
        is_active: true,
      },
    ],
    selected_company: {
      id: "c",
      code: "C",
      display_name: "Company",
      legal_name: "Company",
      is_active: true,
    },
    selection_required: false,
  },
};
const receipt = {
  id: "r",
  receipt_number: "RCPT-2026-1",
  company: "c",
  client: "client",
  client_name: "Acme",
  received_at: "2026-08-02T10:00:00Z",
  value_date: "2026-08-02",
  currency: "PKR",
  amount: "70.00",
  payment_method: "BANK_TRANSFER",
  bank_account: "bank",
  cheque_reference: "",
  external_reference: "BANK-9",
  status: "CONFIRMED",
  notes: "",
  allocated_amount: "60.00",
  unallocated_amount: "10.00",
  allocations: [
    {
      id: "a",
      invoice: "i",
      invoice_number: "INV-1",
      amount: "60.00",
      allocated_at: "2026-08-03T10:00:00Z",
    },
  ],
};
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function withAuth(node: React.ReactNode, permissions = session.permissions) {
  return render(
    <AuthProvider session={{ ...session, permissions }}>{node}</AuthProvider>,
  );
}

describe("Receipt screens", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());
  it("renders authoritative receipt list money and create permission", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ count: 1, next: null, previous: null, results: [receipt] }),
      ),
    );
    withAuth(<ReceiptListPage searchParams={{}} />, [
      "billing.view_clientreceipt",
      "billing.add_clientreceipt",
    ]);
    expect(
      await screen.findByRole("link", { name: "RCPT-2026-1" }),
    ).toBeTruthy();
    expect(screen.getByText("Acme")).toBeTruthy();
    expect(screen.getAllByText(/PKR.*10.00/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "New Receipt" })).toBeTruthy();
  });
  it("creates a draft from least-privilege client and bank references", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(
        json({
          results: [
            {
              client: "client",
              company: "c",
              billing_name: "Acme",
              currency: "PKR",
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        json({
          results: [
            {
              id: "bank",
              company: "c",
              name: "Collections",
              bank_name: "Test Bank",
              currency: "PKR",
            },
          ],
        }),
      )
      .mockResolvedValueOnce(json(receipt, 201));
    vi.stubGlobal("fetch", backend);
    withAuth(<ReceiptCreatePage />, ["billing.add_clientreceipt"]);
    await screen.findByRole("option", { name: "Acme (PKR)" });
    fireEvent.change(screen.getByLabelText("Client"), {
      target: { value: "client" },
    });
    fireEvent.change(screen.getByLabelText("Received at"), {
      target: { value: "2026-09-10T10:00" },
    });
    fireEvent.change(screen.getByLabelText("Amount"), {
      target: { value: "70.00" },
    });
    fireEvent.change(screen.getByLabelText("Payment method"), {
      target: { value: "BANK_TRANSFER" },
    });
    fireEvent.change(screen.getByLabelText("Receiving bank account"), {
      target: { value: "bank" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() => expect(backend).toHaveBeenCalledTimes(3));
    const payload = JSON.parse(
      String(
        (backend.mock.calls[2] as unknown as [unknown, RequestInit])[1].body,
      ),
    );
    expect(payload).toMatchObject({
      company: "c",
      client: "client",
      amount: "70.00",
      bank_account: "bank",
    });
    expect(payload.status).toBeUndefined();
  });
  it("renders detail, allocation history, eligible balance and receipt-to-invoice link", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json(receipt))
      .mockResolvedValueOnce(
        json([
          {
            id: "i",
            invoice_number: "INV-1",
            invoice_date: "2026-08-01",
            currency: "PKR",
            total_amount: "100",
            amount_paid: "0",
            balance_due: "40",
            status: "ISSUED",
          },
        ]),
      );
    vi.stubGlobal("fetch", backend);
    withAuth(<ReceiptDetailPage id="r" />);
    expect(await screen.findByText("Allocation history")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "INV-1" }).getAttribute("href"),
    ).toBe("/invoices/i");
    expect(screen.getByText(/PKR.*10.00/)).toBeTruthy();
    expect(screen.getByText(/PKR.*40.00 outstanding/)).toBeTruthy();
  });
  it("shows backend allocation errors and refreshes authoritative state", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json(receipt))
      .mockResolvedValueOnce(
        json([
          {
            id: "i",
            invoice_number: "INV-1",
            invoice_date: "",
            currency: "PKR",
            total_amount: "100",
            amount_paid: "0",
            balance_due: "40",
            status: "ISSUED",
          },
        ]),
      )
      .mockResolvedValueOnce(
        json({ amount: ["Allocation exceeds the receipt balance."] }, 400),
      )
      .mockResolvedValueOnce(json(receipt))
      .mockResolvedValueOnce(json([]));
    vi.stubGlobal("fetch", backend);
    withAuth(<ReceiptDetailPage id="r" />);
    await screen.findByText(/PKR.*40.00 outstanding/);
    fireEvent.change(screen.getByLabelText("Eligible invoice"), {
      target: { value: "i" },
    });
    fireEvent.change(screen.getByLabelText("Allocation amount"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Allocate payment" }));
    expect(
      await screen.findByText("Allocation exceeds the receipt balance."),
    ).toBeTruthy();
    await waitFor(() => expect(backend).toHaveBeenCalledTimes(5));
  });
  it("blocks receipt screens without permissions", () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    withAuth(<ReceiptListPage searchParams={{}} />, []);
    expect(screen.getByRole("alert").textContent).toContain("permission");
    expect(backend).not.toHaveBeenCalled();
  });
});
