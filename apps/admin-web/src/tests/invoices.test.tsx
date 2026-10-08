import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { InvoiceDetailPage } from "@/features/invoices/detail-page";
import { InvoiceListPage } from "@/features/invoices/list-page";
import type { InvoiceDetail } from "@/features/invoices/types";
import type { SessionData } from "@/lib/auth/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/invoices",
}));

export const invoice: InvoiceDetail = {
  id: "invoice-1",
  invoice_number: "INV-2026-001",
  company: "company-1",
  client: "client-1",
  contract: "contract-1",
  invoice_type: "SERVICE",
  currency: "PKR",
  invoice_date: "2026-08-01",
  service_period_start: "2026-07-01",
  service_period_end: "2026-07-31",
  due_date: "2026-08-31",
  client_po_reference: "PO-44",
  client_reference: "REF-9",
  source_billing_schedule: null,
  subtotal: "10000.00",
  discount_total: "500.00",
  tax_total: "1520.00",
  adjustment_total: "0.00",
  total_amount: "11020.00",
  amount_paid: "2000.00",
  balance_due: "9020.00",
  status: "PARTIALLY_PAID",
  generated_by: "user-1",
  reviewed_by: "user-2",
  reviewed_at: "2026-08-02T10:00:00Z",
  approved_by: "user-3",
  approved_at: "2026-08-03T10:00:00Z",
  issued_by: "user-4",
  issued_at: "2026-08-04T10:00:00Z",
  voided_by: null,
  voided_at: null,
  void_reason: "",
  billing_name_snapshot: "Acme Security Client",
  billing_address_snapshot: "Test address",
  tax_registration_snapshot: "",
  payment_terms_snapshot: 30,
  payment_instructions_snapshot: "",
  notes_snapshot: "",
  posted_at: "2026-08-04T10:05:00Z",
  created_at: "2026-08-01T09:00:00Z",
  updated_at: "2026-08-04T10:05:00Z",
  is_overdue: true,
  pdf_available: true,
  lines: [
    {
      id: "line-1",
      line_number: 1,
      contract_service: "service-1",
      site: "site-1",
      billing_rule: null,
      description: "Guarding service",
      quantity: "10.0000",
      unit: "SHIFT",
      unit_price: "1000.00",
      gross_amount: "10000.00",
      discount_amount: "500.00",
      taxable_amount: "9500.00",
      tax_amount: "1520.00",
      line_total: "11020.00",
      revenue_account: "account-1",
      cost_center: null,
      created_at: "2026-08-01T09:00:00Z",
    },
  ],
  receipt_allocations: [
    {
      id: "allocation-1",
      receipt: "receipt-1",
      receipt_number: "RCPT-2026-001",
      receipt_date: "2026-08-05T10:00:00Z",
      payment_method: "BANK_TRANSFER",
      reference: "BANK-9",
      amount: "2000.00",
      allocated_at: "2026-08-05T10:05:00Z",
    },
  ],
};

const baseSession: SessionData = {
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
  permissions: ["billing.view_clientinvoice"],
  scopes: {
    is_superuser: false,
    accessible_company_ids: ["company-1"],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
  company_context: {
    companies: [
      {
        id: "company-1",
        code: "C1",
        display_name: "Company One",
        legal_name: "Company One",
        is_active: true,
      },
    ],
    selected_company: {
      id: "company-1",
      code: "C1",
      display_name: "Company One",
      legal_name: "Company One",
      is_active: true,
    },
    selection_required: false,
  },
};

function renderWithSession(
  node: React.ReactNode,
  permissions = baseSession.permissions,
) {
  return render(
    <AuthProvider session={{ ...baseSession, permissions }}>
      {node}
    </AuthProvider>,
  );
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("invoice screens", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("renders list rows, money, status, overdue, pagination, and filters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ count: 12, next: "/next", previous: null, results: [invoice] }),
      ),
    );
    renderWithSession(
      <InvoiceListPage
        searchParams={{ status: "PARTIALLY_PAID", page: "1" }}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("Loading");
    expect(
      await screen.findByRole("link", { name: "INV-2026-001" }),
    ).toBeTruthy();
    expect(screen.getByText("Acme Security Client")).toBeTruthy();
    expect(screen.getAllByText(/PKR.*11,020.00/).length).toBeGreaterThan(0);
    expect(screen.getByRole("status").textContent).toContain("Partially paid");
    expect(screen.getByText("Overdue")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Next" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "INV-2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(push).toHaveBeenCalledWith(
      expect.stringContaining("search=INV-2026"),
    );
  });

  it("renders filtered empty and stable API error states", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json({ count: 0, next: null, previous: null, results: [] }),
      )
      .mockResolvedValueOnce(json({ detail: "private backend detail" }, 500));
    vi.stubGlobal("fetch", fetchMock);
    const first = renderWithSession(
      <InvoiceListPage searchParams={{ status: "PAID" }} />,
    );
    expect(
      await screen.findByText("No invoices match these filters."),
    ).toBeTruthy();
    first.unmount();
    renderWithSession(<InvoiceListPage searchParams={{}} />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Invoices could not be loaded",
    );
    expect(screen.queryByText("private backend detail")).toBeNull();
  });

  it("denies direct list access without fetching and hides invoice navigation", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<InvoiceListPage searchParams={{}} />, []);
    expect(screen.getByRole("alert").textContent).toContain("permission");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the New Invoice CTA only with create permission", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    const withCreate = renderWithSession(
      <InvoiceListPage searchParams={{}} />,
      ["billing.view_clientinvoice", "billing.add_clientinvoice"],
    );
    expect(
      await withCreate.findByRole("link", { name: "New Invoice" }),
    ).toBeTruthy();
    withCreate.unmount();

    renderWithSession(<InvoiceListPage searchParams={{}} />, [
      "billing.view_clientinvoice",
    ]);
    await screen.findByText("No invoices found.");
    expect(screen.queryByRole("link", { name: "New Invoice" })).toBeNull();
  });

  it("renders detail totals, lines, workflow metadata and permitted PDF action", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(invoice)),
    );
    renderWithSession(<InvoiceDetailPage id="invoice-1" />, [
      "billing.view_clientinvoice",
      "billing.download_invoice",
    ]);
    expect(
      await screen.findByRole("heading", { name: "INV-2026-001" }),
    ).toBeTruthy();
    expect(screen.getByText("Guarding service")).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Financial summary" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Lifecycle" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "RCPT-2026-001" }).getAttribute("href"),
    ).toBe("/receipts/receipt-1");
  });

  it("hides unavailable or unauthorized PDFs and normalizes not found", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ ...invoice, pdf_available: false })),
    );
    const first = renderWithSession(<InvoiceDetailPage id="invoice-1" />, [
      "billing.view_clientinvoice",
      "billing.download_invoice",
    ]);
    await screen.findByRole("heading", { name: "INV-2026-001" });
    expect(screen.queryByRole("button", { name: "Download PDF" })).toBeNull();
    first.unmount();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "hidden" }, 404)),
    );
    renderWithSession(<InvoiceDetailPage id="missing" />);
    expect(await screen.findByText("Invoice not found.")).toBeTruthy();
  });
});
