import { createServer } from "node:http";

const json = (response, status, body) => {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
};

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

createServer((request, response) => {
  const path = request.url;
  if (path === "/api/v1/health/") return json(response, 200, { status: "ok" });
  if (path === "/api/v1/auth/login/" && request.method === "POST") {
    return json(response, 200, {
      access: "e2e-access",
      refresh: "e2e-refresh",
    });
  }
  if (path === "/api/v1/auth/refresh/" && request.method === "POST") {
    return json(response, 200, {
      access: "e2e-access-rotated",
      refresh: "e2e-refresh-rotated",
    });
  }
  if (path === "/api/v1/auth/logout/" && request.method === "POST") {
    response.writeHead(204);
    return response.end();
  }
  if (!request.headers.authorization?.startsWith("Bearer e2e-access")) {
    return json(response, 401, { detail: "Unauthenticated" });
  }
  if (path === "/api/v1/auth/me/") {
    return json(response, 200, {
      id: "00000000-0000-0000-0000-000000000001",
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
    });
  }
  if (path === "/api/v1/auth/me/permissions/") {
    return json(response, 200, { permissions: ["billing.view_clientinvoice"] });
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
  return json(response, 404, { detail: "Not found" });
}).listen(4010, "127.0.0.1");
