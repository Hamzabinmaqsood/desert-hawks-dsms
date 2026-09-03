import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as list } from "@/app/api/invoices/route";
import { GET as detail } from "@/app/api/invoices/[id]/route";
import { GET as download } from "@/app/api/invoices/[id]/download/route";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function request(path: string) {
  return new NextRequest(`http://admin.test${path}`, {
    headers: { Cookie: `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh` },
  });
}

describe("Invoice BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("forwards only supported list filters and pagination", async () => {
    const backend = vi.fn(async () =>
      json({ count: 0, next: null, previous: null, results: [] }),
    );
    vi.stubGlobal("fetch", backend);
    const response = await list(
      request("/api/invoices?status=ISSUED&page=2&search=INV&ignored=secret"),
    );
    expect(response.status).toBe(200);
    const call = backend.mock.calls[0] as unknown as
      [RequestInfo | URL, RequestInit?] | undefined;
    const url = String(call?.[0] ?? "");
    expect(url).toContain("billing/invoices/?status=ISSUED&page=2&search=INV");
    expect(url).not.toContain("ignored");
    expect((call?.[1] as RequestInit | undefined)?.headers).toMatchObject({
      Authorization: "Bearer access",
    });
  });

  it("returns detail and normalizes hidden or forbidden invoices", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ id: "invoice-1" }))
      .mockResolvedValueOnce(json({ detail: "sensitive" }, 404))
      .mockResolvedValueOnce(json({ detail: "sensitive" }, 403));
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await detail(request("/api/invoices/invoice-1"), {
          params: Promise.resolve({ id: "invoice-1" }),
        })
      ).status,
    ).toBe(200);
    const missing = await detail(request("/api/invoices/missing"), {
      params: Promise.resolve({ id: "missing" }),
    });
    expect(missing.status).toBe(404);
    expect(await missing.json()).toEqual({ message: "Invoice not found." });
    const forbidden = await detail(request("/api/invoices/hidden"), {
      params: Promise.resolve({ id: "hidden" }),
    });
    expect(forbidden.status).toBe(403);
    expect(JSON.stringify(await forbidden.json())).not.toContain("sensitive");
  });

  it("refreshes an expired session through the shared auth path", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(
        json({ access: "rotated", refresh: "rotated-refresh" }),
      )
      .mockResolvedValueOnce(
        json({ count: 0, next: null, previous: null, results: [] }),
      );
    vi.stubGlobal("fetch", backend);
    const response = await list(request("/api/invoices"));
    expect(response.status).toBe(200);
    expect(backend).toHaveBeenCalledTimes(3);
    expect(response.cookies.get(ACCESS_COOKIE)?.value).toBe("rotated");
  });

  it("streams private PDF headers and normalizes missing downloads", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(
        new Response("pdf", {
          status: 200,
          headers: {
            "Content-Type": "application/pdf",
            "Content-Disposition": "attachment; filename=INV-1.pdf",
          },
        }),
      )
      .mockResolvedValueOnce(json({ detail: "private path" }, 404));
    vi.stubGlobal("fetch", backend);
    const file = await download(request("/api/invoices/invoice-1/download"), {
      params: Promise.resolve({ id: "invoice-1" }),
    });
    expect(file.status).toBe(200);
    expect(file.headers.get("content-type")).toBe("application/pdf");
    expect(file.headers.get("cache-control")).toBe("private, no-store");
    const missing = await download(request("/api/invoices/missing/download"), {
      params: Promise.resolve({ id: "missing" }),
    });
    expect(missing.status).toBe(404);
    expect(JSON.stringify(await missing.json())).not.toContain("private path");
  });
});
