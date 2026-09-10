import { randomUUID } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

const DRAFT_INVOICE_ID = "90000000-0000-0000-0000-000000000001";

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
    page.getByRole("img", { name: "Desert Hawks official logo" }),
  ).toBeVisible();

  await page.getByLabel("Work email").fill("employee@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("img", { name: "Desert Hawks official logo" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Welcome, Test" }),
  ).toBeVisible();
  await expect(page.getByText("employee@example.test").first()).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
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

test("a maker submits a draft and a separate approver approves, issues and downloads it", async ({
  page,
}) => {
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
});
