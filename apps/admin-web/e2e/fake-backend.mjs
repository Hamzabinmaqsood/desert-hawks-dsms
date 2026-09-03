import { createServer } from "node:http";

const json = (response, status, body) => {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
};

const readJsonBody = (request) =>
  new Promise((resolve) => {
    let data = "";
    request.on("data", (chunk) => (data += chunk));
    request.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        resolve({});
      }
    });
  });

const MAKER_ID = "00000000-0000-0000-0000-000000000001";
const APPROVER_ID = "00000000-0000-0000-0000-000000000002";

// Two logical actors so maker/checker separation is exercised for real: the
// maker may author and submit, the approver may approve, issue and download.
// Neither set is a superset of the other.
const AUTHORING_PERMISSIONS = [
  "billing.view_clientinvoice",
  "billing.add_clientinvoice",
  "billing.change_clientinvoice",
];

const ACTORS = {
  employee: {
    id: MAKER_ID,
    email: "employee@example.test",
    first_name: "Test",
    last_name: "Employee",
    permissions: AUTHORING_PERMISSIONS,
  },
  maker: {
    id: MAKER_ID,
    email: "maker@example.test",
    first_name: "Test",
    last_name: "Employee",
    permissions: AUTHORING_PERMISSIONS,
  },
  approver: {
    id: APPROVER_ID,
    email: "approver@example.test",
    first_name: "Test",
    last_name: "Approver",
    permissions: [
      "billing.view_clientinvoice",
      "billing.approve_invoice",
      "billing.issue_invoice",
      "billing.download_invoice",
    ],
  },
};

const actorKeyForEmail = (email) => {
  const key = String(email ?? "").split("@")[0];
  return Object.hasOwn(ACTORS, key) ? key : "employee";
};

const actorForToken = (authorization) => {
  const key = String(authorization ?? "").split("-")[2];
  return ACTORS[key] ?? ACTORS.employee;
};

const DRAFT_ID = "90000000-0000-0000-0000-000000000001";
const ACCOUNT_ID = "50000000-0000-0000-0000-000000000099";

function freshDraft() {
  return {
    id: DRAFT_ID,
    invoice_number: "INV-E2E-DRAFT-001",
    company: "00000000-0000-0000-0000-000000000002",
    client: "20000000-0000-0000-0000-000000000001",
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
    subtotal: "0.00",
    discount_total: "0.00",
    tax_total: "0.00",
    adjustment_total: "0.00",
    total_amount: "0.00",
    amount_paid: "0.00",
    balance_due: "0.00",
    status: "DRAFT",
    generated_by: "00000000-0000-0000-0000-000000000001",
    reviewed_by: null,
    reviewed_at: null,
    approved_by: null,
    approved_at: null,
    issued_by: null,
    issued_at: null,
    voided_by: null,
    voided_at: null,
    void_reason: "",
    billing_name_snapshot: "E2E Draft Client",
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
    lines: [],
  };
}

let draft = freshDraft();

function recomputeTotals() {
  const sum = (key) =>
    draft.lines.reduce((total, line) => total + Number(line[key]), 0);
  draft.subtotal = sum("gross_amount").toFixed(2);
  draft.discount_total = sum("discount_amount").toFixed(2);
  draft.tax_total = sum("tax_amount").toFixed(2);
  draft.total_amount = sum("line_total").toFixed(2);
  draft.balance_due = (
    Number(draft.total_amount) - Number(draft.amount_paid)
  ).toFixed(2);
}

const invoice = {
  id: "10000000-0000-0000-0000-000000000001",
  invoice_number: "INV-E2E-001",
  company: "00000000-0000-0000-0000-000000000002",
  client: "20000000-0000-0000-0000-000000000001",
  contract: "30000000-0000-0000-0000-000000000001",
  invoice_type: "SERVICE",
  currency: "PKR",
  invoice_date: "2026-08-01",
  service_period_start: "2026-07-01",
  service_period_end: "2026-07-31",
  due_date: "2026-08-31",
  client_po_reference: "PO-E2E",
  client_reference: "REF-E2E",
  source_billing_schedule: null,
  subtotal: "10000.00",
  discount_total: "0.00",
  tax_total: "1600.00",
  adjustment_total: "0.00",
  total_amount: "11600.00",
  amount_paid: "0.00",
  balance_due: "11600.00",
  status: "ISSUED",
  generated_by: "00000000-0000-0000-0000-000000000001",
  reviewed_by: null,
  reviewed_at: null,
  approved_by: null,
  approved_at: "2026-08-02T10:00:00Z",
  issued_by: null,
  issued_at: "2026-08-03T10:00:00Z",
  voided_by: null,
  voided_at: null,
  void_reason: "",
  billing_name_snapshot: "E2E Security Client",
  billing_address_snapshot: "Test address",
  tax_registration_snapshot: "",
  payment_terms_snapshot: 30,
  payment_instructions_snapshot: "",
  notes_snapshot: "",
  posted_at: "2026-08-03T10:00:00Z",
  created_at: "2026-08-01T09:00:00Z",
  updated_at: "2026-08-03T10:00:00Z",
  is_overdue: false,
  pdf_available: false,
  lines: [
    {
      id: "40000000-0000-0000-0000-000000000001",
      line_number: 1,
      contract_service: null,
      site: null,
      billing_rule: null,
      description: "Monthly guarding service",
      quantity: "10.0000",
      unit: "SHIFT",
      unit_price: "1000.00",
      gross_amount: "10000.00",
      discount_amount: "0.00",
      taxable_amount: "10000.00",
      tax_amount: "1600.00",
      line_total: "11600.00",
      revenue_account: "50000000-0000-0000-0000-000000000001",
      cost_center: null,
      created_at: "2026-08-01T09:00:00Z",
    },
  ],
};

createServer(async (request, response) => {
  const path = request.url;
  if (path === "/api/v1/health/") return json(response, 200, { status: "ok" });
  if (path === "/api/v1/auth/login/" && request.method === "POST") {
    const body = await readJsonBody(request);
    const key = actorKeyForEmail(body.email);
    return json(response, 200, {
      access: `e2e-access-${key}`,
      refresh: `e2e-refresh-${key}`,
    });
  }
  if (path === "/api/v1/auth/refresh/" && request.method === "POST") {
    const body = await readJsonBody(request);
    const key = String(body.refresh ?? "").split("-")[2];
    return json(response, 200, {
      access: `e2e-access-${key ?? "employee"}-rotated`,
      refresh: `e2e-refresh-${key ?? "employee"}-rotated`,
    });
  }
  if (path === "/api/v1/auth/logout/" && request.method === "POST") {
    response.writeHead(204);
    return response.end();
  }
  if (!request.headers.authorization?.startsWith("Bearer e2e-access")) {
    return json(response, 401, { detail: "Unauthenticated" });
  }
  const actor = actorForToken(request.headers.authorization);
  if (path === "/api/v1/auth/me/") {
    return json(response, 200, {
      id: actor.id,
      email: actor.email,
      first_name: actor.first_name,
      last_name: actor.last_name,
      is_active: true,
      is_staff: false,
      is_superuser: false,
      last_login: null,
      date_joined: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  }
  if (path === "/api/v1/auth/me/permissions/") {
    return json(response, 200, { permissions: actor.permissions });
  }
  if (path === "/api/v1/auth/me/access-scopes/") {
    return json(response, 200, {
      is_superuser: false,
      accessible_company_ids: ["00000000-0000-0000-0000-000000000002"],
      accessible_region_ids: [],
      accessible_branch_ids: [],
      accessible_department_ids: [],
      accessible_operational_zone_ids: [],
      assignments: [],
    });
  }
  if (path === "/api/v1/billing/billing-profiles/?is_active=true") {
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "10000000-0000-0000-0000-000000000099",
          client: "20000000-0000-0000-0000-000000000001",
          company: "00000000-0000-0000-0000-000000000002",
          billing_name: "E2E Draft Client",
          currency: "PKR",
          payment_terms_days: 30,
        },
      ],
    });
  }
  if (path === "/api/v1/contracts/contracts/") {
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  }
  if (path === "/api/v1/contracts/contract-services/") {
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  }
  if (path === "/api/v1/contracts/sites/") {
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  }
  if (path === "/api/v1/billing/billing-rules/") {
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  }
  if (path === "/api/v1/billing/invoice-reference/revenue-accounts/") {
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: ACCOUNT_ID,
          company: "00000000-0000-0000-0000-000000000002",
          code: "4000",
          name: "Service Revenue",
          account_type: "REVENUE",
        },
      ],
    });
  }
  if (path === "/api/v1/billing/invoices/" && request.method === "POST") {
    const body = await readJsonBody(request);
    draft = {
      ...freshDraft(),
      invoice_date: body.invoice_date ?? "2026-09-01",
      invoice_type: body.invoice_type ?? "STANDARD",
      contract: body.contract ?? null,
      service_period_start: body.service_period_start ?? null,
      service_period_end: body.service_period_end ?? null,
      client_po_reference: body.client_po_reference ?? "",
      client_reference: body.client_reference ?? "",
    };
    return json(response, 201, draft);
  }
  if (
    path === `/api/v1/billing/invoices/${DRAFT_ID}/` &&
    request.method === "PATCH"
  ) {
    const body = await readJsonBody(request);
    draft = { ...draft, ...body, updated_at: new Date().toISOString() };
    return json(response, 200, draft);
  }
  if (
    path === `/api/v1/billing/invoices/${DRAFT_ID}/lines/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const quantity = Number(body.quantity ?? 0);
    const unitPrice = Number(body.unit_price ?? 0);
    const discount = Number(body.discount_amount ?? 0);
    const taxRate = Number(body.tax_rate ?? 0);
    const gross = quantity * unitPrice;
    const taxable = gross - discount;
    const tax = (taxable * taxRate) / 100;
    const line = {
      id: `line-e2e-${draft.lines.length + 1}`,
      line_number: draft.lines.length + 1,
      contract_service: body.contract_service ?? null,
      site: body.site ?? null,
      billing_rule: body.billing_rule ?? null,
      description: body.description ?? "",
      quantity: quantity.toFixed(4),
      unit: body.unit ?? "SERVICE",
      unit_price: unitPrice.toFixed(2),
      gross_amount: gross.toFixed(2),
      discount_amount: discount.toFixed(2),
      taxable_amount: taxable.toFixed(2),
      tax_amount: tax.toFixed(2),
      line_total: (taxable + tax).toFixed(2),
      revenue_account: body.revenue_account ?? ACCOUNT_ID,
      cost_center: null,
      created_at: new Date().toISOString(),
    };
    draft.lines.push(line);
    recomputeTotals();
    return json(response, 201, line);
  }
  if (
    path?.startsWith(`/api/v1/billing/invoices/${DRAFT_ID}/lines/`) &&
    request.method === "PATCH"
  ) {
    const lineId = path.split("/").filter(Boolean).pop();
    const body = await readJsonBody(request);
    const existing = draft.lines.find((line) => line.id === lineId);
    if (!existing) return json(response, 404, { detail: "Not found" });
    const quantity = Number(body.quantity ?? existing.quantity);
    const unitPrice = Number(body.unit_price ?? existing.unit_price);
    const discount = Number(body.discount_amount ?? existing.discount_amount);
    const taxRate = Number(body.tax_rate ?? 0);
    const gross = quantity * unitPrice;
    const taxable = gross - discount;
    const tax = (taxable * taxRate) / 100;
    Object.assign(existing, {
      description: body.description ?? existing.description,
      quantity: quantity.toFixed(4),
      unit_price: unitPrice.toFixed(2),
      gross_amount: gross.toFixed(2),
      discount_amount: discount.toFixed(2),
      taxable_amount: taxable.toFixed(2),
      tax_amount: tax.toFixed(2),
      line_total: (taxable + tax).toFixed(2),
    });
    recomputeTotals();
    return json(response, 200, existing);
  }
  // Workflow transitions mirror the backend state machine: each one accepts a
  // single source status, and approval enforces maker/checker. Nothing here
  // succeeds unconditionally.
  if (
    path === `/api/v1/billing/invoices/${DRAFT_ID}/submit/` &&
    request.method === "POST"
  ) {
    if (draft.status !== "DRAFT" || draft.lines.length === 0)
      return json(response, 400, {
        detail: ["Only a non-empty draft invoice can be submitted."],
      });
    draft.status = "UNDER_REVIEW";
    return json(response, 200, draft);
  }
  if (
    path === `/api/v1/billing/invoices/${DRAFT_ID}/approve/` &&
    request.method === "POST"
  ) {
    if (draft.status !== "UNDER_REVIEW")
      return json(response, 400, { detail: ["Invoice is not under review."] });
    if (draft.generated_by === actor.id)
      return json(response, 400, {
        detail: ["Maker/checker policy prevents self-approval."],
      });
    draft.status = "APPROVED";
    draft.approved_by = actor.id;
    draft.approved_at = "2026-09-02T10:00:00Z";
    return json(response, 200, draft);
  }
  if (
    path === `/api/v1/billing/invoices/${DRAFT_ID}/issue/` &&
    request.method === "POST"
  ) {
    if (draft.status !== "APPROVED")
      return json(response, 400, {
        detail: ["Only approved invoices can be issued."],
      });
    draft.status = "ISSUED";
    draft.issued_by = actor.id;
    draft.issued_at = "2026-09-03T10:00:00Z";
    draft.posted_at = "2026-09-03T10:00:00Z";
    draft.pdf_available = true;
    return json(response, 200, draft);
  }
  if (path === `/api/v1/billing/invoices/${DRAFT_ID}/download/`) {
    if (!draft.pdf_available)
      return json(response, 404, { detail: "Not found" });
    response.writeHead(200, {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="${draft.invoice_number}.pdf"`,
    });
    return response.end(
      ["%PDF-1.4", "% e2e fake invoice", "%%EOF", ""].join("\n"),
    );
  }
  if (
    path?.startsWith("/api/v1/billing/invoices/?") ||
    path === "/api/v1/billing/invoices/"
  ) {
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [invoice],
    });
  }
  if (path === `/api/v1/billing/invoices/${invoice.id}/`) {
    return json(response, 200, invoice);
  }
  if (path === `/api/v1/billing/invoices/${DRAFT_ID}/`) {
    return json(response, 200, draft);
  }
  return json(response, 404, { detail: "Not found" });
}).listen(4010, "127.0.0.1");
