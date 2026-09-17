import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as payableAccounts } from "@/app/api/reference/vendor-payable-accounts/route";
import { GET as detail, PATCH as update } from "@/app/api/vendors/[id]/route";
import { GET as list, POST as create } from "@/app/api/vendors/route";
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
    ...init,
    headers: {
      Cookie: `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`,
      ...(init.headers ?? {}),
    },
  });
}

describe("Vendor BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("allowlists list filters and uses the dedicated backend path", async () => {
    const backend = vi.fn(async () =>
      json({ count: 0, next: null, previous: null, results: [] }),
    );
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await list(
          request("/api/vendors?search=hawk&is_active=false&company=foreign"),
        )
      ).status,
    ).toBe(200);
    const url = String((backend.mock.calls[0] as unknown as [URL])[0]);
    expect(url).toContain("finance/vendors/?search=hawk&is_active=false");
    expect(url).not.toContain("company");
  });

  it("requires same origin and strips server-owned and banking fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ id: "v" }, 201)),
    );
    expect(
      (
        await create(
          request("/api/vendors", {
            method: "POST",
            headers: { Origin: "https://evil.test" },
            body: "{}",
          }),
        )
      ).status,
    ).toBe(403);

    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toMatchObject({ code: "V-1", payable_account: "a" });
      expect(body.company).toBeUndefined();
      expect(body.bank_details_encrypted).toBeUndefined();
      expect(body.created_at).toBeUndefined();
      return json({ id: "v" }, 201);
    });
    vi.stubGlobal("fetch", backend);
    const response = await create(
      request("/api/vendors", {
        method: "POST",
        headers: { Origin: "http://admin.test", Host: "admin.test" },
        body: JSON.stringify({
          code: "V-1",
          payable_account: "a",
          company: "foreign",
          bank_details_encrypted: "secret",
          created_at: "attacker",
        }),
      }),
    );
    expect(response.status).toBe(201);
  });

  it("allowlists PATCH and preserves backend field validation", async () => {
    const backend = vi.fn(async (_url: unknown, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        name: "Updated",
        payable_account: "bad",
      });
      return json(
        { payable_account: ["The selected account is not eligible."] },
        400,
      );
    });
    vi.stubGlobal("fetch", backend);
    const response = await update(
      request("/api/vendors/v", {
        method: "PATCH",
        headers: { Origin: "http://admin.test", Host: "admin.test" },
        body: JSON.stringify({
          name: "Updated",
          payable_account: "bad",
          company: "foreign",
          bank_details_encrypted: "secret",
        }),
      }),
      { params: Promise.resolve({ id: "v" }) },
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({
      non_field_errors: [],
      payable_account: ["The selected account is not eligible."],
    });
  });

  it("preserves 401 after refresh cannot recover", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "hidden" }, 401)),
    );
    const response = await detail(request("/api/vendors/v"), {
      params: Promise.resolve({ id: "v" }),
    });
    expect(response.status).toBe(401);
    expect(JSON.stringify(await response.json())).not.toContain("hidden");
  });

  it("normalizes forbidden/not-found failures and routes the minimal reference", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "hidden" }, 403))
      .mockResolvedValueOnce(json({ detail: "hidden" }, 404))
      .mockResolvedValueOnce(json([{ id: "a", code: "2000", name: "AP" }]));
    vi.stubGlobal("fetch", backend);
    expect(
      (
        await detail(request("/api/vendors/v"), {
          params: Promise.resolve({ id: "v" }),
        })
      ).status,
    ).toBe(403);
    const missing = await detail(request("/api/vendors/missing"), {
      params: Promise.resolve({ id: "missing" }),
    });
    expect(missing.status).toBe(404);
    expect(JSON.stringify(await missing.json())).not.toContain("hidden");
    expect(
      (await payableAccounts(request("/api/reference/vendor-payable-accounts")))
        .status,
    ).toBe(200);
    expect(String((backend.mock.calls[2] as unknown as [URL])[0])).toContain(
      "finance/ap-reference/payable-accounts/",
    );
  });
});
