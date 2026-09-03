import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

test("employee signs in, uses the protected shell, and signs out", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Work email").fill("employee@example.test");
  await page.getByLabel("Password").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
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
