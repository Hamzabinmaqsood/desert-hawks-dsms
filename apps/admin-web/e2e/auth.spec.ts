import { randomUUID } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

const DRAFT_INVOICE_ID = "90000000-0000-0000-0000-000000000001";
const VENDOR_BILL_ACCOUNT_ID = "50000000-0000-0000-0000-000000000300";
const COMPANY_A_ID = "00000000-0000-0000-0000-000000000002";
const COMPANY_B_ID = "00000000-0000-0000-0000-000000000003";
const INDUSTRY_ID = "62000000-0000-0000-0000-000000000001";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15_000 });
}

test("employee signs in, uses the protected shell, and signs out", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByRole("img", { name: "Business Operations Platform mark" }),
  ).toBeVisible();
  await expect(page.locator(".brand-login")).toContainText(
    "Business Operations Platform",
  );
  await expect(page.locator("body")).not.toContainText(
    "Security Management Platform",
  );

  await page.getByLabel("Work email").fill("employee@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("img", { name: "Business Operations Platform mark" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Alpha Works workspace" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Finance" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Administration" }),
  ).toBeVisible();
  await expect(page.getByText("employee@example.test").first()).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});

test("multi-company employee explicitly selects and switches active Company", async ({
  page,
}) => {
  await signIn(page, "multicompany@example.test");
  await expect(
    page.getByRole("heading", { name: "Select a Company" }),
  ).toBeVisible();
  const switcher = page.getByLabel("Active Company");
  await expect(switcher).toHaveValue("");

  await switcher.selectOption({ label: "NTA — Northstar Alpha" });
  await expect(switcher).toHaveValue(COMPANY_A_ID);
  await expect(
    page.getByRole("heading", { name: "Alpha Works workspace" }),
  ).toBeVisible();
  await expect(page.locator(".sidebar .brand")).toContainText(
    "Alpha operations",
  );
  await expect(page.locator(".sidebar .brand")).not.toContainText(
    "Northstar Alpha",
  );
  await expect(page).toHaveTitle("Alpha Works — Business Operations Platform");

  await expect(
    page.getByRole("link", { name: "Invoices", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Vendors", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Invoices" })).toBeVisible();

  await switcher.selectOption({ label: "NTB — Northstar Bravo" });
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("link", { name: "Invoices", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Vendors", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("INV-E2E-001")).toHaveCount(0);
  await page.goto("/invoices");
  await expect(
    page.getByRole("heading", { name: "Module unavailable" }),
  ).toBeVisible();
  await expect(
    page.getByText("This module is not enabled for this Company."),
  ).toBeVisible();

  await switcher.selectOption({ label: "NTA — Northstar Alpha" });
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("link", { name: "Invoices", exact: true }),
  ).toBeVisible();

  await page
    .getByRole("link", { name: "Company settings", exact: true })
    .click();
  await expect(page).toHaveURL(/\/settings\/company$/);
  await expect(page.getByLabel("Default currency")).toHaveValue("USD");
  await expect(page.getByLabel("Invoice prefix")).toHaveValue("AINV");

  await switcher.selectOption({ label: "NTB — Northstar Bravo" });
  await expect(switcher).toHaveValue(COMPANY_B_ID);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByText("multicompany@example.test").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Bravo Works workspace" }),
  ).toBeVisible();
  await expect(page.locator(".sidebar .brand")).toContainText(
    "Bravo operations",
  );
  await expect(page.locator(".sidebar .brand")).not.toContainText(
    "Alpha Works",
  );
  await expect(page.locator(".sidebar .brand")).not.toContainText(
    "Northstar Alpha",
  );
  await expect(page).toHaveTitle("Bravo Works — Business Operations Platform");
  await page
    .getByRole("link", { name: "Company settings", exact: true })
    .click();
  await expect(page.getByLabel("Default currency")).toHaveValue("AED");
  await expect(page.getByLabel("Invoice prefix")).toHaveValue("BINV");
  await expect(page.getByLabel("Timezone")).toHaveValue("Asia/Dubai");
});

test("platform operator changes a module and tenant UX follows authoritative context", async ({
  page,
}) => {
  await signIn(page, "platformoperator@example.test");
  await page.goto("/platform/companies");
  await expect(page).toHaveTitle(
    "Platform administration — Business Operations Platform",
  );
  await expect(page.getByRole("heading", { name: "Platform" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Home" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Companies" })).toBeVisible();
  await page.getByRole("link", { name: "Open" }).click();
  await page.getByRole("link", { name: "Manage business modules" }).click();
  await expect(
    page.getByRole("heading", { name: "Northstar Alpha" }),
  ).toBeVisible();
  await page
    .getByLabel("Billing & Receivables source")
    .selectOption("DISABLED");
  await page.getByLabel("Change reason").fill("Customer module change");
  await page.getByRole("button", { name: "Save overrides" }).click();
  await expect(page.getByText("Subscription overrides saved.")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "employee@example.test");
  await expect(
    page.getByRole("link", { name: "Invoices", exact: true }),
  ).toHaveCount(0);
  await page.goto("/invoices");
  await expect(
    page.getByRole("heading", { name: "Module unavailable" }),
  ).toBeVisible();
  await page.goto("/platform/companies");
  await expect(
    page.getByRole("heading", { name: "Platform administration unavailable" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "platformoperator@example.test");
  await page.goto(
    `/platform/subscriptions/${"92000000-0000-0000-0000-000000000001"}`,
  );
  await page
    .getByLabel("Billing & Receivables source")
    .selectOption("INHERITED");
  await page.getByLabel("Change reason").fill("Restore contracted module");
  await page.getByRole("button", { name: "Save overrides" }).click();
  await expect(page.getByText("Subscription overrides saved.")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "employee@example.test");
  await expect(
    page.getByRole("link", { name: "Invoices", exact: true }),
  ).toBeVisible();
});

test("mobile shell exposes grouped navigation without viewport overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "employee@example.test");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await menu.click();
  await expect(
    page.getByRole("button", { name: "Close menu" }),
  ).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByLabel("Active Company")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Finance" })).toBeVisible();
  await page
    .getByLabel("Primary navigation")
    .getByRole("link", { name: "Invoices", exact: true })
    .click();
  await expect(page).toHaveURL(/\/invoices$/);
  await expect(page.getByRole("button", { name: "Menu" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("employee reads an Invoice list and detail", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("employee@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await expect(page).toHaveURL(/\/invoices$/);
  await expect(page.getByRole("heading", { name: "Invoices" })).toBeVisible();
  await page.getByRole("link", { name: "INV-E2E-001" }).click();
  await expect(page).toHaveURL(/\/invoices\/10000000-/);
  await expect(
    page.getByRole("heading", { name: "INV-E2E-001" }),
  ).toBeVisible();
  await expect(page.getByText("Monthly support service")).toBeVisible();
  await expect(page.getByText(/PKR.*11,600.00/).first()).toBeVisible();
  await expect(page.getByText("Issued").first()).toBeVisible();
  await page
    .getByLabel("Primary navigation")
    .getByRole("link", { name: "Invoices", exact: true })
    .click();
  await expect(page).toHaveURL(/\/invoices$/);
});

test("a maker creates a draft invoice, adds and edits a line, and sees server totals", async ({
  page,
}) => {
  const siteRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/reference/sites"))
      siteRequests.push(request.url());
  });
  await page.goto("/login");
  await page.getByLabel("Work email").fill("maker@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await page.getByRole("link", { name: "New Invoice" }).click();
  await expect(page).toHaveURL(/\/invoices\/new$/);

  await page
    .getByRole("combobox", { name: "Billing profile" })
    .selectOption({ label: "E2E Draft Client (PKR)" });
  await page.getByLabel("Invoice date").fill("2026-09-01");
  await page
    .getByRole("combobox", { name: "Invoice type" })
    .selectOption("STANDARD");
  await page.getByRole("button", { name: "Create draft" }).click();

  await expect(page).toHaveURL(/\/invoices\/90000000-.*\/edit$/);
  await expect(
    page.getByRole("heading", { name: "Edit INV-E2E-DRAFT-001" }),
  ).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Site" })).toHaveCount(0);
  expect(siteRequests).toEqual([]);

  await page.getByLabel("Description").fill("Consulting service");
  await page.getByLabel("Quantity").fill("4.0000");
  await page.getByLabel("Unit price").fill("2500.00");
  await page
    .getByRole("combobox", { name: "Revenue account" })
    .selectOption({ label: "4000 — Service Revenue" });
  await page.getByRole("button", { name: "Add line" }).click();

  await expect(page.getByText("Consulting service")).toBeVisible();
  await expect(page.getByText(/PKR.*10,000.00/).first()).toBeVisible();

  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Quantity").fill("6.0000");
  await page.getByRole("button", { name: "Save line" }).click();
  await expect(page.getByText(/PKR.*15,000.00/).first()).toBeVisible();

  await page
    .getByRole("link", { name: "Back to invoice", exact: true })
    .click();
  await expect(page).toHaveURL(/\/invoices\/90000000-/);
  await expect(
    page.getByRole("heading", { name: "INV-E2E-DRAFT-001" }),
  ).toBeVisible();
  await expect(page.getByText("Consulting service")).toBeVisible();
});

test("least-privilege actors complete the Invoice and Receipt lifecycle", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await signIn(page, "maker@example.test");

  // Author a fresh draft with one line so the invoice is submittable.
  await page.goto("/invoices/new");
  await page
    .getByRole("combobox", { name: "Billing profile" })
    .selectOption({ label: "E2E Draft Client (PKR)" });
  await page.getByLabel("Invoice date").fill("2026-09-01");
  await page
    .getByRole("combobox", { name: "Invoice type" })
    .selectOption("STANDARD");
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page).toHaveURL(/\/invoices\/90000000-.*\/edit$/);

  await page.getByLabel("Description").fill("Consulting service");
  await page.getByLabel("Quantity").fill("4.0000");
  await page.getByLabel("Unit price").fill("2500.00");
  await page
    .getByRole("combobox", { name: "Revenue account" })
    .selectOption({ label: "4000 — Service Revenue" });
  await page.getByRole("button", { name: "Add line" }).click();
  await expect(page.getByText("Consulting service")).toBeVisible();

  await page
    .getByRole("link", { name: "Back to invoice", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "INV-E2E-DRAFT-001" }),
  ).toBeVisible();

  // The maker may submit but must not be offered approval or issuing.
  await expect(page.getByRole("button", { name: "Approve" })).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Issue invoice" }),
  ).toBeHidden();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.getByRole("button", { name: "Confirm submit" }).click();
  await expect(page.getByText("Under review").first()).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Submit for review" }),
  ).toBeHidden();
  await expect(page.getByRole("link", { name: "Edit" })).toBeHidden();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // A different actor holds approval and issuing authority.
  await signIn(page, "approver@example.test");
  await page.goto(`/invoices/${DRAFT_INVOICE_ID}`);
  await expect(
    page.getByRole("heading", { name: "INV-E2E-DRAFT-001" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("button", { name: "Confirm approve" }).click();
  await expect(page.getByText("Approved").first()).toBeVisible();

  await expect(page.getByRole("button", { name: "Download PDF" })).toBeHidden();
  await page.getByRole("button", { name: "Issue invoice" }).click();
  await page.getByRole("button", { name: "Confirm issue" }).click();
  await expect(page.getByText("Issued").first()).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toBe("INV-E2E-DRAFT-001.pdf");

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "receiptmaker@example.test");
  await expect(page.getByRole("link", { name: "Receipts" })).toBeVisible();
  await page.getByRole("link", { name: "Receipts" }).click();
  await page.getByRole("link", { name: "New Receipt" }).click();
  await page
    .getByLabel("Client")
    .selectOption({ label: "E2E Draft Client (PKR)" });
  await page.getByLabel("Received at").fill("2026-09-10T10:00");
  await page.getByLabel("Value date").fill("2026-09-10");
  await page.getByLabel("Amount").fill("10000.00");
  await page.getByLabel("Payment method").selectOption("BANK_TRANSFER");
  await page.getByLabel("Receiving bank account").selectOption("bank-1");
  await page.getByLabel("External reference").fill("BANK-E2E-9");
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page.getByRole("heading", { name: "RCPT-E2E-001" })).toBeVisible(
    { timeout: 15_000 },
  );
  await expect(
    page.getByRole("button", { name: "Confirm receipt" }),
  ).toBeHidden();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "receiptchecker@example.test");
  const sessionResponse = await page.request.get("/api/auth/session");
  expect(sessionResponse.ok()).toBeTruthy();
  expect((await sessionResponse.json()).permissions).not.toContain(
    "finance.manage_chart_of_accounts",
  );
  await page.goto("/receipts/70000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "Confirm receipt" }).click();
  await expect(page.getByText("CONFIRMED")).toBeVisible();
  await page.getByLabel("Eligible invoice").selectOption(DRAFT_INVOICE_ID);
  await page.getByLabel("Allocation amount").fill("6000.00");
  await page.getByRole("button", { name: "Allocate payment" }).click();
  await expect(page.getByText(/^PKR\s+4,000\.00$/).first()).toBeVisible();
  await page.getByRole("link", { name: "INV-E2E-DRAFT-001" }).click();
  await expect(page.getByText(/^PKR\s+6,000\.00$/).first()).toBeVisible();
  await expect(page.getByText(/^PKR\s+4,000\.00$/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "RCPT-E2E-001" })).toBeVisible();

  await page.getByRole("link", { name: "RCPT-E2E-001" }).click();
  await page.getByLabel("Eligible invoice").selectOption(DRAFT_INVOICE_ID);
  await page.getByLabel("Allocation amount").fill("4000.00");
  await page.getByRole("button", { name: "Allocate payment" }).click();
  await expect(page.locator(".status-badge")).toHaveText("ALLOCATED");
  await expect(page.getByText(/^PKR\s+0\.00$/)).toBeVisible();
  await page.getByRole("link", { name: "INV-E2E-DRAFT-001" }).first().click();
  await expect(page.getByText("Paid").first()).toBeVisible();
  await expect(page.getByText(/^PKR\s+10,000\.00$/).first()).toBeVisible();
  await expect(page.getByText(/^PKR\s+0\.00$/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "RCPT-E2E-001" })).toHaveCount(2);
});

test("least-privilege Vendor manager creates, edits, and searches Vendor master data", async ({
  page,
}) => {
  await signIn(page, "vendormanager@example.test");
  const sessionResponse = await page.request.get("/api/auth/session");
  const session = await sessionResponse.json();
  expect(session.permissions).toEqual([
    "finance.view_vendor",
    "finance.add_vendor",
    "finance.change_vendor",
  ]);
  expect(session.permissions).not.toContain("finance.manage_procurement");
  expect(session.permissions).not.toContain("finance.manage_chart_of_accounts");

  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await expect(page).toHaveURL(/\/vendors$/);
  await page.getByRole("link", { name: "New Vendor" }).click();
  await page.getByLabel("Code").fill("V-E2E-001");
  await page.getByLabel("Vendor name").fill("E2E Secure Supplier");
  await page.getByLabel("Tax number").fill("NTN-E2E");
  await page.getByLabel("Email").fill("supplier@example.test");
  await page
    .getByLabel("Payable account")
    .selectOption({ label: "2000 — Trade Payables" });
  await page.getByRole("button", { name: "Save Vendor" }).click();

  await expect(page).toHaveURL(/\/vendors\/80000000-/);
  await expect(
    page.getByRole("heading", { name: "E2E Secure Supplier" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Edit Vendor" }).click();
  await page.getByLabel("Vendor name").fill("E2E Updated Supplier");
  await page.getByRole("button", { name: "Save Vendor" }).click();
  await expect(
    page.getByRole("heading", { name: "E2E Updated Supplier" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await page.getByLabel("Search").fill("Updated Supplier");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("link", { name: "V-E2E-001" })).toBeVisible();
});

test("least-privilege Bill author completes draft Vendor Bill authoring", async ({
  page,
}) => {
  // This full lifecycle takes about 36 seconds in the Next.js dev E2E harness.
  test.setTimeout(60_000);
  await signIn(page, "billauthor@example.test");
  const session = await (await page.request.get("/api/auth/session")).json();
  expect(session.permissions).not.toContain("finance.manage_procurement");
  expect(session.permissions).not.toContain("finance.manage_chart_of_accounts");
  expect(session.permissions).not.toContain("finance.approve_finance");

  await page.getByRole("link", { name: "Vendor Bills" }).click();
  await page.getByRole("link", { name: "New Vendor Bill" }).click();
  await page.getByLabel("Internal Bill Reference").fill("BILL-E2E-001");
  await page.getByLabel("Supplier Invoice Number").fill("SUP-E2E-001");
  await page.getByLabel("Bill date").fill("2026-09-17");
  await page.getByLabel("Due date").fill("2026-10-17");
  const vendorSelect = page.getByRole("combobox", {
    name: "Vendor",
    exact: true,
  });
  await vendorSelect.selectOption({
    label: "V-E2E-001 — E2E Updated Supplier",
  });
  await expect(vendorSelect).toHaveValue(
    "80000000-0000-0000-0000-000000000001",
  );
  const createResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/vendor-bills") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create draft" }).click();
  expect((await createResponse).status()).toBe(201);
  await expect(page).toHaveURL(/\/vendor-bills\/81000000-.*\/edit$/, {
    timeout: 15_000,
  });

  await page.getByLabel("Description").fill("Operating supplies");
  await page.getByLabel("Quantity").fill("2.0000");
  await page.getByLabel("Unit price").fill("100.00");
  await page.getByLabel("Tax amount").fill("20.00");
  await page
    .getByLabel("Expense / asset account")
    .selectOption(VENDOR_BILL_ACCOUNT_ID);
  await page.getByRole("button", { name: "Add line" }).click();
  await expect(page.getByText("220.00").first()).toBeVisible();

  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Quantity").fill("3.0000");
  await page.getByRole("button", { name: "Save line" }).click();
  await expect(page.getByText("320.00").first()).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("No line items yet.")).toBeVisible();

  await page.getByLabel("Description").fill("Replacement supplies");
  await page.getByLabel("Quantity").fill("1.0000");
  await page.getByLabel("Unit price").fill("100.00");
  await page.getByLabel("Tax amount").fill("20.00");
  await page
    .getByLabel("Expense / asset account")
    .selectOption(VENDOR_BILL_ACCOUNT_ID);
  await page.getByRole("button", { name: "Add line" }).click();
  await page.getByLabel("Due date").fill("2026-10-31");
  await page.getByRole("button", { name: "Save header" }).click();
  await expect(page).toHaveURL(/\/vendor-bills\/81000000-/);
  await expect(page.getByText("SUP-E2E-001")).toBeVisible();
  await expect(page.getByText("2026-10-31")).toBeVisible();
  await expect(page.getByText("120.00").first()).toBeVisible();
  await page.getByLabel("Supporting document").setInputFiles({
    name: "supplier-invoice.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%%EOF"),
  });
  await expect(
    page.getByRole("link", { name: "supplier-invoice.pdf" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.getByRole("button", { name: "Confirm submit for review" }).click();
  await expect(page.getByText("SUBMITTED")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "billchecker@example.test");
  const checkerSession = await (
    await page.request.get("/api/auth/session")
  ).json();
  expect(checkerSession.permissions).not.toContain(
    "finance.manage_procurement",
  );
  expect(checkerSession.permissions).not.toContain(
    "finance.manage_chart_of_accounts",
  );
  await page.goto(`/vendor-bills/81000000-0000-0000-0000-000000000001`);
  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("button", { name: "Confirm approve" }).click();
  await expect(page.getByText("APPROVED")).toBeVisible();
  await page.getByRole("button", { name: "Post to accounts payable" }).click();
  await page
    .getByRole("button", { name: "Confirm post to accounts payable" })
    .click();
  await expect(page.getByText("POSTED")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Edit Vendor Bill" }),
  ).toHaveCount(0);
  const download = await page.request.get(
    "/api/vendor-bills/81000000-0000-0000-0000-000000000001/attachments/83000000-0000-0000-0000-000000000001/download",
  );
  expect(download.status()).toBe(200);
});

test("least-privilege payment maker and checker settle a posted Vendor Bill", async ({
  page,
}) => {
  await signIn(page, "paymentmaker@example.test");
  const makerSession = await (
    await page.request.get("/api/auth/session")
  ).json();
  expect(makerSession.permissions).not.toContain("finance.approve_finance");
  expect(makerSession.permissions).not.toContain("finance.post_journal");
  expect(makerSession.permissions).not.toContain("finance.manage_procurement");
  expect(makerSession.permissions).not.toContain(
    "finance.manage_chart_of_accounts",
  );

  await page.getByRole("link", { name: "Vendor Payments" }).click();
  await page.getByRole("link", { name: "New Vendor Payment" }).click();
  await page
    .getByLabel("Vendor Bill")
    .selectOption("81000000-0000-0000-0000-000000000001");
  await page.getByLabel("Voucher number").fill("PV-E2E-001");
  await page.getByLabel("Payment date").fill("2026-09-18");
  await page.getByLabel("Amount").fill("70.00");
  await page.getByLabel("Reference").fill("MAKER-REF");
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page).toHaveURL(/\/vendor-payments\/84000000-/);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText("SUBMITTED")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "paymentchecker@example.test");
  const checkerSession = await (
    await page.request.get("/api/auth/session")
  ).json();
  expect(checkerSession.permissions).not.toContain(
    "finance.add_paymentvoucher",
  );
  expect(checkerSession.permissions).not.toContain(
    "finance.manage_procurement",
  );
  expect(checkerSession.permissions).not.toContain(
    "finance.manage_chart_of_accounts",
  );
  await page.goto("/vendor-payments/84000000-0000-0000-0000-000000000001");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("APPROVED")).toBeVisible();
  await page
    .getByLabel("Payment account")
    .selectOption("50000000-0000-0000-0000-000000000400");
  await page.getByLabel("Payment reference").fill("BANK-E2E-001");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Pay Vendor" }).click();
  await expect(page.getByText("PAID")).toHaveCount(2);

  await page.getByRole("link", { name: "Open Vendor Bill" }).click();
  await expect(page.getByText("PARTIALLY PAID")).toBeVisible();
  await expect(page.getByText("70.00").first()).toBeVisible();
  await expect(page.getByText("50.00").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "PV-E2E-001" })).toBeVisible();
});

test("general-business administrator completes People and Client Contract setup without security traffic", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const securityRequests: string[] = [];
  page.on("request", (request) => {
    if (
      /\/api\/(?:client-contracts\/(?:sites|posts|staffing)|people\/readiness\/guards)/.test(
        request.url(),
      )
    )
      securityRequests.push(request.url());
  });
  await signIn(page, "workspaceadmin@example.test");
  await expect(
    page
      .getByLabel("Primary navigation")
      .getByRole("heading", { name: "People" }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Primary navigation")
      .getByRole("heading", { name: "Clients" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Employees", exact: true }).click();
  await page.getByRole("link", { name: "Add employee" }).click();
  await page.getByLabel("Employee number").fill("EMP-E2E-001");
  await page.getByLabel("First name").fill("Amina");
  await page.getByLabel("Last name").fill("Khan");
  await page.getByLabel("Mobile number").fill("03000000000");
  await page.getByRole("button", { name: "Save employee" }).click();
  await expect(page).toHaveURL(/\/employees\/61000000-/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Amina Khan" })).toBeVisible();
  await page.getByRole("link", { name: "Edit employee" }).click();
  await page.getByLabel("Personal email").fill("amina.updated@example.test");
  await page.getByRole("button", { name: "Save employee" }).click();
  await expect(page.getByText("amina.updated@example.test")).toBeVisible();

  await page.getByRole("link", { name: "Clients", exact: true }).click();
  await page.getByRole("link", { name: "Add client" }).click();
  await page
    .getByRole("textbox", { name: "Client code", exact: true })
    .fill("CLI-E2E-001");
  await page.getByLabel("Legal name").fill("Acme Advisory Limited");
  await page.getByLabel("Trade name").fill("Acme Advisory");
  await page.getByLabel("Industry").selectOption(INDUSTRY_ID);
  await page.getByLabel("Main email").fill("hello@acme.test");
  await page.getByRole("button", { name: "Save client" }).click();
  await expect(page).toHaveURL(/\/clients\/63000000-/, { timeout: 15_000 });
  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.getByText("Active").first()).toBeVisible();
  await page.locator("summary", { hasText: "Add contact" }).click();
  await page.getByLabel("Name").last().fill("Fatima Ali");
  await page.getByLabel("Email").last().fill("fatima@acme.test");
  await page.getByRole("button", { name: "Add contact" }).click();
  await expect(page.getByText("Fatima Ali")).toBeVisible();

  await page.getByRole("link", { name: "Create contract" }).click();
  await page
    .getByRole("textbox", { name: "Contract number", exact: true })
    .fill("CTR-E2E-001");
  await page.getByLabel("Title").fill("Advisory services agreement");
  await page.getByLabel("Contract type").selectOption("PROJECT");
  await page.getByLabel("Start date").fill("2026-10-19");
  await page.getByRole("button", { name: "Save contract" }).click();
  await expect(page).toHaveURL(/\/contracts\/65000000-/, { timeout: 15_000 });
  await expect(
    page.getByRole("heading", { name: "Advisory services agreement" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Contracts", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Advisory services agreement" }),
  ).toBeVisible();
  await expect(page.locator("main")).not.toContainText(
    /Security Site|Security Post|staffing requirement/i,
  );
  expect(securityRequests).toEqual([]);
});

test("Company switching removes stale People and Client Contract capabilities", async ({
  page,
}) => {
  await signIn(page, "multicompany@example.test");
  const switcher = page.getByLabel("Active Company");
  await switcher.selectOption(COMPANY_A_ID);
  await expect(
    page.getByRole("link", { name: "Employees", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Employees", exact: true }).click();
  await expect(page.getByRole("link", { name: "Amina Khan" })).toBeVisible();

  await page.getByLabel("Active Company").selectOption(COMPANY_B_ID);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("link", { name: "Employees", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Clients", exact: true }),
  ).toHaveCount(0);
  await page.goto("/employees");
  await expect(
    page.getByRole("heading", { name: "Module unavailable" }),
  ).toBeVisible();
  await expect(page.getByText("Amina Khan")).toHaveCount(0);

  await page.getByLabel("Active Company").selectOption(COMPANY_A_ID);
  await expect(
    page.getByRole("link", { name: "Employees", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Employees", exact: true }).click();
  await expect(page.getByRole("link", { name: "Amina Khan" })).toBeVisible();
});

test("read-only workspace user sees lists without create or edit actions", async ({
  page,
}) => {
  await signIn(page, "workspaceviewer@example.test");
  await page.getByRole("link", { name: "Employees", exact: true }).click();
  await expect(page.getByRole("link", { name: "Amina Khan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Add employee" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Edit" })).toHaveCount(0);
  await page.getByRole("link", { name: "Clients", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Acme Advisory Limited" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Add client" })).toHaveCount(0);
});
