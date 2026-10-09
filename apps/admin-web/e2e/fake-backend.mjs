import { createServer } from "node:http";

const json = (response, status, body, headers = {}) => {
  response.writeHead(status, {
    "Content-Type": "application/json",
    ...headers,
  });
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
const COMPANY_A = {
  id: "00000000-0000-0000-0000-000000000002",
  code: "DHA",
  display_name: "Desert Hawks Alpha",
  legal_name: "Desert Hawks Alpha Limited",
  is_active: true,
  branding: {
    display_name: "Alpha Shield",
    tagline: "Alpha operations",
    primary_color: "#174D34",
    accent_color: "#D6A84F",
    can_manage: false,
  },
  business_settings: {
    default_currency: "USD",
    timezone: "America/New_York",
    invoice_number_prefix: "AINV",
    receipt_number_prefix: "AREC",
    credit_note_number_prefix: "ACN",
    debit_note_number_prefix: "ADN",
    can_manage: false,
  },
};
const COMPANY_B = {
  id: "00000000-0000-0000-0000-000000000003",
  code: "DHB",
  display_name: "Desert Hawks Bravo",
  legal_name: "Desert Hawks Bravo Limited",
  is_active: true,
  branding: {
    display_name: "Bravo Guard",
    tagline: "Bravo operations",
    primary_color: "#243B6B",
    accent_color: "#4DB6AC",
    can_manage: false,
  },
  business_settings: {
    default_currency: "AED",
    timezone: "Asia/Dubai",
    invoice_number_prefix: "BINV",
    receipt_number_prefix: "BREC",
    credit_note_number_prefix: "BCN",
    debit_note_number_prefix: "BDN",
    can_manage: false,
  },
};
const companyContexts = new Map();

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
  multicompany: {
    id: MAKER_ID,
    email: "multicompany@example.test",
    first_name: "Multi",
    last_name: "Company",
    permissions: AUTHORING_PERMISSIONS,
    companies: [COMPANY_A, COMPANY_B],
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
  receiptmaker: {
    id: MAKER_ID,
    email: "receiptmaker@example.test",
    first_name: "Receipt",
    last_name: "Maker",
    permissions: ["billing.view_clientreceipt", "billing.add_clientreceipt"],
  },
  receiptchecker: {
    id: APPROVER_ID,
    email: "receiptchecker@example.test",
    first_name: "Receipt",
    last_name: "Checker",
    permissions: [
      "billing.view_clientreceipt",
      "billing.confirm_receipt",
      "billing.allocate_receipt",
      "billing.view_clientinvoice",
    ],
  },
  vendormanager: {
    id: MAKER_ID,
    email: "vendormanager@example.test",
    first_name: "Vendor",
    last_name: "Manager",
    permissions: [
      "finance.view_vendor",
      "finance.add_vendor",
      "finance.change_vendor",
    ],
  },
  billauthor: {
    id: MAKER_ID,
    email: "billauthor@example.test",
    first_name: "Bill",
    last_name: "Author",
    permissions: [
      "finance.view_vendorbill",
      "finance.add_vendorbill",
      "finance.change_vendorbill",
      "finance.view_vendor",
      "finance.add_vendorbillline",
      "finance.change_vendorbillline",
      "finance.delete_vendorbillline",
      "finance.manage_finance_attachments",
    ],
  },
  billchecker: {
    id: APPROVER_ID,
    email: "billchecker@example.test",
    first_name: "Bill",
    last_name: "Checker",
    permissions: [
      "finance.view_vendorbill",
      "finance.approve_finance",
      "finance.post_journal",
      "finance.manage_finance_attachments",
    ],
  },
  paymentmaker: {
    id: MAKER_ID,
    email: "paymentmaker@example.test",
    first_name: "Payment",
    last_name: "Maker",
    permissions: [
      "finance.view_paymentvoucher",
      "finance.add_paymentvoucher",
      "finance.change_paymentvoucher",
      "finance.view_vendorbill",
    ],
  },
  paymentchecker: {
    id: APPROVER_ID,
    email: "paymentchecker@example.test",
    first_name: "Payment",
    last_name: "Checker",
    permissions: [
      "finance.view_paymentvoucher",
      "finance.view_vendorbill",
      "finance.approve_finance",
      "finance.post_journal",
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

const actorBody = (actor) => ({
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

const contextSessionId = (request) =>
  String(request.headers.cookie ?? "").match(
    /(?:^|;\s*)sessionid=([^;]+)/,
  )?.[1];

const contextBody = (request, actor) => {
  const companies = actor.companies ?? [COMPANY_A];
  const sessionId = contextSessionId(request);
  const selectedId =
    companies.length === 1 ? companies[0].id : companyContexts.get(sessionId);
  const selectedCompany =
    companies.find((company) => company.id === selectedId) ?? null;
  return {
    user: actorBody(actor),
    companies: companies.map((company) => ({
      id: company.id,
      code: company.code,
      display_name: company.display_name,
      legal_name: company.legal_name,
      is_active: company.is_active,
    })),
    selected_company: selectedCompany,
    selection_required: companies.length > 0 && !selectedCompany,
  };
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
  receipt_allocations: [],
};

const RECEIPT_ID = "70000000-0000-0000-0000-000000000001";
let receipt = null;

const VENDOR_ID = "80000000-0000-0000-0000-000000000001";
const PAYABLE_ACCOUNT_ID = "50000000-0000-0000-0000-000000000200";
let vendor = {
  id: VENDOR_ID,
  code: "V-E2E-001",
  name: "E2E Updated Supplier",
  tax_number: "NTN-E2E",
  email: "supplier@example.test",
  phone: "",
  payment_terms_days: 30,
  payable_account: PAYABLE_ACCOUNT_ID,
  is_active: true,
};

const VENDOR_BILL_ID = "81000000-0000-0000-0000-000000000001";
const VENDOR_BILL_ACCOUNT_ID = "50000000-0000-0000-0000-000000000300";
let vendorBill = null;
let vendorBillAttachment = null;
const VENDOR_PAYMENT_ID = "84000000-0000-0000-0000-000000000001";
const PAYMENT_ACCOUNT_ID = "50000000-0000-0000-0000-000000000400";
let vendorPayment = null;
const vendorBillBody = () => ({
  ...vendorBill,
  vendor_code: vendor?.code ?? "V-E2E-001",
  vendor_name: vendor?.name ?? "E2E Updated Supplier",
  outstanding_amount: vendorBill
    ? (
        Number(vendorBill.total_amount) - Number(vendorBill.paid_amount)
      ).toFixed(2)
    : "0.00",
  payments: vendorPayment
    ? [
        {
          id: vendorPayment.id,
          voucher_number: vendorPayment.voucher_number,
          payment_date: vendorPayment.payment_date,
          amount: vendorPayment.amount,
          status: vendorPayment.status,
          payment_status: vendorPayment.payment_status,
          payment_reference: vendorPayment.payment_reference,
        },
      ]
    : [],
});
function recomputeVendorBill() {
  const lines = vendorBill?.lines ?? [];
  vendorBill.subtotal = lines
    .reduce(
      (sum, line) => sum + Number(line.quantity) * Number(line.unit_price),
      0,
    )
    .toFixed(2);
  vendorBill.tax_amount = lines
    .reduce((sum, line) => sum + Number(line.tax_amount), 0)
    .toFixed(2);
  vendorBill.total_amount = (
    Number(vendorBill.subtotal) + Number(vendorBill.tax_amount)
  ).toFixed(2);
}

const vendorBody = () => ({
  ...vendor,
  payable_account_code: "2000",
  payable_account_name: "Trade Payables",
  created_at: "2026-09-13T09:00:00Z",
  updated_at: "2026-09-13T09:00:00Z",
});

function receiptBody() {
  return {
    ...receipt,
    allocated_amount:
      receipt?.allocations
        .reduce((sum, item) => sum + Number(item.amount), 0)
        .toFixed(2) ?? "0.00",
    unallocated_amount: receipt
      ? (
          Number(receipt.amount) -
          receipt.allocations.reduce(
            (sum, item) => sum + Number(item.amount),
            0,
          )
        ).toFixed(2)
      : "0.00",
  };
}

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
    companyContexts.delete(contextSessionId(request));
    response.writeHead(204);
    return response.end();
  }
  if (!request.headers.authorization?.startsWith("Bearer e2e-access")) {
    return json(response, 401, { detail: "Unauthenticated" });
  }
  const actor = actorForToken(request.headers.authorization);
  if (path === "/api/v1/auth/company-context/" && request.method === "GET") {
    return json(response, 200, contextBody(request, actor));
  }
  if (path === "/api/v1/auth/company-context/" && request.method === "PUT") {
    const body = await readJsonBody(request);
    const companies = actor.companies ?? [COMPANY_A];
    if (!companies.some((company) => company.id === body.company_id)) {
      return json(response, 404, { detail: "Not found." });
    }
    const sessionId = `context${String(actor.email).split("@")[0]}${String(body.company_id).slice(-1)}`;
    companyContexts.set(sessionId, body.company_id);
    const syntheticRequest = {
      headers: { cookie: `sessionid=${sessionId}` },
    };
    return json(response, 200, contextBody(syntheticRequest, actor), {
      "Set-Cookie": `sessionid=${sessionId}; Path=/; HttpOnly; SameSite=Lax`,
    });
  }
  if (path === "/api/v1/auth/company-branding/" && request.method === "GET") {
    const context = contextBody(request, actor);
    if (!context.selected_company)
      return json(response, 404, { detail: "Not found." });
    return json(response, 200, context.selected_company.branding);
  }
  if (
    path === "/api/v1/auth/company-business-settings/" &&
    request.method === "GET"
  ) {
    const context = contextBody(request, actor);
    if (!context.selected_company)
      return json(response, 404, { detail: "Not found." });
    return json(response, 200, context.selected_company.business_settings);
  }
  if (path === "/api/v1/auth/me/") {
    return json(response, 200, actorBody(actor));
  }
  if (path === "/api/v1/auth/me/permissions/") {
    return json(response, 200, { permissions: actor.permissions });
  }
  if (path === "/api/v1/auth/me/access-scopes/") {
    return json(response, 200, {
      is_superuser: false,
      accessible_company_ids: (actor.companies ?? [COMPANY_A]).map(
        (company) => company.id,
      ),
      accessible_region_ids: [],
      accessible_branch_ids: [],
      accessible_department_ids: [],
      accessible_operational_zone_ids: [],
      assignments: [],
    });
  }
  if (path === "/api/v1/finance/ap-reference/payable-accounts/")
    return json(response, 200, [
      { id: PAYABLE_ACCOUNT_ID, code: "2000", name: "Trade Payables" },
    ]);
  if (path === "/api/v1/finance/vendors/" && request.method === "POST") {
    const body = await readJsonBody(request);
    vendor = {
      id: VENDOR_ID,
      code: body.code,
      name: body.name,
      tax_number: body.tax_number ?? "",
      email: body.email ?? "",
      phone: body.phone ?? "",
      payment_terms_days: Number(body.payment_terms_days),
      payable_account: body.payable_account,
      is_active: body.is_active ?? true,
    };
    return json(response, 201, vendorBody());
  }
  if (
    path === `/api/v1/finance/vendors/${VENDOR_ID}/` &&
    request.method === "PATCH"
  ) {
    const body = await readJsonBody(request);
    vendor = { ...vendor, ...body };
    return json(response, 200, vendorBody());
  }
  if (path === `/api/v1/finance/vendors/${VENDOR_ID}/`)
    return vendor
      ? json(response, 200, vendorBody())
      : json(response, 404, { detail: "Not found" });
  if (
    path === "/api/v1/finance/vendors/" ||
    path?.startsWith("/api/v1/finance/vendors/?")
  ) {
    const query = new URL(path, "http://backend.test").searchParams;
    const matches =
      vendor &&
      (!query.get("search") ||
        `${vendor.code} ${vendor.name}`
          .toLowerCase()
          .includes(query.get("search").toLowerCase())) &&
      (!query.get("is_active") ||
        String(vendor.is_active) === query.get("is_active"));
    return json(response, 200, {
      count: matches ? 1 : 0,
      next: null,
      previous: null,
      results: matches ? [vendorBody()] : [],
    });
  }
  if (path === "/api/v1/finance/ap-reference/expense-accounts/")
    return json(response, 200, [
      {
        id: VENDOR_BILL_ACCOUNT_ID,
        code: "5000",
        name: "Operating Supplies",
        account_type: "EXPENSE",
      },
    ]);
  if (path === "/api/v1/finance/vendor-bills/" && request.method === "POST") {
    const body = await readJsonBody(request);
    vendorBill = {
      id: VENDOR_BILL_ID,
      ...body,
      status: "DRAFT",
      subtotal: "0.00",
      tax_amount: "0.00",
      total_amount: "0.00",
      paid_amount: "0.00",
      match_exception: "",
      purchase_order: null,
      lines: [],
    };
    return json(response, 201, vendorBillBody());
  }
  if (
    path === `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/` &&
    request.method === "PATCH"
  ) {
    vendorBill = { ...vendorBill, ...(await readJsonBody(request)) };
    return json(response, 200, vendorBillBody());
  }
  if (path === `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/`)
    return vendorBill
      ? json(response, 200, vendorBillBody())
      : json(response, 404, { detail: "Not found" });
  for (const [action, target] of [
    ["submit", "SUBMITTED"],
    ["approve", "APPROVED"],
    ["post", "POSTED"],
  ]) {
    if (
      path === `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/${action}/` &&
      request.method === "POST"
    ) {
      vendorBill.status = target;
      return json(response, 200, vendorBillBody());
    }
  }
  if (
    path === `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/attachments/` &&
    request.method === "POST"
  ) {
    request.resume();
    vendorBillAttachment = {
      id: "83000000-0000-0000-0000-000000000001",
      filename: "supplier-invoice.pdf",
      content_type: "application/pdf",
      size: 14,
      created_at: "2026-09-17T10:00:00Z",
    };
    return json(response, 201, vendorBillAttachment);
  }
  if (path === `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/attachments/`)
    return json(
      response,
      200,
      vendorBillAttachment ? [vendorBillAttachment] : [],
    );
  if (
    path ===
    `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/attachments/83000000-0000-0000-0000-000000000001/download/`
  ) {
    response.writeHead(200, {
      "Content-Type": "application/pdf",
      "Content-Disposition": "attachment; filename=supplier-invoice.pdf",
      "Cache-Control": "private, no-store",
    });
    return response.end("%PDF-1.4\n%%EOF");
  }
  if (
    path === `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/lines/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const line = {
      id: "82000000-0000-0000-0000-000000000001",
      purchase_order_line: null,
      receipt_line: null,
      ...body,
      expense_account_code: "5000",
      expense_account_name: "Operating Supplies",
      line_total: (
        Number(body.quantity) * Number(body.unit_price) +
        Number(body.tax_amount)
      ).toFixed(2),
    };
    vendorBill.lines.push(line);
    recomputeVendorBill();
    return json(response, 201, line);
  }
  if (
    path ===
      `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/lines/82000000-0000-0000-0000-000000000001/` &&
    request.method === "PATCH"
  ) {
    const body = await readJsonBody(request);
    vendorBill.lines[0] = { ...vendorBill.lines[0], ...body };
    vendorBill.lines[0].line_total = (
      Number(vendorBill.lines[0].quantity) *
        Number(vendorBill.lines[0].unit_price) +
      Number(vendorBill.lines[0].tax_amount)
    ).toFixed(2);
    recomputeVendorBill();
    return json(response, 200, vendorBill.lines[0]);
  }
  if (
    path ===
      `/api/v1/finance/vendor-bills/${VENDOR_BILL_ID}/lines/82000000-0000-0000-0000-000000000001/` &&
    request.method === "DELETE"
  ) {
    vendorBill.lines = [];
    recomputeVendorBill();
    response.writeHead(204);
    return response.end();
  }
  if (
    path === "/api/v1/finance/vendor-bills/" ||
    path?.startsWith("/api/v1/finance/vendor-bills/?")
  )
    return json(response, 200, {
      count: vendorBill ? 1 : 0,
      next: null,
      previous: null,
      results: vendorBill ? [vendorBillBody()] : [],
    });
  if (path === "/api/v1/finance/ap-reference/payable-bills/")
    return json(
      response,
      200,
      vendorBill && ["POSTED", "PARTIALLY_PAID"].includes(vendorBill.status)
        ? [vendorBillBody()]
        : [],
    );
  if (path === "/api/v1/finance/ap-reference/payment-accounts/")
    return json(response, 200, [
      {
        id: PAYMENT_ACCOUNT_ID,
        code: "1100",
        name: "Operating Bank",
        account_type: "ASSET",
      },
    ]);
  if (
    path === "/api/v1/finance/vendor-payments/" &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    vendorPayment = {
      id: VENDOR_PAYMENT_ID,
      ...body,
      bill_number: vendorBill.bill_number,
      vendor_name: vendor?.name ?? "E2E Updated Supplier",
      status: "DRAFT",
      payment_status: "PENDING",
    };
    return json(response, 201, vendorPayment);
  }
  if (path === `/api/v1/finance/vendor-payments/${VENDOR_PAYMENT_ID}/`)
    return vendorPayment
      ? json(response, 200, vendorPayment)
      : json(response, 404, { detail: "Not found" });
  for (const [action, target] of [
    ["submit", "SUBMITTED"],
    ["approve", "APPROVED"],
    ["reject", "REJECTED"],
  ]) {
    if (
      path ===
        `/api/v1/finance/vendor-payments/${VENDOR_PAYMENT_ID}/${action}/` &&
      request.method === "POST"
    ) {
      vendorPayment.status = target;
      return json(response, 200, vendorPayment);
    }
  }
  if (
    path === `/api/v1/finance/vendor-payments/${VENDOR_PAYMENT_ID}/pay/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    vendorPayment.status = "PAID";
    vendorPayment.payment_status = "PAID";
    vendorPayment.payment_reference = body.payment_reference ?? "";
    vendorBill.paid_amount = (
      Number(vendorBill.paid_amount) + Number(vendorPayment.amount)
    ).toFixed(2);
    vendorBill.status =
      Number(vendorBill.paid_amount) === Number(vendorBill.total_amount)
        ? "PAID"
        : "PARTIALLY_PAID";
    return json(response, 200, vendorPayment);
  }
  if (
    path === "/api/v1/finance/vendor-payments/" ||
    path?.startsWith("/api/v1/finance/vendor-payments/?")
  )
    return json(response, 200, {
      count: vendorPayment ? 1 : 0,
      next: null,
      previous: null,
      results: vendorPayment ? [vendorPayment] : [],
    });
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
  if (path === "/api/v1/billing/receipt-reference/clients/")
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          client: draft.client,
          company: draft.company,
          billing_name: draft.billing_name_snapshot,
          currency: "PKR",
        },
      ],
    });
  if (path === "/api/v1/billing/receipt-reference/bank-accounts/")
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "bank-1",
          company: invoice.company,
          name: "Main collections",
          bank_name: "Test Bank",
          currency: "PKR",
        },
      ],
    });
  if (path === "/api/v1/billing/receipts/" && request.method === "POST") {
    const body = await readJsonBody(request);
    receipt = {
      id: RECEIPT_ID,
      receipt_number: "RCPT-E2E-001",
      company: body.company,
      client: body.client,
      client_name: invoice.billing_name_snapshot,
      received_at: body.received_at,
      value_date: body.value_date,
      currency: body.currency,
      amount: body.amount,
      payment_method: body.payment_method,
      bank_account: body.bank_account,
      cheque_reference: body.cheque_reference ?? "",
      external_reference: body.external_reference ?? "",
      status: "DRAFT",
      notes: body.notes ?? "",
      allocations: [],
    };
    return json(response, 201, receiptBody());
  }
  if (
    path === `/api/v1/billing/receipts/${RECEIPT_ID}/confirm/` &&
    request.method === "POST"
  ) {
    receipt.status = "CONFIRMED";
    return json(response, 200, receiptBody());
  }
  if (path === `/api/v1/billing/receipts/${RECEIPT_ID}/eligible-invoices/`)
    return json(
      response,
      200,
      draft.balance_due !== "0.00"
        ? [
            {
              id: draft.id,
              invoice_number: draft.invoice_number,
              invoice_date: draft.invoice_date,
              currency: draft.currency,
              total_amount: draft.total_amount,
              amount_paid: draft.amount_paid,
              balance_due: draft.balance_due,
              status: draft.status,
            },
          ]
        : [],
    );
  if (
    path === `/api/v1/billing/receipts/${RECEIPT_ID}/allocate/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const amount = Number(body.amount);
    const allocationId = `allocation-e2e-${receipt.allocations.length + 1}`;
    receipt.allocations.push({
      id: allocationId,
      invoice: draft.id,
      invoice_number: draft.invoice_number,
      amount: amount.toFixed(2),
      allocated_at: new Date().toISOString(),
    });
    const allocated = receipt.allocations.reduce(
      (sum, allocation) => sum + Number(allocation.amount),
      0,
    );
    receipt.status =
      allocated === Number(receipt.amount)
        ? "ALLOCATED"
        : "PARTIALLY_ALLOCATED";
    draft.amount_paid = allocated.toFixed(2);
    draft.balance_due = (Number(draft.total_amount) - allocated).toFixed(2);
    draft.status = draft.balance_due === "0.00" ? "PAID" : "PARTIALLY_PAID";
    draft.receipt_allocations = receipt.allocations.map((allocation) => ({
      id: allocation.id,
      receipt: RECEIPT_ID,
      receipt_number: receipt.receipt_number,
      receipt_date: receipt.received_at,
      payment_method: receipt.payment_method,
      reference: receipt.external_reference,
      amount: allocation.amount,
      allocated_at: allocation.allocated_at,
    }));
    return json(response, 201, {
      id: allocationId,
      amount: amount.toFixed(2),
    });
  }
  if (path === `/api/v1/billing/receipts/${RECEIPT_ID}/`)
    return json(response, 200, receiptBody());
  if (
    path === "/api/v1/billing/receipts/" ||
    path?.startsWith("/api/v1/billing/receipts/?")
  )
    return json(response, 200, {
      count: receipt ? 1 : 0,
      next: null,
      previous: null,
      results: receipt ? [receiptBody()] : [],
    });
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
