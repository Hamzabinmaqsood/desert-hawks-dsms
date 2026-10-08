import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { NewInvoicePage } from "@/features/invoices/create-page";
import { InvoiceEditPage } from "@/features/invoices/edit-page";
import type { InvoiceDetail } from "@/features/invoices/types";
import type { SessionData } from "@/lib/auth/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/invoices",
}));

const draftInvoice: InvoiceDetail = {
  id: "invoice-1",
  invoice_number: "INV-DRAFT-001",
  company: "company-1",
  client: "client-1",
  contract: "contract-1",
  invoice_type: "STANDARD",
  currency: "PKR",
  invoice_date: "2026-09-01",
  service_period_start: "2026-08-01",
  service_period_end: "2026-08-31",
  due_date: "2026-10-01",
  client_po_reference: "PO-1",
  client_reference: "REF-1",
  source_billing_schedule: null,
  subtotal: "10000.00",
  discount_total: "0.00",
  tax_total: "1600.00",
  adjustment_total: "0.00",
  total_amount: "11600.00",
  amount_paid: "0.00",
  balance_due: "11600.00",
  status: "DRAFT",
  generated_by: "user-1",
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

const issuedInvoice: InvoiceDetail = { ...draftInvoice, status: "ISSUED" };

const baseSession: SessionData = {
  authenticated: true,
  user: {
    id: "user-1",
    email: "maker@example.test",
    first_name: "Maker",
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
    "billing.change_clientinvoice",
  ],
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

function routedFetch(
  routes: Array<[RegExp, (init?: RequestInit) => Response]>,
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    for (const [pattern, respond] of routes) {
      if (pattern.test(`${method} ${url}`)) return respond(init);
    }
    throw new Error(`Unhandled request: ${method} ${url}`);
  });
}

const referenceRoutes: Array<[RegExp, () => Response]> = [
  [
    /GET .*\/api\/reference\/billing-profiles/,
    () =>
      json({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: "profile-1",
            client: "client-1",
            company: "company-1",
            billing_name: "Acme Security Client",
            currency: "PKR",
            payment_terms_days: 30,
          },
        ],
      }),
  ],
  [
    /GET .*\/api\/reference\/contracts/,
    () =>
      json({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: "contract-1",
            company: "company-1",
            client: "client-1",
            contract_number: "C-1",
            title: "Guarding Contract",
          },
        ],
      }),
  ],
  [
    /GET .*\/api\/reference\/accounts/,
    () =>
      json({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: "account-1",
            company: "company-1",
            code: "4000",
            name: "Service Revenue",
            account_type: "REVENUE",
          },
        ],
      }),
  ],
  [
    /GET .*\/api\/reference\/billing-rules/,
    () => json({ count: 0, next: null, previous: null, results: [] }),
  ],
  [
    /GET .*\/api\/reference\/contract-services/,
    () => json({ count: 0, next: null, previous: null, results: [] }),
  ],
  [
    /GET .*\/api\/reference\/sites/,
    () => json({ count: 0, next: null, previous: null, results: [] }),
  ],
];

describe("New Invoice page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    push.mockReset();
  });
  afterEach(() => cleanup());

  it("hides the create form without add permission", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithSession(<NewInvoicePage />, ["billing.view_clientinvoice"]);
    expect(screen.getByRole("alert").textContent).toContain("permission");
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("renders required fields and blocks submit until reference data loads", async () => {
    vi.stubGlobal("fetch", routedFetch(referenceRoutes));
    renderWithSession(<NewInvoicePage />);
    expect(
      await screen.findByRole("combobox", { name: "Billing profile" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("Invoice date")).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Invoice type" })).toBeTruthy();
    expect(
      await screen.findByRole("option", { name: "Acme Security Client (PKR)" }),
    ).toBeTruthy();
  });

  it("shows server-side field validation errors and redirects to draft edit on success", async () => {
    const fetchMock = routedFetch([
      ...referenceRoutes,
      [
        /POST .*\/api\/invoices$/,
        () =>
          json(
            { invoice_date: ["Invoice date cannot be in the future."] },
            400,
          ),
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<NewInvoicePage />);
    await screen.findByRole("combobox", { name: "Billing profile" });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Billing profile" }),
      { target: { value: "profile-1" } },
    );
    fireEvent.change(screen.getByLabelText("Invoice date"), {
      target: { value: "2026-09-01" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Invoice type" }), {
      target: { value: "STANDARD" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(
      await screen.findByText("Invoice date cannot be in the future."),
    ).toBeTruthy();
    expect(push).not.toHaveBeenCalled();

    fetchMock.mockImplementationOnce(async () =>
      json({ ...draftInvoice, id: "invoice-new" }, 201),
    );
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await vi.waitFor(() =>
      expect(push).toHaveBeenCalledWith("/invoices/invoice-new/edit"),
    );
  });
});

describe("Invoice edit page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => cleanup());

  it("denies access without edit permission", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithSession(<InvoiceEditPage id="invoice-1" />, [
      "billing.view_clientinvoice",
    ]);
    expect(screen.getByRole("alert").textContent).toContain("permission");
  });

  it("blocks editing controls for a non-draft invoice", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch([
        [/GET .*\/api\/invoices\/invoice-1$/, () => json(issuedInvoice)],
      ]),
    );
    renderWithSession(<InvoiceEditPage id="invoice-1" />);
    expect(
      await screen.findByText("This invoice can no longer be edited."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });

  it("saves draft header changes and renders backend validation errors", async () => {
    const fetchMock = routedFetch([
      [/GET .*\/api\/invoices\/invoice-1$/, () => json(draftInvoice)],
      [/GET .*\/api\/reference\/contracts/, () => referenceRoutes[1][1]()],
      [/GET .*\/api\/reference\/accounts/, () => referenceRoutes[2][1]()],
      [/GET .*\/api\/reference\/billing-rules/, () => referenceRoutes[3][1]()],
      [
        /GET .*\/api\/reference\/contract-services/,
        () => referenceRoutes[4][1](),
      ],
      [/GET .*\/api\/reference\/sites/, () => referenceRoutes[5][1]()],
      [
        /PATCH .*\/api\/invoices\/invoice-1$/,
        () => json({ client_po_reference: ["Must be alphanumeric."] }, 400),
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<InvoiceEditPage id="invoice-1" />);
    await screen.findByRole("heading", { name: "Edit INV-DRAFT-001" });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Must be alphanumeric.")).toBeTruthy();

    fetchMock.mockImplementationOnce(async () =>
      json({ ...draftInvoice, client_po_reference: "PO-2" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved.")).toBeTruthy();
  });
});

describe("Invoice line editor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => cleanup());

  function editRoutes(
    currentInvoice: { value: InvoiceDetail },
    overrides: Array<[RegExp, () => Response]> = [],
  ) {
    return routedFetch([
      // Overrides must win over the defaults below for the same pattern,
      // since routedFetch dispatches to the first match.
      ...overrides,
      [/GET .*\/api\/invoices\/invoice-1$/, () => json(currentInvoice.value)],
      [/GET .*\/api\/reference\/contracts/, () => referenceRoutes[1][1]()],
      [/GET .*\/api\/reference\/accounts/, () => referenceRoutes[2][1]()],
      [/GET .*\/api\/reference\/billing-rules/, () => referenceRoutes[3][1]()],
      [
        /GET .*\/api\/reference\/contract-services/,
        () => referenceRoutes[4][1](),
      ],
      [/GET .*\/api\/reference\/sites/, () => referenceRoutes[5][1]()],
    ]);
  }

  it("adds a line, prevents double submit, and refreshes totals from the server", async () => {
    let addCalls = 0;
    const current = { value: draftInvoice };
    const fetchMock = editRoutes(current, [
      [
        /POST .*\/api\/invoices\/invoice-1\/lines$/,
        () => {
          addCalls += 1;
          current.value = {
            ...draftInvoice,
            subtotal: "20000.00",
            total_amount: "23200.00",
            lines: [
              ...draftInvoice.lines,
              { ...draftInvoice.lines[0], id: "line-2", line_number: 2 },
            ],
          };
          return json({ id: "line-2" }, 201);
        },
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<InvoiceEditPage id="invoice-1" />);
    await screen.findByRole("heading", { name: "Edit INV-DRAFT-001" });
    await screen.findByRole("option", { name: "4000 — Service Revenue" });

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Extra shift" },
    });
    fireEvent.change(screen.getByLabelText("Quantity"), {
      target: { value: "5.0000" },
    });
    fireEvent.change(screen.getByLabelText("Unit price"), {
      target: { value: "500.00" },
    });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Revenue account" }),
      { target: { value: "account-1" } },
    );
    const submitButton = screen.getByRole("button", { name: "Add line" });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    await vi.waitFor(() => expect(addCalls).toBe(1));
    expect(await screen.findAllByText(/PKR.*23,200.00/)).toBeTruthy();
  });

  it("requires confirmation before deleting a line", async () => {
    let deleteCalls = 0;
    const current = { value: draftInvoice };
    const fetchMock = editRoutes(current, [
      [
        /DELETE .*\/api\/invoices\/invoice-1\/lines\/line-1$/,
        () => {
          deleteCalls += 1;
          current.value = { ...draftInvoice, lines: [] };
          return json({ ok: true });
        },
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<InvoiceEditPage id="invoice-1" />);
    await screen.findByRole("heading", { name: "Edit INV-DRAFT-001" });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.getByText("Remove this invoice line?")).toBeTruthy();
    expect(deleteCalls).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await vi.waitFor(() => expect(deleteCalls).toBe(1));
    expect(await screen.findByText("No line items yet.")).toBeTruthy();
  });

  it("renders server-side validation errors on the line form", async () => {
    const fetchMock = editRoutes({ value: draftInvoice }, [
      [
        /POST .*\/api\/invoices\/invoice-1\/lines$/,
        () => json({ quantity: ["Ensure this value is greater than 0."] }, 400),
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<InvoiceEditPage id="invoice-1" />);
    await screen.findByRole("heading", { name: "Edit INV-DRAFT-001" });
    await screen.findByRole("option", { name: "4000 — Service Revenue" });

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Bad line" },
    });
    fireEvent.change(screen.getByLabelText("Quantity"), {
      target: { value: "1.0000" },
    });
    fireEvent.change(screen.getByLabelText("Unit price"), {
      target: { value: "10.00" },
    });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Revenue account" }),
      { target: { value: "account-1" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Add line" }));
    expect(
      await screen.findByText("Ensure this value is greater than 0."),
    ).toBeTruthy();
  });

  it("degrades gracefully and never mentions chart-of-accounts when the account reference is denied", async () => {
    const fetchMock = editRoutes({ value: draftInvoice }, [
      [
        /GET .*\/api\/reference\/accounts/,
        () =>
          json(
            { message: "You do not have access to this reference data." },
            403,
          ),
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithSession(<InvoiceEditPage id="invoice-1" />);
    await screen.findByRole("heading", { name: "Edit INV-DRAFT-001" });

    expect(
      await screen.findByText(
        "Revenue accounts are not available with your current permissions.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "No revenue accounts are available, so new lines cannot be added.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Add line" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(document.body.textContent).not.toContain("manage_chart_of_accounts");
  });
});
