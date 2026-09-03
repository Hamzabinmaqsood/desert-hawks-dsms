import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { InvoiceDetailPage } from "@/features/invoices/detail-page";
import type { InvoiceDetail } from "@/features/invoices/types";
import type { SessionData } from "@/lib/auth/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/invoices",
}));

const invoice: InvoiceDetail = {
  id: "invoice-1",
  invoice_number: "INV-2026-001",
  company: "company-1",
  client: "client-1",
  contract: null,
  invoice_type: "STANDARD",
  currency: "PKR",
  invoice_date: "2026-09-01",
  service_period_start: null,
  service_period_end: null,
  due_date: "2026-10-01",
  client_po_reference: "",
  client_reference: "",
  source_billing_schedule: null,
  subtotal: "10000.00",
  discount_total: "0.00",
  tax_total: "1600.00",
  adjustment_total: "0.00",
  total_amount: "11600.00",
  amount_paid: "0.00",
  balance_due: "11600.00",
  status: "DRAFT",
  generated_by: "maker-1",
  reviewed_by: null,
  reviewed_at: null,
  approved_by: null,
  approved_at: null,
  issued_by: null,
  issued_at: null,
  voided_by: null,
  voided_at: null,
  void_reason: "",
  billing_name_snapshot: "Acme Security Client",
  billing_address_snapshot: "Test address",
  tax_registration_snapshot: "",
  payment_terms_snapshot: 30,
  payment_instructions_snapshot: "",
  notes_snapshot: "",
  posted_at: null,
  created_at: "2026-09-01T09:00:00Z",
  updated_at: "2026-09-01T09:00:00Z",
  is_overdue: false,
  pdf_available: false,
  lines: [
    {
      id: "line-1",
      line_number: 1,
      contract_service: null,
      site: null,
      billing_rule: null,
      description: "Guarding service",
      quantity: "10.0000",
      unit: "SHIFT",
      unit_price: "1000.00",
      gross_amount: "10000.00",
      discount_amount: "0.00",
      taxable_amount: "10000.00",
      tax_amount: "1600.00",
      line_total: "11600.00",
      revenue_account: "account-1",
      cost_center: null,
      created_at: "2026-09-01T09:00:00Z",
    },
  ],
};

const at = (
  status: InvoiceDetail["status"],
  extra: Partial<InvoiceDetail> = {},
): InvoiceDetail => ({ ...invoice, status, ...extra });

const session: SessionData = {
  authenticated: true,
  user: {
    id: "approver-1",
    email: "approver@example.test",
    first_name: "Approver",
    last_name: "User",
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
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function renderDetail(
  current: InvoiceDetail,
  permissions: string[],
  userId = "approver-1",
) {
  render(
    <AuthProvider
      session={{
        ...session,
        permissions,
        user: { ...session.user, id: userId },
      }}
    >
      <InvoiceDetailPage id="invoice-1" />
    </AuthProvider>,
  );
  await screen.findByRole("heading", { name: current.invoice_number });
}

const MAKER = ["billing.view_clientinvoice", "billing.change_clientinvoice"];
const APPROVER = ["billing.view_clientinvoice", "billing.approve_invoice"];
const ISSUER = ["billing.view_clientinvoice", "billing.issue_invoice"];
const VIEWER = ["billing.view_clientinvoice"];

afterEach(cleanup);

describe("Invoice workflow action visibility", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    ["DRAFT", MAKER, "Submit for review", true],
    ["DRAFT", VIEWER, "Submit for review", false],
    ["UNDER_REVIEW", APPROVER, "Approve", true],
    ["UNDER_REVIEW", VIEWER, "Approve", false],
    ["APPROVED", ISSUER, "Issue invoice", true],
    ["APPROVED", VIEWER, "Issue invoice", false],
  ] as const)(
    "renders %s / %j so that %s visible=%s",
    async (status, permissions, label, visible) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => json(at(status))),
      );
      await renderDetail(at(status), [...permissions]);
      if (visible)
        expect(screen.getByRole("button", { name: label })).toBeTruthy();
      else expect(screen.queryByRole("button", { name: label })).toBeNull();
    },
  );

  it("offers no workflow transition on an ISSUED invoice", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(at("ISSUED", { pdf_available: true }))),
    );
    await renderDetail(at("ISSUED"), [
      ...MAKER,
      "billing.approve_invoice",
      "billing.issue_invoice",
      "billing.download_invoice",
    ]);
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Issue invoice" })).toBeNull();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeTruthy();
  });

  it("offers Edit only while the invoice is a DRAFT", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(at("DRAFT"))),
    );
    await renderDetail(at("DRAFT"), MAKER);
    expect(screen.getByRole("link", { name: "Edit" })).toBeTruthy();
    cleanup();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(at("UNDER_REVIEW"))),
    );
    await renderDetail(at("UNDER_REVIEW"), MAKER);
    expect(screen.queryByRole("link", { name: "Edit" })).toBeNull();
  });

  it("blocks Submit on an empty draft with a backend-consistent explanation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(at("DRAFT", { lines: [] }))),
    );
    await renderDetail(at("DRAFT"), MAKER);
    const button = screen.getByRole("button", { name: "Submit for review" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen.getByText("Add at least one line before submitting."),
    ).toBeTruthy();
  });
});

describe("Invoice workflow transitions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits a draft and renders the backend-returned UNDER_REVIEW state", async () => {
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) =>
      init?.method === "POST" ? json(at("UNDER_REVIEW")) : json(at("DRAFT")),
    );
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("DRAFT"), MAKER);

    fireEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm submit" }));

    await waitFor(() =>
      expect(screen.getAllByText("Under review").length).toBeGreaterThan(0),
    );
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).toBeNull();
    const [url, init] = backend.mock.calls.at(-1) as [
      URL | string,
      RequestInit,
    ];
    expect(String(url)).toContain("/api/invoices/invoice-1/submit");
    expect(init.method).toBe("POST");
  });

  it("approves an invoice under review", async () => {
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) =>
      init?.method === "POST" ? json(at("APPROVED")) : json(at("UNDER_REVIEW")),
    );
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("UNDER_REVIEW"), APPROVER);

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approve" }));

    await waitFor(() =>
      expect(screen.getAllByText("Approved").length).toBeGreaterThan(0),
    );
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("issues an approved invoice and surfaces the newly available PDF", async () => {
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) =>
      init?.method === "POST"
        ? json(at("ISSUED", { pdf_available: true }))
        : json(at("APPROVED")),
    );
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("APPROVED"), [...ISSUER, "billing.download_invoice"]);
    expect(screen.queryByRole("button", { name: "Download PDF" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Issue invoice" }));
    expect(
      screen.getByText(
        "Issue this invoice? Issuing posts it to accounts receivable and generates the official PDF.",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm issue" }));

    await waitFor(() =>
      expect(screen.getAllByText("Issued").length).toBeGreaterThan(0),
    );
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Issue invoice" })).toBeNull();
  });
});

describe("Invoice workflow failures", () => {
  beforeEach(() => vi.clearAllMocks());

  it("surfaces the backend maker/checker rejection and keeps the invoice under review", async () => {
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) =>
      init?.method === "POST"
        ? json(
            { detail: ["Maker/checker policy prevents self-approval."] },
            400,
          )
        : json(at("UNDER_REVIEW")),
    );
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("UNDER_REVIEW"), APPROVER);

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approve" }));

    await waitFor(() =>
      expect(
        screen.getByText("Maker/checker policy prevents self-approval."),
      ).toBeTruthy(),
    );
    expect(screen.getAllByText("Under review").length).toBeGreaterThan(0);
    // Still under review, so the action remains offered rather than advancing.
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("proactively blocks approval when the viewer is the invoice maker", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(at("UNDER_REVIEW", { generated_by: "maker-1" }))),
    );
    await renderDetail(at("UNDER_REVIEW"), APPROVER, "maker-1");

    expect(
      (screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      screen.getByText(
        "This invoice requires approval by another authorized user.",
      ),
    ).toBeTruthy();
  });

  it("keeps the invoice APPROVED and hides the PDF when issuing fails", async () => {
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) =>
      init?.method === "POST"
        ? json(
            {
              detail: [
                "No open accounting period covers this billing transaction.",
              ],
            },
            400,
          )
        : json(at("APPROVED")),
    );
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("APPROVED"), [...ISSUER, "billing.download_invoice"]);

    fireEvent.click(screen.getByRole("button", { name: "Issue invoice" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm issue" }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "No open accounting period covers this billing transaction.",
        ),
      ).toBeTruthy(),
    );
    expect(screen.getAllByText("Approved").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Download PDF" })).toBeNull();
    expect(screen.getByRole("button", { name: "Issue invoice" })).toBeTruthy();
  });

  it("refreshes stale state when another user already advanced the invoice", async () => {
    let advanced = false;
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) => {
      if (init?.method === "POST") {
        advanced = true;
        return json({ detail: ["Invoice is not under review."] }, 400);
      }
      return json(at(advanced ? "APPROVED" : "UNDER_REVIEW"));
    });
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("UNDER_REVIEW"), APPROVER);

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approve" }));

    await waitFor(() =>
      expect(screen.getByText("Invoice is not under review.")).toBeTruthy(),
    );
    // The obsolete action must not linger once authoritative state is re-read.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Approve" })).toBeNull(),
    );
    expect(screen.getAllByText("Approved").length).toBeGreaterThan(0);
  });

  it("issues only once when the confirm button is double-clicked", async () => {
    let release: (value: Response) => void = () => {};
    const backend = vi.fn(async (_input: URL | string, init?: RequestInit) =>
      init?.method === "POST"
        ? new Promise<Response>((resolve) => {
            release = resolve;
          })
        : json(at("APPROVED")),
    );
    vi.stubGlobal("fetch", backend);
    await renderDetail(at("APPROVED"), ISSUER);

    fireEvent.click(screen.getByRole("button", { name: "Issue invoice" }));
    const confirm = screen.getByRole("button", { name: "Confirm issue" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    const posts = backend.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Issuing…" })).toBeTruthy();

    release(json(at("ISSUED", { pdf_available: true })));
    await waitFor(() =>
      expect(screen.getAllByText("Issued").length).toBeGreaterThan(0),
    );
  });
});
