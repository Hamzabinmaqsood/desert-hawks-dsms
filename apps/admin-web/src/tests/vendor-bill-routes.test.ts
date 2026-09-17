import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET as accounts } from "@/app/api/reference/vendor-bill-accounts/route";
import {
  GET as detail,
  PATCH as update,
} from "@/app/api/vendor-bills/[id]/route";
import { POST as addLine } from "@/app/api/vendor-bills/[id]/lines/route";
import {
  DELETE as deleteLine,
  PATCH as updateLine,
} from "@/app/api/vendor-bills/[id]/lines/[lineId]/route";
import { GET as list, POST as create } from "@/app/api/vendor-bills/route";
import { POST as submit } from "@/app/api/vendor-bills/[id]/submit/route";
import { POST as reject } from "@/app/api/vendor-bills/[id]/reject/route";
import {
  GET as attachments,
  POST as uploadAttachment,
} from "@/app/api/vendor-bills/[id]/attachments/route";
import { GET as downloadAttachment } from "@/app/api/vendor-bills/[id]/attachments/[attachmentId]/download/route";
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
      ...(init.headers ?? {}),
      Origin: "http://admin.test",
      Host: "admin.test",
    },
  });
}
const context = { params: Promise.resolve({ id: "bill" }) };
const lineContext = { params: Promise.resolve({ id: "bill", lineId: "line" }) };
const attachmentContext = {
  params: Promise.resolve({ id: "bill", attachmentId: "attachment" }),
};

describe("Vendor Bill BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });
  it("forwards only supported list filters", async () => {
    const backend = vi.fn(async () => json({ count: 0, results: [] }));
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await list(
          request(
            "/api/vendor-bills?search=x&status=DRAFT&vendor=v&company=foreign",
          ),
        )
      ).status,
    ).toBe(200);
    const url = String((backend.mock.calls[0] as unknown as [URL])[0]);
    expect(url).toContain("search=x");
    expect(url).toContain("status=DRAFT");
    expect(url).not.toContain("company");
  });
  it("requires same origin and strips all server-owned header fields", async () => {
    expect(
      (
        await create(
          new NextRequest("http://admin.test/api/vendor-bills", {
            method: "POST",
            headers: { Origin: "https://evil.test" },
            body: "{}",
          }),
        )
      ).status,
    ).toBe(403);
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({
        vendor: "v",
        bill_number: "B-1",
        vendor_invoice_number: "S-1",
        bill_date: "2026-09-17",
        due_date: "2026-10-17",
        match_type: "TWO_WAY",
      });
      return json({ id: "bill" }, 201);
    });
    vi.stubGlobal("fetch", backend);
    const response = await create(
      request("/api/vendor-bills", {
        method: "POST",
        body: JSON.stringify({
          vendor: "v",
          bill_number: "B-1",
          vendor_invoice_number: "S-1",
          bill_date: "2026-09-17",
          due_date: "2026-10-17",
          match_type: "TWO_WAY",
          company: "foreign",
          status: "POSTED",
          subtotal: "9",
          total_amount: "9",
          paid_amount: "9",
          created_by: "x",
          approved_by: "x",
          journal_entry: "x",
          match_exception: "x",
        }),
      }),
    );
    expect(response.status).toBe(201);
  });
  it("supports detail and allowlisted header PATCH with field errors", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ id: "bill" }))
      .mockImplementationOnce(async (_url: unknown, init?: RequestInit) => {
        expect(JSON.parse(String(init?.body))).toEqual({ due_date: "bad" });
        return json({ due_date: ["Invalid date."] }, 400);
      });
    vi.stubGlobal("fetch", backend);
    expect(
      (await detail(request("/api/vendor-bills/bill"), context)).status,
    ).toBe(200);
    const response = await update(
      request("/api/vendor-bills/bill", {
        method: "PATCH",
        body: JSON.stringify({
          due_date: "bad",
          status: "POSTED",
          total_amount: "1",
        }),
      }),
      context,
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      due_date: ["Invalid date."],
    });
  });
  it("allowlists line mutations, supports delete, and proxies minimal accounts", async () => {
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      if (init?.body) {
        const body = JSON.parse(String(init.body));
        expect(body.vendor_bill).toBeUndefined();
        expect(body.line_total).toBeUndefined();
        expect(body.status).toBeUndefined();
      }
      return json(init?.method === "DELETE" ? null : []);
    });
    vi.stubGlobal("fetch", backend);
    const malicious = {
      description: "Fuel",
      quantity: "2",
      unit_price: "100",
      tax_amount: "20",
      expense_account: "a",
      vendor_bill: "other",
      line_total: "999",
      status: "POSTED",
    };
    expect(
      (
        await addLine(
          request("/api/vendor-bills/bill/lines", {
            method: "POST",
            body: JSON.stringify(malicious),
          }),
          context,
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await updateLine(
          request("/api/vendor-bills/bill/lines/line", {
            method: "PATCH",
            body: JSON.stringify(malicious),
          }),
          lineContext,
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await deleteLine(
          request("/api/vendor-bills/bill/lines/line", { method: "DELETE" }),
          lineContext,
        )
      ).status,
    ).toBe(200);
    expect(
      (await accounts(request("/api/reference/vendor-bill-accounts"))).status,
    ).toBe(200);
    expect(String((backend.mock.calls[3] as unknown as [URL])[0])).toContain(
      "finance/ap-reference/expense-accounts/",
    );
  });
  it("sends empty workflow payloads and allowlists only rejection reason", async () => {
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.status).toBeUndefined();
      expect(body.company).toBeUndefined();
      expect(body.journal_entry).toBeUndefined();
      return json({ status: "SUBMITTED" });
    });
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await submit(
          request("/api/vendor-bills/bill/submit", {
            method: "POST",
            body: JSON.stringify({
              status: "POSTED",
              company: "x",
              journal_entry: "x",
            }),
          }),
          context,
        )
      ).status,
    ).toBe(200);
    expect(
      JSON.parse(
        String(
          (backend.mock.calls[0] as unknown as [unknown, RequestInit])[1].body,
        ),
      ),
    ).toEqual({});
    await reject(
      request("/api/vendor-bills/bill/reject", {
        method: "POST",
        body: JSON.stringify({
          reason: "Wrong price",
          status: "REJECTED",
          approved_by: "x",
        }),
      }),
      context,
    );
    expect(
      JSON.parse(
        String(
          (backend.mock.calls[1] as unknown as [unknown, RequestInit])[1].body,
        ),
      ),
    ).toEqual({ reason: "Wrong price" });
  });
  it("allowlists one attachment file and privately proxies downloads", async () => {
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      if (init?.method === "POST") {
        const data = init.body as FormData;
        expect([...data.keys()]).toEqual(["file"]);
      }
      return new Response(
        init?.method === "GET" ? "pdf" : JSON.stringify({ id: "a" }),
        {
          status: 200,
          headers: {
            "Content-Type":
              init?.method === "GET" ? "application/pdf" : "application/json",
            "Content-Disposition": "attachment; filename=invoice.pdf",
          },
        },
      );
    });
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await attachments(
          request("/api/vendor-bills/bill/attachments"),
          context,
        )
      ).status,
    ).toBe(200);
    const form = new FormData();
    form.set(
      "file",
      new File(["%PDF-1.4"], "invoice.pdf", { type: "application/pdf" }),
    );
    form.set("company", "foreign");
    const multipart = request("/api/vendor-bills/bill/attachments", {
      method: "POST",
    });
    vi.spyOn(multipart, "formData").mockResolvedValue(form);
    expect((await uploadAttachment(multipart, context)).status).toBe(200);
    const downloaded = await downloadAttachment(
      request("/api/vendor-bills/bill/attachments/attachment/download"),
      attachmentContext,
    );
    expect(downloaded.status).toBe(200);
    expect(downloaded.headers.get("Cache-Control")).toBe("private, no-store");
  });
});
