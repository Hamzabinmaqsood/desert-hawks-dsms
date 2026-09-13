import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as allocate } from "@/app/api/receipts/[id]/allocate/route";
import { GET as eligible } from "@/app/api/receipts/[id]/eligible-invoices/route";
import { GET as detail } from "@/app/api/receipts/[id]/route";
import { GET as list, POST as create } from "@/app/api/receipts/route";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function request(
  path: string,
  init: {
    method?: string;
    body?: string;
    headers?: Record<string, string>;
  } = {},
) {
  return new NextRequest(`http://admin.test${path}`, {
    method: init.method,
    body: init.body,
    headers: {
      Cookie: `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`,
      ...init.headers,
    },
  });
}

describe("Receipt BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("allowlists list filters and uses the scoped backend path", async () => {
    const backend = vi.fn(async () =>
      json({ count: 0, next: null, previous: null, results: [] }),
    );
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await list(
          request("/api/receipts?status=CONFIRMED&search=RCPT&secret=x"),
        )
      ).status,
    ).toBe(200);
    const url = String((backend.mock.calls[0] as unknown as [URL])[0]);
    expect(url).toContain("billing/receipts/?status=CONFIRMED&search=RCPT");
    expect(url).not.toContain("secret");
  });

  it("requires same origin and strips server-owned create fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ id: "receipt-1" }, 201)),
    );
    const rejected = await create(
      request("/api/receipts", {
        method: "POST",
        headers: { Origin: "https://evil.test" },
        body: "{}",
      }),
    );
    expect(rejected.status).toBe(403);
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toMatchObject({
        company: "c",
        client: "x",
        amount: "10.00",
      });
      expect(body.status).toBeUndefined();
      expect(body.received_by).toBeUndefined();
      expect(body.allocated_amount).toBeUndefined();
      return json({ id: "receipt-1" }, 201);
    });
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await create(
          request("/api/receipts", {
            method: "POST",
            headers: { Origin: "http://admin.test", Host: "admin.test" },
            body: JSON.stringify({
              company: "c",
              client: "x",
              amount: "10.00",
              status: "ALLOCATED",
              received_by: "attacker",
              allocated_amount: "10",
            }),
          }),
        )
      ).status,
    ).toBe(201);
  });

  it("allowlists allocation input and preserves backend validation", async () => {
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({ invoice: "invoice-1", amount: "25.00" });
      return json({ amount: ["Allocation exceeds balance."] }, 400);
    });
    vi.stubGlobal("fetch", backend);
    const response = await allocate(
      request("/api/receipts/r/allocate", {
        method: "POST",
        headers: { Origin: "http://admin.test", Host: "admin.test" },
        body: JSON.stringify({
          invoice: "invoice-1",
          amount: "25.00",
          allocated_by: "attacker",
          balance: "0",
        }),
      }),
      { params: Promise.resolve({ id: "r" }) },
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      amount: ["Allocation exceeds balance."],
    });
  });

  it("normalizes detail errors and routes eligible invoices", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "hidden" }, 404))
      .mockResolvedValueOnce(json([{ id: "i" }]));
    vi.stubGlobal("fetch", backend);
    const missing = await detail(request("/api/receipts/missing"), {
      params: Promise.resolve({ id: "missing" }),
    });
    expect(missing.status).toBe(404);
    expect(JSON.stringify(await missing.json())).not.toContain("hidden");
    expect(
      (
        await eligible(request("/api/receipts/r/eligible-invoices"), {
          params: Promise.resolve({ id: "r" }),
        })
      ).status,
    ).toBe(200);
    expect(String((backend.mock.calls[1] as unknown as [URL])[0])).toContain(
      "billing/receipts/r/eligible-invoices/",
    );
  });
});
