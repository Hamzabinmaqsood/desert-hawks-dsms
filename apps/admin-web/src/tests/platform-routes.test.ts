import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET, PUT } from "@/app/api/platform/[...segments]/route";
import { backendErrorBody } from "@/lib/api/backend-error";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function request(path: string, init: RequestInit = {}, sameOrigin = true) {
  const headers = new Headers(init.headers);
  headers.set("Cookie", `${ACCESS_COOKIE}=access; ${REFRESH_COOKIE}=refresh`);
  headers.set("Host", "admin.test");
  headers.set("Origin", sameOrigin ? "http://admin.test" : "http://evil.test");
  const { signal, ...rest } = init;
  return new NextRequest(`http://admin.test${path}`, {
    ...rest,
    headers,
    signal: signal ?? undefined,
  });
}

const context = (segments: string[]) => ({
  params: Promise.resolve({ segments }),
});

describe("platform administration BFF", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("forwards only allowlisted platform reads through the authenticated session", async () => {
    const backend = vi.fn(async () => json([{ id: "people" }]));
    vi.stubGlobal("fetch", backend);
    const response = await GET(
      request("/api/platform/modules"),
      context(["modules"]),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual([{ id: "people" }]);
    const [backendUrl, backendInit] = backend.mock.calls[0] as unknown as [
      RequestInfo | URL,
      RequestInit,
    ];
    expect(String(backendUrl)).toMatch(/platform\/modules\/$/);
    expect(new Headers(backendInit.headers).get("Authorization")).toBe(
      "Bearer access",
    );
  });

  it("rejects non-allowlisted paths before contacting the backend", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    const response = await GET(
      request("/api/platform/private-data"),
      context(["private-data"]),
    );
    expect(response.status).toBe(404);
    expect(backend).not.toHaveBeenCalled();
  });

  it("rejects cross-origin commercial mutations", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    const response = await PUT(
      request(
        "/api/platform/subscriptions/92000000-0000-0000-0000-000000000001/overrides",
        { method: "PUT", body: JSON.stringify({ enabled_module_ids: [] }) },
        false,
      ),
      context([
        "subscriptions",
        "92000000-0000-0000-0000-000000000001",
        "overrides",
      ]),
    );
    expect(response.status).toBe(403);
    expect(backend).not.toHaveBeenCalled();
  });

  it("forwards one normalized batch override request and returns server authority", async () => {
    const authoritative = {
      subscription_id: "92000000-0000-0000-0000-000000000001",
      entitlement_revision: 5,
      effective_module_ids: ["finance_core"],
    };
    const backend = vi.fn(async () => json(authoritative));
    vi.stubGlobal("fetch", backend);
    const payload = {
      enabled_module_ids: [],
      disabled_module_ids: ["billing_receivables"],
      reason: "Customer request",
    };
    const response = await PUT(
      request(
        "/api/platform/subscriptions/92000000-0000-0000-0000-000000000001/overrides",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      ),
      context([
        "subscriptions",
        "92000000-0000-0000-0000-000000000001",
        "overrides",
      ]),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(authoritative);
    const [, backendInit] = backend.mock.calls[0] as unknown as [
      RequestInfo | URL,
      RequestInit,
    ];
    expect(JSON.parse(String(backendInit.body))).toEqual(payload);
  });

  it("normalizes backend module denials without exposing entitlement internals", () => {
    expect(
      backendErrorBody(
        {
          status: 403,
          data: {
            code: "module_not_enabled",
            detail: "internal module enforcement detail",
            required_modules: ["billing_receivables"],
          },
        },
        "Request failed.",
      ),
    ).toEqual({
      code: ["module_not_enabled"],
      non_field_errors: ["This module is not enabled for this Company."],
    });
  });
});
