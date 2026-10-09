import { randomUUID } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

const DRAFT_INVOICE_ID = "90000000-0000-0000-0000-000000000001";
const VENDOR_BILL_ACCOUNT_ID = "50000000-0000-0000-0000-000000000300";
const COMPANY_A_ID = "00000000-0000-0000-0000-000000000002";
const COMPANY_B_ID = "00000000-0000-0000-0000-000000000003";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("employee signs in, uses the protected shell, and signs out", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByRole("img", { name: "DSMS platform mark" }),
  ).toBeVisible();
  await expect(page.locator(".brand-login")).not.toContainText("Desert Hawks");

  await page.getByLabel("Work email").fill("employee@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("img", { name: "DSMS platform mark" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Alpha Shield workspace" }),
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

  await switcher.selectOption({ label: "DHA — Desert Hawks Alpha" });
  await expect(switcher).toHaveValue(COMPANY_A_ID);
  await expect(
    page.getByRole("heading", { name: "Alpha Shield workspace" }),
  ).toBeVisible();
  await expect(page.locator(".sidebar .brand")).toContainText(
    "Alpha operations",
  );
  await expect(page.locator(".sidebar .brand")).not.toContainText(
    "Desert Hawks",
  );
  await expect(page).toHaveTitle("Alpha Shield — DSMS");

  await switcher.selectOption({ label: "DHB — Desert Hawks Bravo" });
  await expect(switcher).toHaveValue(COMPANY_B_ID);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByText("multicompany@example.test").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Bravo Guard workspace" }),
  ).toBeVisible();
  await expect(page.locator(".sidebar .brand")).toContainText(
    "Bravo operations",
  );
  await expect(page.locator(".sidebar .brand")).not.toContainText(
    "Alpha Shield",
  );
  await expect(page.locator(".sidebar .brand")).not.toContainText(
    "Desert Hawks",
  );
  await expect(page).toHaveTitle("Bravo Guard — DSMS");
});

test("employee reads an Invoice list and detail", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("employee@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Invoices" }).click();
  await expect(page).toHaveURL(/\/invoices$/);
  await expect(page.getByRole("heading", { name: "Invoices" })).toBeVisible();
  await page.getByRole("link", { name: "INV-E2E-001" }).click();
  await expect(page).toHaveURL(/\/invoices\/10000000-/);
  await expect(
    page.getByRole("heading", { name: "INV-E2E-001" }),
  ).toBeVisible();
  await expect(page.getByText("Monthly guarding service")).toBeVisible();
  await expect(page.getByText(/PKR.*11,600.00/).first()).toBeVisible();
  await expect(page.getByText("Issued").first()).toBeVisible();
  await page.getByRole("link", { name: "Invoices" }).first().click();
  await expect(page).toHaveURL(/\/invoices$/);
});

test("a maker creates a draft invoice, adds and edits a line, and sees server totals", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("maker@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.getByRole("link", { name: "Invoices" }).click();
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

  await page.getByLabel("Description").fill("Guard patrol");
  await page.getByLabel("Quantity").fill("4.0000");
  await page.getByLabel("Unit price").fill("2500.00");
  await page
    .getByRole("combobox", { name: "Revenue account" })
    .selectOption({ label: "4000 — Service Revenue" });
  await page.getByRole("button", { name: "Add line" }).click();

  await expect(page.getByText("Guard patrol")).toBeVisible();
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
  await expect(page.getByText("Guard patrol")).toBeVisible();
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

  await page.getByLabel("Description").fill("Guard patrol");
  await page.getByLabel("Quantity").fill("4.0000");
  await page.getByLabel("Unit price").fill("2500.00");
  await page
    .getByRole("combobox", { name: "Revenue account" })
    .selectOption({ label: "4000 — Service Revenue" });
  await page.getByRole("button", { name: "Add line" }).click();
  await expect(page.getByText("Guard patrol")).toBeVisible();

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

  await page.getByRole("link", { name: "Vendors" }).click();
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

  await page.getByRole("link", { name: "Vendors" }).first().click();
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
  await expect(page).toHaveURL(/\/vendor-bills\/81000000-.*\/edit$/);

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
