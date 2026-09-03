import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as approve } from "@/app/api/invoices/[id]/approve/route";
import { GET as download } from "@/app/api/invoices/[id]/download/route";
import { POST as issue } from "@/app/api/invoices/[id]/issue/route";
import { POST as submit } from "@/app/api/invoices/[id]/submit/route";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function request(path: string, origin = "http://admin.test") {
  const headers = new Headers();
  headers.set("Origin", origin);
  headers.set("Host", "admin.test");
  headers.set("Cookie", `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`);
  return new NextRequest(`http://admin.test${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify({ status: "ISSUED", approved_by: "attacker" }),
  });
}

const params = (id: string) => ({ params: Promise.resolve({ id }) });

const ACTIONS = [
  { name: "submit", handler: submit, path: "submit" },
  { name: "approve", handler: approve, path: "approve" },
  { name: "issue", handler: issue, path: "issue" },
] as const;

describe("Invoice workflow BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it.each(ACTIONS)(
    "forwards $name to the backend without any browser-supplied payload",
    async ({ handler, path }) => {
      const backend = vi.fn(async () =>
        json({ id: "invoice-1", status: "UNDER_REVIEW" }),
      );
      vi.stubGlobal("fetch", backend);

      const response = await handler(
        request(`/api/invoices/invoice-1/${path}`),
        params("invoice-1"),
      );

      expect(response.status).toBe(200);
      const [url, init] = backend.mock.calls[0] as unknown as [
        URL | string,
        RequestInit,
      ];
      expect(String(url)).toBe(
        `http://backend.test/api/v1/billing/invoices/invoice-1/${path}/`,
      );
      expect(init.method).toBe("POST");
      // The browser body carried `status` and `approved_by`; neither may reach Django.
      expect(init.body).toBe("{}");
    },
  );

  it.each(ACTIONS)(
    "rejects cross-origin $name without calling the backend",
    async ({ handler, path }) => {
      const backend = vi.fn();
      vi.stubGlobal("fetch", backend);

      const response = await handler(
        request(`/api/invoices/invoice-1/${path}`, "http://attacker.test"),
        params("invoice-1"),
      );

      expect(response.status).toBe(403);
      expect(backend).not.toHaveBeenCalled();
    },
  );

  it("preserves a backend business error from approve as a readable message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ detail: ["Maker/checker policy prevents self-approval."] }, 400),
      ),
    );

    const response = await approve(
      request("/api/invoices/invoice-1/approve"),
      params("invoice-1"),
    );

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({
      non_field_errors: ["Maker/checker policy prevents self-approval."],
    });
  });

  it("preserves a backend state error from issue", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ detail: ["Only approved invoices can be issued."] }, 400),
      ),
    );

    const response = await issue(
      request("/api/invoices/invoice-1/issue"),
      params("invoice-1"),
    );

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({
      non_field_errors: ["Only approved invoices can be issued."],
    });
  });

  it("normalizes a 403 from submit without leaking the backend body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "Internal RBAC trace" }, 403)),
    );

    const response = await submit(
      request("/api/invoices/invoice-1/submit"),
      params("invoice-1"),
    );

    expect(response.status).toBe(403);
    const body = (await response.json()) as Record<string, string[]>;
    expect(body.non_field_errors).toEqual([
      "You do not have permission to perform this action.",
    ]);
  });

  it("normalizes a 404 from approve", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({}, 404)),
    );

    const response = await approve(
      request("/api/invoices/missing/approve"),
      params("missing"),
    );

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toMatchObject({
      non_field_errors: ["The requested invoice could not be found."],
    });
  });

  it("returns a safe failure when the backend errors on issue", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    );

    const response = await issue(
      request("/api/invoices/invoice-1/issue"),
      params("invoice-1"),
    );

    expect(response.status).toBe(500);
    const body = (await response.json()) as Record<string, string[]>;
    expect(body.non_field_errors).toEqual(["The invoice could not be issued."]);
    expect(JSON.stringify(body)).not.toContain("boom");
  });

  it("streams the issued PDF through the same-origin download route", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("%PDF-1.4 fake", {
            status: 200,
            headers: {
              "Content-Type": "application/pdf",
              "Content-Disposition": 'attachment; filename="invoice-INV-1.pdf"',
            },
          }),
      ),
    );

    const headers = new Headers();
    headers.set("Host", "admin.test");
    headers.set("Cookie", `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`);
    const response = await download(
      new NextRequest("http://admin.test/api/invoices/invoice-1/download", {
        headers,
      }),
      params("invoice-1"),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(response.headers.get("content-disposition")).toBe(
      'attachment; filename="invoice-INV-1.pdf"',
    );
    expect(response.headers.get("cache-control")).toBe("private, no-store");
  });

  it.each([
    [403, "You do not have permission to download this invoice."],
    [404, "Invoice PDF not found."],
  ])(
    "handles a %i from the private download route",
    async (status, message) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => json({ detail: "internal" }, status)),
      );

      const headers = new Headers();
      headers.set("Host", "admin.test");
      headers.set(
        "Cookie",
        `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`,
      );
      const response = await download(
        new NextRequest("http://admin.test/api/invoices/invoice-1/download", {
          headers,
        }),
        params("invoice-1"),
      );

      expect(response.status).toBe(status);
      await expect(response.json()).resolves.toEqual({ message });
    },
  );
});
