import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as createInvoice, GET as list } from "@/app/api/invoices/route";
import { PATCH as patchInvoice } from "@/app/api/invoices/[id]/route";
import { POST as addLine } from "@/app/api/invoices/[id]/lines/route";
import {
  DELETE as deleteLine,
  PATCH as patchLine,
} from "@/app/api/invoices/[id]/lines/[lineId]/route";
import { GET as billingProfiles } from "@/app/api/reference/billing-profiles/route";
import { GET as revenueAccounts } from "@/app/api/reference/accounts/route";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Origin", "http://admin.test");
  headers.set("Host", "admin.test");
  headers.set("Cookie", `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`);
  const { signal, ...rest } = init;
  return new NextRequest(`http://admin.test${path}`, {
    ...rest,
    headers,
    signal: signal ?? undefined,
  });
}

function crossOriginRequest(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Origin", "http://attacker.test");
  headers.set("Host", "admin.test");
  headers.set("Cookie", `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`);
  const { signal, ...rest } = init;
  return new NextRequest(`http://admin.test${path}`, {
    ...rest,
    headers,
    signal: signal ?? undefined,
  });
}

describe("Invoice mutation BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("rejects cross-origin invoice creation without calling the backend", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    const response = await createInvoice(
      crossOriginRequest("/api/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ billing_profile: "profile-1" }),
      }),
    );
    expect(response.status).toBe(403);
    expect(backend).not.toHaveBeenCalled();
  });

  it("forwards only writable create fields and strips workflow fields", async () => {
    const backend = vi.fn(async () => json({ id: "invoice-1" }, 201));
    vi.stubGlobal("fetch", backend);
    const response = await createInvoice(
      request("/api/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          billing_profile: "profile-1",
          invoice_date: "2026-09-01",
          invoice_type: "STANDARD",
          status: "ISSUED",
          total_amount: "999999.00",
          invoice_number: "FAKE-1",
        }),
      }),
    );
    expect(response.status).toBe(201);
    const call = backend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    const sentBody = JSON.parse(String(call?.[1]?.body));
    expect(sentBody).toEqual({
      billing_profile: "profile-1",
      invoice_date: "2026-09-01",
      invoice_type: "STANDARD",
    });
    expect(sentBody.status).toBeUndefined();
    expect(sentBody.total_amount).toBeUndefined();
    expect(sentBody.invoice_number).toBeUndefined();
  });

  it("normalizes field validation errors on create", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json(
          {
            code: "error",
            detail: "The request could not be completed.",
            errors: { billing_profile: ["This field is required."] },
            billing_profile: ["This field is required."],
          },
          400,
        ),
      ),
    );
    const response = await createInvoice(
      request("/api/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_date: "2026-09-01" }),
      }),
    );
    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.billing_profile).toEqual(["This field is required."]);
    expect(JSON.stringify(body)).not.toContain("code");
  });

  it("surfaces a business-conflict message and never leaks raw envelope text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json(
          {
            code: "error",
            detail: "The request could not be completed.",
            errors: ["Only draft invoices can be edited."],
          },
          400,
        ),
      ),
    );
    const response = await patchInvoice(
      request("/api/invoices/invoice-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_date: "2026-09-02" }),
      }),
      { params: Promise.resolve({ id: "invoice-1" }) },
    );
    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.non_field_errors).toEqual([
      "Only draft invoices can be edited.",
    ]);
  });

  it("rejects cross-origin draft updates", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    const response = await patchInvoice(
      crossOriginRequest("/api/invoices/invoice-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_date: "2026-09-02" }),
      }),
      { params: Promise.resolve({ id: "invoice-1" }) },
    );
    expect(response.status).toBe(403);
    expect(backend).not.toHaveBeenCalled();
  });

  it("forwards only writable draft-update fields", async () => {
    const backend = vi.fn(async () => json({ id: "invoice-1" }));
    vi.stubGlobal("fetch", backend);
    await patchInvoice(
      request("/api/invoices/invoice-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          invoice_date: "2026-09-02",
          billing_profile: "should-be-dropped",
          status: "ISSUED",
        }),
      }),
      { params: Promise.resolve({ id: "invoice-1" }) },
    );
    const call = backend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    const sentBody = JSON.parse(String(call?.[1]?.body));
    expect(sentBody).toEqual({ invoice_date: "2026-09-02" });
  });

  it("rejects cross-origin line mutations and forwards only writable line fields", async () => {
    const rejectedBackend = vi.fn();
    vi.stubGlobal("fetch", rejectedBackend);
    const rejected = await addLine(
      crossOriginRequest("/api/invoices/invoice-1/lines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: "Line" }),
      }),
      { params: Promise.resolve({ id: "invoice-1" }) },
    );
    expect(rejected.status).toBe(403);
    expect(rejectedBackend).not.toHaveBeenCalled();

    const backend = vi.fn(async () => json({ id: "line-1" }, 201));
    vi.stubGlobal("fetch", backend);
    await addLine(
      request("/api/invoices/invoice-1/lines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: "Guarding",
          quantity: "10.0000",
          unit_price: "1000.00",
          revenue_account: "account-1",
          line_total: "999999.00",
        }),
      }),
      { params: Promise.resolve({ id: "invoice-1" }) },
    );
    const call = backend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    const sentBody = JSON.parse(String(call?.[1]?.body));
    expect(sentBody).toEqual({
      description: "Guarding",
      quantity: "10.0000",
      unit_price: "1000.00",
      revenue_account: "account-1",
    });
    expect(sentBody.line_total).toBeUndefined();
  });

  it("updates and deletes a line through the authenticated session path", async () => {
    const patchBackend = vi.fn(async () => json({ id: "line-1" }));
    vi.stubGlobal("fetch", patchBackend);
    const patched = await patchLine(
      request("/api/invoices/invoice-1/lines/line-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantity: "5.0000" }),
      }),
      { params: Promise.resolve({ id: "invoice-1", lineId: "line-1" }) },
    );
    expect(patched.status).toBe(200);

    const deleteBackend = vi.fn(
      async () => new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", deleteBackend);
    const deleted = await deleteLine(
      request("/api/invoices/invoice-1/lines/line-1", { method: "DELETE" }),
      { params: Promise.resolve({ id: "invoice-1", lineId: "line-1" }) },
    );
    expect(deleted.status).toBe(200);
    expect(await deleted.json()).toEqual({ ok: true });

    const call = deleteBackend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    expect(String(call?.[0] ?? "")).toContain(
      "billing/invoices/invoice-1/lines/line-1/",
    );
  });

  it("normalizes 403 and 404 responses without leaking backend detail", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "sensitive" }, 403))
      .mockResolvedValueOnce(json({ detail: "sensitive" }, 404));
    vi.stubGlobal("fetch", backend);
    const forbidden = await deleteLine(
      request("/api/invoices/invoice-1/lines/line-1", { method: "DELETE" }),
      { params: Promise.resolve({ id: "invoice-1", lineId: "line-1" }) },
    );
    expect(forbidden.status).toBe(403);
    expect(JSON.stringify(await forbidden.json())).not.toContain("sensitive");

    const missing = await deleteLine(
      request("/api/invoices/missing/lines/line-1", { method: "DELETE" }),
      { params: Promise.resolve({ id: "missing", lineId: "line-1" }) },
    );
    expect(missing.status).toBe(404);
    expect(JSON.stringify(await missing.json())).not.toContain("sensitive");
  });

  it("proxies scoped billing-profile reference data with only whitelisted params", async () => {
    const backend = vi.fn(async () =>
      json({ count: 0, next: null, previous: null, results: [] }),
    );
    vi.stubGlobal("fetch", backend);
    const response = await billingProfiles(
      request("/api/reference/billing-profiles?is_active=true&extra=drop"),
    );
    expect(response.status).toBe(200);
    const call = backend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    const url = String(call?.[0] ?? "");
    expect(url).toContain("billing/billing-profiles/?is_active=true");
    expect(url).not.toContain("extra");
  });

  it("projects BillingProfile responses down to safe selection fields only", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
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
              billing_address: "123 Internal Street",
              billing_email: "ap@acme.internal",
              billing_phone: "+92-300-0000000",
              tax_registration_number: "NTN-999999",
              payment_terms_days: 30,
              currency: "PKR",
              default_billing_frequency: "MONTHLY",
              default_revenue_account: "account-internal-1",
              default_receivable_account: "account-internal-2",
              default_tax_account: "account-internal-3",
              default_discount_account: null,
              default_payment_instructions: "Wire to internal account only.",
              invoice_notes: "Client has a history of late payment disputes.",
              is_active: true,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
        }),
      ),
    );
    const response = await billingProfiles(
      request("/api/reference/billing-profiles?is_active=true"),
    );
    const body = await response.json();
    expect(body.results[0]).toEqual({
      id: "profile-1",
      client: "client-1",
      company: "company-1",
      billing_name: "Acme Security Client",
      currency: "PKR",
      payment_terms_days: 30,
      is_active: true,
    });
    const raw = JSON.stringify(body);
    expect(raw).not.toContain("billing_address");
    expect(raw).not.toContain("billing_email");
    expect(raw).not.toContain("tax_registration_number");
    expect(raw).not.toContain("default_revenue_account");
    expect(raw).not.toContain("default_receivable_account");
    expect(raw).not.toContain("invoice_notes");
    expect(raw).not.toContain("payment_instructions");
  });

  it("keeps the existing read list route untouched by these changes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    const response = await list(request("/api/invoices"));
    expect(response.status).toBe(200);
  });

  it("routes the revenue-account reference through the least-privilege Invoice endpoint, not chart-of-accounts", async () => {
    const backend = vi.fn(async () =>
      json({ count: 0, next: null, previous: null, results: [] }),
    );
    vi.stubGlobal("fetch", backend);
    const response = await revenueAccounts(request("/api/reference/accounts"));
    expect(response.status).toBe(200);
    const call = backend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    const url = String(call?.[0] ?? "");
    expect(url).toContain("billing/invoice-reference/revenue-accounts/");
    expect(url).not.toContain("finance/accounts");
  });

  it("normalizes a 403 from the revenue-account reference without leaking backend detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ detail: "finance.manage_chart_of_accounts required" }, 403),
      ),
    );
    const response = await revenueAccounts(request("/api/reference/accounts"));
    expect(response.status).toBe(403);
    const body = await response.json();
    expect(JSON.stringify(body)).not.toContain("manage_chart_of_accounts");
    expect(body.message).toBe("You do not have access to this reference data.");
  });
});
