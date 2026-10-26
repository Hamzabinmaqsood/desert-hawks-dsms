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
  code: "NTA",
  display_name: "Northstar Alpha",
  legal_name: "Northstar Alpha Limited",
  is_active: true,
  effective_modules: [
    "people",
    "client_contracts",
    "finance_core",
    "billing_receivables",
    "procurement_payables",
    "asset_management",
  ],
  entitlement_revision: 4,
  branding: {
    display_name: "Alpha Works",
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
  code: "NTB",
  display_name: "Northstar Bravo",
  legal_name: "Northstar Bravo Limited",
  is_active: true,
  effective_modules: ["finance_core", "procurement_payables"],
  entitlement_revision: 9,
  branding: {
    display_name: "Bravo Works",
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
const PEOPLE_COMPANY_A = {
  ...COMPANY_A,
  effective_modules: [
    ...COMPANY_A.effective_modules,
    "recruitment",
    "leave",
    "learning",
  ],
  entitlement_revision: 5,
};
const companyContexts = new Map();
const PLATFORM_PLAN = {
  id: "91000000-0000-0000-0000-000000000001",
  code: "GROWTH",
  name: "Growth",
  description: "Modular growth plan",
  is_active: true,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};
const PLATFORM_SUBSCRIPTION_ID = "92000000-0000-0000-0000-000000000001";
const SNAPSHOT_MODULES = [
  "people",
  "client_contracts",
  "finance_core",
  "billing_receivables",
  "procurement_payables",
  "asset_management",
];
let platformOverrides = [];
let platformEntitlementRevision = 4;
const PLATFORM_MODULES = [
  ["people", "People & Employee Records", []],
  ["client_contracts", "Clients & Contracts", []],
  ["finance_core", "Finance & Accounting", []],
  [
    "billing_receivables",
    "Billing & Receivables",
    ["client_contracts", "finance_core"],
  ],
  ["procurement_payables", "Procurement & Payables", ["finance_core"]],
  ["asset_management", "Asset Management", ["finance_core"]],
].map(([id, display_name, hard_dependencies]) => ({
  id,
  display_name,
  classification: "GENERAL_BUSINESS",
  hard_dependencies,
  legacy_default: true,
}));

const platformSubscription = () => ({
  id: PLATFORM_SUBSCRIPTION_ID,
  company: {
    id: COMPANY_A.id,
    code: COMPANY_A.code,
    legal_name: COMPANY_A.legal_name,
    trade_name: COMPANY_A.display_name,
    is_active: true,
  },
  plan: PLATFORM_PLAN,
  status: "ACTIVE",
  policy_mode: "SUBSCRIPTION",
  effective_module_count: COMPANY_A.effective_modules.length,
  entitlement_revision: platformEntitlementRevision,
  starts_at: "2026-10-01T00:00:00Z",
  trial_ends_at: null,
  grace_ends_at: null,
  suspended_at: null,
  terminated_at: null,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
});

const platformEntitlements = () => ({
  subscription_id: PLATFORM_SUBSCRIPTION_ID,
  subscription_status: "ACTIVE",
  company: platformSubscription().company,
  plan: PLATFORM_PLAN,
  policy_mode: "SUBSCRIPTION",
  plan_entitlement_revision: 4,
  snapshot_plan_entitlement_revision: 4,
  entitlement_revision: platformEntitlementRevision,
  snapshot_initialized: true,
  plan_module_ids: SNAPSHOT_MODULES,
  snapshot_module_ids: SNAPSHOT_MODULES,
  overrides: platformOverrides,
  effective_module_ids: COMPANY_A.effective_modules,
});

// Two logical actors so maker/checker separation is exercised for real: the
// maker may author and submit, the approver may approve, issue and download.
// Neither set is a superset of the other.
const AUTHORING_PERMISSIONS = [
  "billing.view_clientinvoice",
  "billing.add_clientinvoice",
  "billing.change_clientinvoice",
];

const ACTORS = {
  workspaceadmin: {
    id: MAKER_ID,
    email: "workspaceadmin@example.test",
    first_name: "Workspace",
    last_name: "Administrator",
    permissions: [
      "workforce.view_employee",
      "workforce.add_employee",
      "workforce.change_employee",
      "workforce.view_employeeaddress",
      "workforce.add_employeeaddress",
      "workforce.view_emergencycontact",
      "workforce.add_emergencycontact",
      "contracts.view_client",
      "contracts.add_client",
      "contracts.change_client",
      "contracts.view_clientcontact",
      "contracts.add_clientcontact",
      "contracts.view_servicecontract",
      "contracts.add_servicecontract",
      "contracts.change_servicecontract",
      "contracts.view_contractservice",
      "contracts.view_contractcommercialterms",
      "contracts.view_contractamendment",
      "contracts.view_servicelevelagreement",
    ],
  },
  workspaceviewer: {
    id: MAKER_ID,
    email: "workspaceviewer@example.test",
    first_name: "Workspace",
    last_name: "Viewer",
    permissions: [
      "workforce.view_employee",
      "contracts.view_client",
      "contracts.view_servicecontract",
    ],
  },
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
    permissions: [
      ...AUTHORING_PERMISSIONS,
      "finance.view_vendor",
      "workforce.view_employee",
      "contracts.view_client",
      "contracts.view_servicecontract",
    ],
    companies: [COMPANY_A, COMPANY_B],
  },
  platformoperator: {
    id: APPROVER_ID,
    email: "platformoperator@example.test",
    first_name: "Platform",
    last_name: "Operator",
    permissions: [],
    companies: [],
    platform_capabilities: [
      "organization.view_platform_tenant_directory",
      "subscriptions.view_plan_catalog",
      "subscriptions.manage_plan_catalog",
      "subscriptions.view_commercial_subscriptions",
      "subscriptions.manage_commercial_subscriptions",
    ],
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
  operationsadmin: {
    id: MAKER_ID,
    email: "operationsadmin@example.test",
    first_name: "Operations",
    last_name: "Administrator",
    companies: [COMPANY_A, COMPANY_B],
    permissions: [
      "finance.view_vendor",
      "finance.view_purchaserequisition",
      "finance.add_purchaserequisition",
      "finance.change_purchaserequisition",
      "finance.view_purchaseorder",
      "finance.add_purchaseorder",
      "finance.change_purchaseorder",
      "finance.view_purchasereceipt",
      "finance.add_purchasereceipt",
      "finance.change_purchasereceipt",
      "finance.approve_finance",
      "assets.view_asset",
      "assets.change_asset",
      "assets.register_asset",
      "assets.receive_asset_stock",
      "assets.view_assetmovement",
      "assets.view_assetissue",
      "assets.add_assetissue",
      "assets.change_assetissue",
      "assets.approve_asset_issue",
      "assets.issue_asset",
      "assets.add_assetreturn",
    ],
  },
  peopleoperations: {
    id: MAKER_ID,
    email: "peopleoperations@example.test",
    first_name: "People",
    last_name: "Operations",
    companies: [PEOPLE_COMPANY_A, COMPANY_B],
    permissions: [
      "recruitment.view_manpowerrequisition",
      "recruitment.add_manpowerrequisition",
      "recruitment.change_manpowerrequisition",
      "recruitment.approve_requisition",
      "recruitment.view_candidate",
      "recruitment.add_candidate",
      "recruitment.view_candidateapplication",
      "recruitment.change_candidateapplication",
      "recruitment.view_employmentoffer",
      "recruitment.view_onboardingcase",
      "recruitment.hire_candidate",
      "leave.view_own_leave_request",
      "leave.create_own_leave_request",
      "leave.change_own_draft_leave_request",
      "leave.view_team_availability",
      "leave.approve_leave_request",
      "leave.reject_leave_request",
      "training.view_trainingcourse",
      "training.add_trainingcourse",
      "training.change_trainingcourse",
      "training.view_trainingsession",
      "training.add_trainingsession",
      "training.change_trainingsession",
      "training.add_trainingenrollment",
      "training.view_employeequalification",
      "workforce.view_employee",
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
    effective_modules: selectedCompany?.effective_modules ?? [],
    entitlement_revision: selectedCompany?.entitlement_revision ?? 0,
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
  billing_name_snapshot: "E2E Services Client",
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
      description: "Monthly support service",
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

const REQUISITION_ID = "85000000-0000-0000-0000-000000000001";
const REQUISITION_LINE_ID = "85100000-0000-0000-0000-000000000001";
const PURCHASE_ORDER_ID = "86000000-0000-0000-0000-000000000001";
const PURCHASE_ORDER_LINE_ID = "86100000-0000-0000-0000-000000000001";
const PURCHASE_RECEIPT_ID = "87000000-0000-0000-0000-000000000001";
const PURCHASE_RECEIPT_LINE_ID = "87100000-0000-0000-0000-000000000001";
const ASSET_ID = "88000000-0000-0000-0000-000000000001";
const ASSET_ISSUE_ID = "89000000-0000-0000-0000-000000000001";
const ASSET_CATEGORY_ID = "88100000-0000-0000-0000-000000000001";
const ASSET_ITEM_ID = "88200000-0000-0000-0000-000000000001";
const ASSET_STORE_ID = "88300000-0000-0000-0000-000000000001";
let purchaseRequisition = null;
let purchaseOrder = null;
let purchaseReceipt = null;
let workspaceAsset = null;
let assetIssue = null;

const requisitionBody = () => ({
  ...purchaseRequisition,
  company: COMPANY_A.id,
  branch: null,
  branch_name: null,
  department: null,
  department_name: null,
  cost_center: null,
  cost_center_name: null,
  created_by_name: "Operations Administrator",
  approved_by_name:
    purchaseRequisition?.status === "APPROVED"
      ? "Operations Administrator"
      : null,
  estimated_total: "1000.00",
  created_at: "2026-10-20T09:00:00Z",
});
const orderBody = () => ({
  ...purchaseOrder,
  company: COMPANY_A.id,
  requisition_number: purchaseRequisition?.requisition_number ?? "PR-E2E-001",
  vendor: VENDOR_ID,
  vendor_code: vendor.code,
  vendor_name: vendor.name,
  created_by_name: "Operations Administrator",
  approved_by_name:
    purchaseOrder?.status === "APPROVED" ? "Operations Administrator" : null,
  total_amount: "950.00",
  created_at: "2026-10-20T10:00:00Z",
});
const purchaseReceiptBody = () => ({
  ...purchaseReceipt,
  company: COMPANY_A.id,
  purchase_order_number: purchaseOrder?.order_number ?? "PO-E2E-001",
  vendor: VENDOR_ID,
  vendor_name: vendor.name,
  received_by_name: "Operations Administrator",
  created_at: "2026-10-20T11:00:00Z",
});
const assetBody = () => ({
  id: ASSET_ID,
  company: COMPANY_A.id,
  item: ASSET_ITEM_ID,
  item_code: "LAPTOP",
  item_name: "Laptop",
  category_name: "IT equipment",
  asset_number: "AST-E2E-001",
  serial_number: "SER-E2E-001",
  status: assetIssue?.status === "ISSUED" ? "ISSUED" : "AVAILABLE",
  condition: workspaceAsset?.condition ?? "NEW",
  current_custody_type:
    assetIssue?.status === "ISSUED" ? "BRANCH" : "WAREHOUSE",
  current_warehouse: ASSET_STORE_ID,
  current_warehouse_name: "Main Store",
  current_branch: assetIssue?.status === "ISSUED" ? COMPANY_A.id : null,
  current_branch_name: assetIssue?.status === "ISSUED" ? "Head office" : null,
  current_employee: null,
  current_employee_name: null,
  current_site: null,
  acquired_on: "2026-10-20",
  procurement_receipt_reference:
    purchaseReceipt?.receipt_number ?? "GRN-E2E-001",
  purchase_order_reference: purchaseOrder?.order_number ?? "PO-E2E-001",
  warranty_expires_on: workspaceAsset?.warranty_expires_on ?? null,
  expected_retirement_on: workspaceAsset?.expected_retirement_on ?? null,
  notes: workspaceAsset?.notes ?? "",
  created_at: "2026-10-20T12:00:00Z",
});
const issueBody = () => ({
  ...assetIssue,
  company: COMPANY_A.id,
  employee: null,
  employee_name: null,
  branch: COMPANY_A.id,
  branch_name: "Head office",
  lines: [
    {
      id: "89100000-0000-0000-0000-000000000001",
      serialized_asset: ASSET_ID,
      requested_quantity: "1.000",
      issued_quantity: assetIssue?.status === "ISSUED" ? "1.000" : null,
      returned_quantity: assetIssue?.status === "RETURNED" ? "1.000" : "0.000",
    },
  ],
});

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

const EMPLOYEE_ID = "61000000-0000-0000-0000-000000000001";
const INDUSTRY_ID = "62000000-0000-0000-0000-000000000001";
const CLIENT_ID = "63000000-0000-0000-0000-000000000001";
const CONTACT_ID = "64000000-0000-0000-0000-000000000001";
const GENERIC_CONTRACT_ID = "65000000-0000-0000-0000-000000000001";
let workspaceEmployee = null;
let workspaceClient = null;
let workspaceContact = null;
let workspaceContract = null;
let recruitmentApplicationStatus = "SCREENING";
let recruitmentHiredEmployee = null;
let submittedLeaveRequest = null;
let learningSessionStatus = "SCHEDULED";
const RECRUITMENT_APPLICATION_ID = "a3000000-0000-4000-8000-000000000001";
const RECRUITMENT_OFFER_ID = "a5000000-0000-4000-8000-000000000001";
const RECRUITMENT_ONBOARDING_ID = "a6000000-0000-4000-8000-000000000001";
const LEAVE_TYPE_ID = "b1000000-0000-4000-8000-000000000001";
const LEARNING_SESSION_ID = "c2000000-0000-4000-8000-000000000001";
const recruitmentApplicationBody = () => ({
  id: RECRUITMENT_APPLICATION_ID,
  application_number: "APP-E2E-001",
  candidate: "a2000000-0000-4000-8000-000000000001",
  vacancy: "a4000000-0000-4000-8000-000000000001",
  status: recruitmentApplicationStatus,
  applied_at: "2026-10-20T08:00:00Z",
  availability_date: null,
  current_employer: "",
  current_job_title: "",
  total_experience_months: 12,
  hired_employee: recruitmentHiredEmployee,
});
const recruitmentOnboardingBody = () => ({
  id: RECRUITMENT_ONBOARDING_ID,
  application: RECRUITMENT_APPLICATION_ID,
  candidate: "a2000000-0000-4000-8000-000000000001",
  proposed_employee_number: "EMP-E2E-002",
  proposed_joining_date: "2026-11-01",
  status: recruitmentHiredEmployee ? "COMPLETED" : "READY_TO_HIRE",
});
const learningSessionBody = () => ({
  id: LEARNING_SESSION_ID,
  session_number: "LS-E2E-001",
  course: "c1000000-0000-4000-8000-000000000001",
  course_version: "c3000000-0000-4000-8000-000000000001",
  program: null,
  start_datetime: "2026-11-20T09:00:00Z",
  end_datetime: "2026-11-20T11:00:00Z",
  enrollment_deadline: null,
  capacity: 12,
  status: learningSessionStatus,
  notes: "",
});
const employeeBody = () => ({
  id: EMPLOYEE_ID,
  company: COMPANY_A.id,
  company_name: COMPANY_A.legal_name,
  user: null,
  user_email: null,
  employee_number: workspaceEmployee?.employee_number ?? "EMP-E2E-001",
  first_name: workspaceEmployee?.first_name ?? "Amina",
  middle_name: workspaceEmployee?.middle_name ?? "",
  last_name: workspaceEmployee?.last_name ?? "Khan",
  full_name: [
    workspaceEmployee?.first_name ?? "Amina",
    workspaceEmployee?.middle_name ?? "",
    workspaceEmployee?.last_name ?? "Khan",
  ]
    .filter(Boolean)
    .join(" "),
  preferred_name: workspaceEmployee?.preferred_name ?? "Amina",
  father_or_spouse_name: "",
  gender: "UNSPECIFIED",
  date_of_birth: null,
  marital_status: "UNSPECIFIED",
  nationality: "PK",
  national_identity_number: null,
  masked_national_identity_number: "",
  national_identity_expiry: null,
  personal_email: workspaceEmployee?.personal_email ?? "amina@example.test",
  mobile_number: workspaceEmployee?.mobile_number ?? "03000000000",
  alternate_mobile_number: "",
  employee_type: "OFFICE_STAFF",
  employment_type: "PERMANENT",
  employment_status: "DRAFT",
  joining_date: "2026-10-19",
  confirmation_date: null,
  probation_end_date: null,
  exit_date: null,
  branch: null,
  branch_name: null,
  department: null,
  department_name: null,
  designation: null,
  designation_name: null,
  notes: null,
  is_active: true,
  created_at: "2026-10-19T00:00:00Z",
  updated_at: "2026-10-19T00:00:00Z",
});
const clientBody = () => ({
  id: CLIENT_ID,
  company: COMPANY_A.id,
  client_code: "CLI-E2E-001",
  legal_name: "Acme Advisory Limited",
  trade_name: "Acme Advisory",
  industry: INDUSTRY_ID,
  industry_name: "Professional services",
  registration_number: "REG-E2E",
  tax_number: "",
  website: "",
  main_email: "hello@acme.test",
  main_phone: "",
  billing_address: "",
  head_office_address: "",
  city: "Karachi",
  province_or_state: "Sindh",
  country_code: "PK",
  status: workspaceClient?.status ?? "PROSPECT",
  notes: "",
  account_manager: null,
  account_manager_name: null,
  created_at: "2026-10-19T00:00:00Z",
  updated_at: "2026-10-19T00:00:00Z",
});
const contractBody = () => ({
  id: GENERIC_CONTRACT_ID,
  company: COMPANY_A.id,
  client: CLIENT_ID,
  client_name: "Acme Advisory Limited",
  contract_number: "CTR-E2E-001",
  contract_type: "PROJECT",
  title: "Advisory services agreement",
  description: "General business advisory services",
  signed_date: null,
  start_date: "2026-10-19",
  end_date: null,
  notice_period_days: null,
  auto_renew: false,
  currency: "PKR",
  status: "DRAFT",
  client_reference: "",
  purchase_order_reference: "",
  internal_reference: "",
  primary_client_contact: null,
  primary_client_contact_name: null,
  account_manager: null,
  account_manager_name: null,
  approved_at: null,
  activated_at: null,
  created_at: "2026-10-19T00:00:00Z",
  updated_at: "2026-10-19T00:00:00Z",
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
  const selectedCompanyId = contextBody(request, actor).selected_company?.id;
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
  if (path === "/api/v1/auth/me/platform-capabilities/") {
    return json(response, 200, {
      capabilities: actor.platform_capabilities ?? [],
      can_access_platform_admin: Boolean(actor.platform_capabilities?.length),
    });
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

  const selectedPeopleCompany = selectedCompanyId === COMPANY_A.id;
  const peoplePage = (results) => ({
    count: results.length,
    next: null,
    previous: null,
    results,
  });
  if (
    path ===
      `/api/v1/recruitment/applications/${RECRUITMENT_APPLICATION_ID}/` &&
    request.method === "GET"
  )
    return selectedPeopleCompany
      ? json(response, 200, recruitmentApplicationBody())
      : json(response, 404, { detail: "Not found." });
  if (
    path ===
      `/api/v1/recruitment/applications/${RECRUITMENT_APPLICATION_ID}/transition/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    recruitmentApplicationStatus = body.status;
    return json(response, 200, recruitmentApplicationBody());
  }
  if (path?.startsWith("/api/v1/recruitment/offers/?"))
    return json(
      response,
      200,
      peoplePage(
        selectedPeopleCompany
          ? [
              {
                id: RECRUITMENT_OFFER_ID,
                application: RECRUITMENT_APPLICATION_ID,
                offer_number: "OFF-E2E-001",
                proposed_joining_date: "2026-11-01",
                offer_expiry_date: "2026-11-15",
                status: "ACCEPTED",
                terms_summary: "Approved employment terms",
              },
            ]
          : [],
      ),
    );
  if (path?.startsWith("/api/v1/recruitment/onboarding/?"))
    return json(
      response,
      200,
      peoplePage(selectedPeopleCompany ? [recruitmentOnboardingBody()] : []),
    );
  if (
    path ===
      `/api/v1/recruitment/onboarding/${RECRUITMENT_ONBOARDING_ID}/hire/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    workspaceEmployee = {
      employee_number: body.employee_number,
      first_name: "Sara",
      middle_name: "",
      last_name: "Ahmed",
      preferred_name: "Sara",
      personal_email: "sara@example.test",
      mobile_number: "03001112222",
    };
    recruitmentApplicationStatus = "HIRED";
    recruitmentHiredEmployee = EMPLOYEE_ID;
    return json(response, 200, { employee_id: EMPLOYEE_ID });
  }
  if (path?.startsWith("/api/v1/recruitment/manpower-requisitions/?"))
    return json(
      response,
      200,
      peoplePage(
        selectedPeopleCompany
          ? [
              {
                id: "a1000000-0000-4000-8000-000000000001",
                company: COMPANY_A.id,
                branch: null,
                department: null,
                designation: "a1000000-0000-4000-8000-000000000010",
                employee_type: "OFFICE_STAFF",
                employment_type: "PERMANENT",
                requested_headcount: 1,
                approved_headcount: null,
                required_by_date: "2026-11-15",
                reason: "Customer success specialist",
                status: "DRAFT",
                created_at: "2026-10-21T08:00:00Z",
              },
            ]
          : [],
      ),
    );
  if (path?.startsWith("/api/v1/recruitment/candidates/?"))
    return json(
      response,
      200,
      peoplePage(
        selectedPeopleCompany
          ? [
              {
                id: "a2000000-0000-4000-8000-000000000001",
                candidate_number: "CAND-E2E-001",
                first_name: "Sara",
                middle_name: "",
                last_name: "Ahmed",
                mobile_number: "03001112222",
                email: "sara@example.test",
                city: "Karachi",
                source_type: "WEBSITE",
                status: "ACTIVE",
                notes: "",
              },
            ]
          : [],
      ),
    );
  if (path?.startsWith("/api/v1/recruitment/applications/?"))
    return json(
      response,
      200,
      peoplePage(selectedPeopleCompany ? [recruitmentApplicationBody()] : []),
    );
  if (path?.startsWith("/api/v1/recruitment/vacancies/?"))
    return json(
      response,
      200,
      peoplePage(
        selectedPeopleCompany
          ? [
              {
                id: "a4000000-0000-4000-8000-000000000001",
                vacancy_code: "VAC-E2E-001",
                title: "Customer success specialist",
                status: "OPEN",
                number_of_positions: 1,
                positions_filled: 0,
                opening_date: "2026-10-20",
              },
            ]
          : [],
      ),
    );
  if (path === "/api/v1/leave/me/requests/" && request.method === "POST") {
    const body = await readJsonBody(request);
    submittedLeaveRequest = {
      id: "b2000000-0000-4000-8000-000000000009",
      request_number: "LR-E2E-NEW",
      employee: EMPLOYEE_ID,
      employee_name: "Sara Ahmed",
      leave_type: body.leave_type,
      leave_type_name: "Annual Leave",
      starts_at: body.starts_at,
      ends_at: body.ends_at,
      requested_units: "1.00",
      approved_units: null,
      reason: body.reason,
      status: "DRAFT",
      emergency_request: Boolean(body.emergency_request),
    };
    return json(response, 201, submittedLeaveRequest);
  }
  if (
    path ===
      "/api/v1/leave/me/requests/b2000000-0000-4000-8000-000000000009/submit/" &&
    request.method === "POST"
  ) {
    submittedLeaveRequest.status = "SUBMITTED";
    return json(response, 200, submittedLeaveRequest);
  }
  if (
    path ===
      "/api/v1/leave/manager/requests/b2000000-0000-4000-8000-000000000009/approve/" &&
    request.method === "POST"
  ) {
    submittedLeaveRequest.status = "APPROVED";
    submittedLeaveRequest.approved_units =
      submittedLeaveRequest.requested_units;
    return json(response, 200, submittedLeaveRequest);
  }
  if (path?.startsWith("/api/v1/leave/types/") && request.method === "GET")
    return json(
      response,
      200,
      peoplePage([
        {
          id: LEAVE_TYPE_ID,
          code: "ANNUAL",
          name: "Annual Leave",
          unit: "DAYS",
          requires_balance: true,
          requires_attachment: false,
          allow_partial_day: false,
        },
      ]),
    );
  if (
    path?.startsWith("/api/v1/leave/me/requests/") &&
    request.method === "GET"
  )
    return json(
      response,
      200,
      peoplePage([
        ...(submittedLeaveRequest ? [submittedLeaveRequest] : []),
        {
          id: "b2000000-0000-4000-8000-000000000001",
          request_number: "LR-E2E-001",
          employee: EMPLOYEE_ID,
          leave_type: LEAVE_TYPE_ID,
          starts_at: "2026-11-10T09:00:00Z",
          ends_at: "2026-11-11T09:00:00Z",
          requested_units: "1.00",
          approved_units: null,
          reason: "Personal appointment",
          status: "SUBMITTED",
          emergency_request: false,
        },
      ]),
    );
  if (
    path?.startsWith("/api/v1/leave/me/balances/") &&
    request.method === "GET"
  )
    return json(response, 200, [
      {
        leave_type: LEAVE_TYPE_ID,
        leave_type_name: "Annual Leave",
        unit: "DAYS",
        entitled: "20.00",
        reserved: "1.00",
        taken: "4.00",
        available: "15.00",
      },
    ]);
  if (
    path?.startsWith("/api/v1/leave/manager/requests/") &&
    request.method === "GET"
  )
    return json(
      response,
      200,
      peoplePage([
        ...(submittedLeaveRequest?.status === "SUBMITTED"
          ? [submittedLeaveRequest]
          : []),
        {
          id: "b3000000-0000-4000-8000-000000000001",
          request_number: "LR-E2E-002",
          employee: EMPLOYEE_ID,
          employee_name: "Amina Khan",
          leave_type: LEAVE_TYPE_ID,
          leave_type_name: "Annual Leave",
          starts_at: "2026-11-14T09:00:00Z",
          ends_at: "2026-11-15T09:00:00Z",
          requested_units: "1.00",
          approved_units: null,
          status: "SUBMITTED",
          emergency_request: false,
        },
      ]),
    );
  if (
    path?.startsWith("/api/v1/leave/team/calendar/") &&
    request.method === "GET"
  )
    return json(response, 200, peoplePage([]));
  if (path?.startsWith("/api/v1/leave/holidays/") && request.method === "GET")
    return json(
      response,
      200,
      peoplePage([
        {
          id: "b4000000-0000-4000-8000-000000000001",
          date: "2026-12-25",
          name: "Company holiday",
          holiday_type: "PUBLIC",
          is_full_day: true,
          calendar_name: "Company calendar",
        },
      ]),
    );
  if (path?.startsWith("/api/v1/training/courses/?"))
    return json(
      response,
      200,
      peoplePage(
        selectedPeopleCompany
          ? [
              {
                id: "c1000000-0000-4000-8000-000000000001",
                company: COMPANY_A.id,
                category: null,
                code: "COMM-101",
                title: "Business communication",
                description: "Communication fundamentals",
                objective: "Improve business communication",
                delivery_method: "CLASSROOM",
                duration_hours: "2.00",
                status: "ACTIVE",
                requires_assessment: false,
                produces_certificate: true,
              },
            ]
          : [],
      ),
    );
  if (
    path === `/api/v1/training/sessions/${LEARNING_SESSION_ID}/` &&
    request.method === "GET"
  )
    return selectedPeopleCompany
      ? json(response, 200, learningSessionBody())
      : json(response, 404, { detail: "Not found." });
  for (const [action, target] of [
    ["open-enrollment", "OPEN_FOR_ENROLLMENT"],
    ["start", "IN_PROGRESS"],
    ["complete", "COMPLETED"],
  ]) {
    if (
      path === `/api/v1/training/sessions/${LEARNING_SESSION_ID}/${action}/` &&
      request.method === "POST"
    ) {
      learningSessionStatus = target;
      return json(response, 200, learningSessionBody());
    }
  }
  if (
    path === `/api/v1/training/sessions/${LEARNING_SESSION_ID}/enroll/` &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const enrollment = {
      id: "c6000000-0000-4000-8000-000000000001",
      session: LEARNING_SESSION_ID,
      employee: body.employee,
      status: "ENROLLED",
    };
    return json(response, 201, enrollment);
  }
  if (path?.startsWith("/api/v1/training/sessions/?"))
    return json(
      response,
      200,
      peoplePage(selectedPeopleCompany ? [learningSessionBody()] : []),
    );
  if (path?.startsWith("/api/v1/training/qualification-types/?"))
    return json(
      response,
      200,
      peoplePage([
        {
          id: "c5000000-0000-4000-8000-000000000001",
          code: "BUSINESS-COMMUNICATION",
          name: "Business communication certificate",
          is_active: true,
        },
      ]),
    );
  if (path?.startsWith("/api/v1/training/employee-qualifications/?"))
    return json(
      response,
      200,
      peoplePage(
        selectedPeopleCompany
          ? [
              {
                id: "c4000000-0000-4000-8000-000000000001",
                employee: EMPLOYEE_ID,
                qualification_type: "c5000000-0000-4000-8000-000000000001",
                source: "TRAINING",
                obtained_on: "2026-10-01",
                expires_on: null,
                status: "VALID",
                notes: "",
              },
            ]
          : [],
      ),
    );
  if (path === "/api/v1/platform/modules/") {
    return json(response, 200, PLATFORM_MODULES);
  }
  if (path === "/api/v1/platform/tenants/") {
    return json(response, 200, [
      {
        id: COMPANY_A.id,
        code: COMPANY_A.code,
        legal_name: COMPANY_A.legal_name,
        trade_name: COMPANY_A.display_name,
        is_active: true,
        country_code: "PK",
        timezone: "Asia/Karachi",
        default_currency: "PKR",
        operational_status: "READY",
        blocker_count: 0,
        blocker_codes: [],
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
  }
  if (path === "/api/v1/platform/plans/") {
    return json(response, 200, [PLATFORM_PLAN]);
  }
  if (path === "/api/v1/platform/subscriptions/") {
    return json(response, 200, [platformSubscription()]);
  }
  if (
    path ===
      `/api/v1/platform/subscriptions/${PLATFORM_SUBSCRIPTION_ID}/entitlements/` &&
    request.method === "GET"
  ) {
    return json(response, 200, platformEntitlements());
  }
  if (
    path ===
      `/api/v1/platform/subscriptions/${PLATFORM_SUBSCRIPTION_ID}/overrides/` &&
    request.method === "PUT"
  ) {
    const body = await readJsonBody(request);
    platformOverrides = [
      ...(body.enabled_module_ids ?? []).map((module_id) => ({
        module_id,
        state: "ENABLED",
      })),
      ...(body.disabled_module_ids ?? []).map((module_id) => ({
        module_id,
        state: "DISABLED",
      })),
    ];
    const enabled = new Set(SNAPSHOT_MODULES);
    for (const override of platformOverrides) {
      if (override.state === "ENABLED") enabled.add(override.module_id);
      else enabled.delete(override.module_id);
    }
    COMPANY_A.effective_modules = SNAPSHOT_MODULES.filter((moduleId) =>
      enabled.has(moduleId),
    );
    platformEntitlementRevision += 1;
    COMPANY_A.entitlement_revision = platformEntitlementRevision;
    return json(response, 200, platformEntitlements());
  }
  if (path === "/api/v1/finance/ap-reference/payable-accounts/")
    return json(response, 200, [
      { id: PAYABLE_ACCOUNT_ID, code: "2000", name: "Trade Payables" },
    ]);
  if (
    path === "/api/v1/finance/purchase-requisitions/" &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const line = body.lines[0];
    purchaseRequisition = {
      id: REQUISITION_ID,
      requisition_number: body.requisition_number,
      required_date: body.required_date,
      purpose: body.purpose,
      status: "DRAFT",
      lines: [
        {
          id: REQUISITION_LINE_ID,
          ...line,
          estimated_total: "1000.00",
          expense_account_code: "6100",
          expense_account_name: "Equipment expense",
        },
      ],
    };
    return json(response, 201, requisitionBody());
  }
  if (
    path === `/api/v1/finance/purchase-requisitions/${REQUISITION_ID}/` &&
    request.method === "GET"
  )
    return purchaseRequisition && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, requisitionBody())
      : json(response, 404, { detail: "Not found." });
  for (const [action, target] of [
    ["submit", "SUBMITTED"],
    ["approve", "APPROVED"],
    ["reject", "REJECTED"],
  ]) {
    if (
      path ===
        `/api/v1/finance/purchase-requisitions/${REQUISITION_ID}/${action}/` &&
      request.method === "POST"
    ) {
      purchaseRequisition.status = target;
      return json(response, 200, requisitionBody());
    }
  }
  if (path?.startsWith("/api/v1/finance/purchase-requisitions/?"))
    return json(response, 200, {
      count: purchaseRequisition && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        purchaseRequisition && selectedCompanyId === COMPANY_A.id
          ? [requisitionBody()]
          : [],
    });
  if (
    path === "/api/v1/finance/purchase-orders/" &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const line = body.lines[0];
    purchaseOrder = {
      id: PURCHASE_ORDER_ID,
      requisition: REQUISITION_ID,
      order_number: body.order_number,
      order_date: body.order_date,
      status: "DRAFT",
      lines: [
        {
          id: PURCHASE_ORDER_LINE_ID,
          ...line,
          requisition_line_description: line.description,
          line_total: "950.00",
          received_quantity: "0.0000",
        },
      ],
    };
    return json(response, 201, orderBody());
  }
  if (path === `/api/v1/finance/purchase-orders/${PURCHASE_ORDER_ID}/`)
    return purchaseOrder && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, orderBody())
      : json(response, 404, { detail: "Not found." });
  for (const [action, target] of [
    ["submit", "SUBMITTED"],
    ["approve", "APPROVED"],
    ["reject", "REJECTED"],
  ]) {
    if (
      path ===
        `/api/v1/finance/purchase-orders/${PURCHASE_ORDER_ID}/${action}/` &&
      request.method === "POST"
    ) {
      purchaseOrder.status = target;
      return json(response, 200, orderBody());
    }
  }
  if (path?.startsWith("/api/v1/finance/purchase-orders/?"))
    return json(response, 200, {
      count: purchaseOrder && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        purchaseOrder && selectedCompanyId === COMPANY_A.id
          ? [orderBody()]
          : [],
    });
  if (
    path === "/api/v1/finance/purchase-receipts/" &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    const line = body.lines[0];
    purchaseReceipt = {
      id: PURCHASE_RECEIPT_ID,
      purchase_order: PURCHASE_ORDER_ID,
      receipt_number: body.receipt_number,
      receipt_date: body.receipt_date,
      receipt_type: body.receipt_type,
      status: "DRAFT",
      lines: [
        {
          id: PURCHASE_RECEIPT_LINE_ID,
          ...line,
          description: purchaseOrder.lines[0].description,
          ordered_quantity: purchaseOrder.lines[0].quantity,
        },
      ],
    };
    return json(response, 201, purchaseReceiptBody());
  }
  if (path === `/api/v1/finance/purchase-receipts/${PURCHASE_RECEIPT_ID}/`)
    return purchaseReceipt && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, purchaseReceiptBody())
      : json(response, 404, { detail: "Not found." });
  if (
    path ===
      `/api/v1/finance/purchase-receipts/${PURCHASE_RECEIPT_ID}/confirm/` &&
    request.method === "POST"
  ) {
    purchaseReceipt.status = "APPROVED";
    purchaseOrder.lines[0].received_quantity =
      purchaseReceipt.lines[0].accepted_quantity;
    return json(response, 200, purchaseReceiptBody());
  }
  if (path?.startsWith("/api/v1/finance/purchase-receipts/?"))
    return json(response, 200, {
      count: purchaseReceipt && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        purchaseReceipt && selectedCompanyId === COMPANY_A.id
          ? [purchaseReceiptBody()]
          : [],
    });
  if (path?.startsWith("/api/v1/assets/categories/?"))
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: ASSET_CATEGORY_ID,
          company: COMPANY_A.id,
          code: "IT",
          name: "IT equipment",
          tracking_method: "SERIALIZED",
          is_controlled: false,
          is_active: true,
        },
      ],
    });
  if (path?.startsWith("/api/v1/assets/items/?"))
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: ASSET_ITEM_ID,
          company: COMPANY_A.id,
          category: ASSET_CATEGORY_ID,
          item_code: "LAPTOP",
          name: "Laptop",
          manufacturer: "Generic",
          model: "Business",
          unit_of_measure: "EACH",
          is_active: true,
        },
      ],
    });
  if (path?.startsWith("/api/v1/assets/stores/?"))
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: ASSET_STORE_ID,
          company: COMPANY_A.id,
          branch: null,
          code: "MAIN",
          name: "Main Store",
          is_active: true,
        },
      ],
    });
  if (
    path === "/api/v1/assets/procurement-registrations/" &&
    request.method === "POST"
  ) {
    workspaceAsset = assetBody();
    return json(response, 201, {
      id: "88400000-0000-0000-0000-000000000001",
      registration_number: "REG-E2E-001",
      receipt_line: PURCHASE_RECEIPT_LINE_ID,
      asset_item: ASSET_ITEM_ID,
      destination_store: ASSET_STORE_ID,
      tracking_method: "SERIALIZED",
      registered: "1.000",
      remaining: "0.000",
      results: [{ asset: ASSET_ID, quantity: "1.000" }],
    });
  }
  if (path === `/api/v1/assets/assets/${ASSET_ID}/` && request.method === "GET")
    return workspaceAsset && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, assetBody())
      : json(response, 404, { detail: "Not found." });
  if (
    path === `/api/v1/assets/assets/${ASSET_ID}/` &&
    request.method === "PATCH"
  ) {
    workspaceAsset = { ...workspaceAsset, ...(await readJsonBody(request)) };
    return json(response, 200, assetBody());
  }
  if (path?.startsWith("/api/v1/assets/assets/?"))
    return json(response, 200, {
      count: workspaceAsset && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        workspaceAsset && selectedCompanyId === COMPANY_A.id
          ? [assetBody()]
          : [],
    });
  if (path?.startsWith("/api/v1/assets/movements/?"))
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  if (
    path === "/api/v1/assets/issues/from-asset/" &&
    request.method === "POST"
  ) {
    const body = await readJsonBody(request);
    assetIssue = { id: ASSET_ISSUE_ID, ...body, status: "DRAFT" };
    return json(response, 201, issueBody());
  }
  for (const [action, target] of [
    ["submit", "PENDING_APPROVAL"],
    ["approve", "APPROVED"],
    ["issue", "ISSUED"],
    ["return", "RETURNED"],
  ]) {
    if (
      path === `/api/v1/assets/issues/${ASSET_ISSUE_ID}/${action}/` &&
      request.method === "POST"
    ) {
      assetIssue.status = target;
      return json(response, 200, issueBody());
    }
  }
  if (path?.startsWith("/api/v1/assets/issues/?"))
    return json(response, 200, {
      count: assetIssue ? 1 : 0,
      next: null,
      previous: null,
      results: assetIssue ? [issueBody()] : [],
    });
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

  if (path?.startsWith("/api/v1/organization/branches/"))
    return json(response, 200, {
      count: 1,
      next: null,
      previous: null,
      results: [{ id: COMPANY_A.id, code: "HQ", name: "Head office" }],
    });
  if (
    [
      "/api/v1/organization/departments/",
      "/api/v1/organization/designations/",
    ].some((prefix) => path?.startsWith(prefix))
  )
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  if (
    path?.startsWith("/api/v1/workforce/employees/?") &&
    request.method === "GET"
  )
    return json(response, 200, {
      count: workspaceEmployee && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        workspaceEmployee && selectedCompanyId === COMPANY_A.id
          ? [employeeBody()]
          : [],
    });
  if (path === "/api/v1/workforce/employees/" && request.method === "POST") {
    workspaceEmployee = await readJsonBody(request);
    return json(response, 201, employeeBody());
  }
  if (
    path === `/api/v1/workforce/employees/${EMPLOYEE_ID}/` &&
    request.method === "GET"
  )
    return workspaceEmployee && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, employeeBody())
      : json(response, 404, { detail: "Not found." });
  if (
    path === `/api/v1/workforce/employees/${EMPLOYEE_ID}/` &&
    request.method === "PATCH"
  ) {
    workspaceEmployee = {
      ...workspaceEmployee,
      ...(await readJsonBody(request)),
    };
    return json(response, 200, employeeBody());
  }
  if (
    path?.startsWith(`/api/v1/workforce/employees/${EMPLOYEE_ID}/`) &&
    request.method === "GET"
  )
    return json(response, 200, []);
  if (path === `/api/v1/documents/employees/${EMPLOYEE_ID}/documents/`)
    return json(response, 200, []);

  if (
    path?.startsWith("/api/v1/contracts/industries/") &&
    request.method === "GET"
  )
    return json(response, 200, {
      count: selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        selectedCompanyId === COMPANY_A.id
          ? [
              {
                id: INDUSTRY_ID,
                company: COMPANY_A.id,
                code: "PROF",
                name: "Professional services",
                is_active: true,
              },
            ]
          : [],
    });
  if (
    path?.startsWith("/api/v1/contracts/clients/?") &&
    request.method === "GET"
  )
    return json(response, 200, {
      count: workspaceClient && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        workspaceClient && selectedCompanyId === COMPANY_A.id
          ? [clientBody()]
          : [],
    });
  if (path === "/api/v1/contracts/clients/" && request.method === "POST") {
    workspaceClient = await readJsonBody(request);
    return json(response, 201, clientBody());
  }
  if (
    path === `/api/v1/contracts/clients/${CLIENT_ID}/activate/` &&
    request.method === "POST"
  ) {
    workspaceClient = { ...workspaceClient, status: "ACTIVE" };
    return json(response, 200, clientBody());
  }
  if (path === `/api/v1/contracts/clients/${CLIENT_ID}/`)
    return workspaceClient && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, clientBody())
      : json(response, 404, { detail: "Not found." });
  if (
    path?.startsWith("/api/v1/contracts/client-contacts/?") &&
    request.method === "GET"
  )
    return json(response, 200, {
      count: workspaceContact ? 1 : 0,
      next: null,
      previous: null,
      results: workspaceContact ? [workspaceContact] : [],
    });
  if (
    path === "/api/v1/contracts/client-contacts/" &&
    request.method === "POST"
  ) {
    workspaceContact = {
      id: CONTACT_ID,
      ...(await readJsonBody(request)),
      designation: "",
      department: "",
      office_phone: "",
      notes: "",
      is_active: true,
    };
    return json(response, 201, workspaceContact);
  }
  if (
    path?.startsWith("/api/v1/contracts/contracts/?") &&
    request.method === "GET"
  )
    return json(response, 200, {
      count: workspaceContract && selectedCompanyId === COMPANY_A.id ? 1 : 0,
      next: null,
      previous: null,
      results:
        workspaceContract && selectedCompanyId === COMPANY_A.id
          ? [contractBody()]
          : [],
    });
  if (path === "/api/v1/contracts/contracts/" && request.method === "POST") {
    workspaceContract = await readJsonBody(request);
    return json(response, 201, contractBody());
  }
  if (path === `/api/v1/contracts/contracts/${GENERIC_CONTRACT_ID}/`)
    return workspaceContract && selectedCompanyId === COMPANY_A.id
      ? json(response, 200, contractBody())
      : json(response, 404, { detail: "Not found." });
  if (
    [
      "/api/v1/contracts/contract-services/?",
      "/api/v1/contracts/commercial-terms/?",
      "/api/v1/contracts/contract-amendments/?",
      "/api/v1/contracts/slas/?",
    ].some((prefix) => path?.startsWith(prefix))
  )
    return json(response, 200, {
      count: 0,
      next: null,
      previous: null,
      results: [],
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
