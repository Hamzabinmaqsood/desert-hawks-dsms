import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET as detail } from "@/app/api/vendor-payments/[id]/route";
import { POST as pay } from "@/app/api/vendor-payments/[id]/pay/route";
import { POST as reject } from "@/app/api/vendor-payments/[id]/reject/route";
import { POST as submit } from "@/app/api/vendor-payments/[id]/submit/route";
import { GET as list, POST as create } from "@/app/api/vendor-payments/route";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function request(
  path: string,
  init: {
    method?: string;
    body?: string;
    headers?: Record<string, string>;
  } = {},
) {
  return new NextRequest(`http://admin.test${path}`, {
    ...init,
    headers: {
      Cookie: `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`,
      Origin: "http://admin.test",
      Host: "admin.test",
      ...(init.headers ?? {}),
    },
  });
}
const context = { params: Promise.resolve({ id: "voucher" }) };

describe("Vendor Payment BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("uses the dedicated scoped list and detail paths", async () => {
    const backend = vi.fn(async () => json({ count: 0, results: [] }));
    vi.stubGlobal("fetch", backend);
    await list(request("/api/vendor-payments?status=DRAFT&company=foreign"));
    await detail(request("/api/vendor-payments/voucher"), context);
    const listUrl = String((backend.mock.calls[0] as unknown as [URL])[0]);
    const detailUrl = String((backend.mock.calls[1] as unknown as [URL])[0]);
    expect(listUrl).toContain("finance/vendor-payments/?status=DRAFT");
    expect(listUrl).not.toContain("company");
    expect(detailUrl).toContain("finance/vendor-payments/voucher/");
  });

  it("strips server-owned create and workflow fields", async () => {
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.company).toBeUndefined();
      expect(body.status).toBeUndefined();
      expect(body.payment_status).toBeUndefined();
      expect(body.journal_entry).toBeUndefined();
      expect(body.paid_amount).toBeUndefined();
      return json({ id: "voucher" }, 201);
    });
    vi.stubGlobal("fetch", backend);
    await create(
      request("/api/vendor-payments", {
        method: "POST",
        body: JSON.stringify({
          vendor_bill: "bill",
          voucher_number: "PV-1",
          payment_date: "2026-09-18",
          amount: "50.00",
          company: "foreign",
          status: "PAID",
          payment_status: "PAID",
          journal_entry: "journal",
          paid_amount: "999",
        }),
      }),
    );
    await submit(
      request("/api/vendor-payments/voucher/submit", {
        method: "POST",
        body: JSON.stringify({ status: "PAID", company: "foreign" }),
      }),
      context,
    );
    expect(JSON.parse(String(backend.mock.calls[1]?.[1]?.body))).toEqual({});
  });

  it("allowlists only reason for reject and account/reference for pay", async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: unknown, init?: RequestInit) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ id: "voucher" });
      }),
    );
    await reject(
      request("/api/vendor-payments/voucher/reject", {
        method: "POST",
        body: JSON.stringify({ reason: "Duplicate", approved_by: "attacker" }),
      }),
      context,
    );
    await pay(
      request("/api/vendor-payments/voucher/pay", {
        method: "POST",
        body: JSON.stringify({
          payment_account: "cash",
          payment_reference: "BANK-1",
          journal_lines: [{ debit: "999" }],
          payment_status: "PAID",
        }),
      }),
      context,
    );
    expect(bodies).toEqual([
      { reason: "Duplicate" },
      { payment_account: "cash", payment_reference: "BANK-1" },
    ]);
  });

  it("rejects cross-origin mutations", async () => {
    const result = await create(
      new NextRequest("http://admin.test/api/vendor-payments", {
        method: "POST",
        headers: { Origin: "https://evil.test", Host: "admin.test" },
        body: "{}",
      }),
    );
    expect(result.status).toBe(403);
  });
});
