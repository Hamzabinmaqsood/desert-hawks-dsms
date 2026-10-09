import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import {
  GET as getBranding,
  PATCH as updateBranding,
} from "@/app/api/auth/company-branding/route";
import { PUT as switchCompany } from "@/app/api/auth/company-context/route";
import { GET as session } from "@/app/api/auth/session/route";
import {
  ACCESS_COOKIE,
  COMPANY_CONTEXT_COOKIE,
  REFRESH_COOKIE,
} from "@/lib/auth/cookies";
import { proxy } from "@/proxy";

const user = {
  id: "user-1",
  email: "employee@example.test",
  first_name: "Test",
  last_name: "Employee",
  is_active: true,
  is_staff: false,
  is_superuser: false,
  last_login: null,
  date_joined: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const scopes = {
  is_superuser: false,
  accessible_company_ids: [],
  accessible_region_ids: [],
  accessible_branch_ids: [],
  accessible_department_ids: [],
  accessible_operational_zone_ids: [],
  assignments: [],
};

const companyA = {
  id: "00000000-0000-0000-0000-00000000000a",
  code: "A",
  display_name: "Company A",
  legal_name: "Company A Limited",
  is_active: true,
};

const companyB = {
  id: "00000000-0000-0000-0000-00000000000b",
  code: "B",
  display_name: "Company B",
  legal_name: "Company B Limited",
  is_active: true,
};

const companyContext = {
  user,
  companies: [companyA],
  selected_company: companyA,
  selection_required: false,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function request(
  path: string,
  init: RequestInit = {},
  cookies?: Record<string, string>,
) {
  const headers = new Headers(init.headers);
  headers.set("Origin", "http://admin.test");
  headers.set("Host", "admin.test");
  if (cookies)
    headers.set(
      "Cookie",
      Object.entries(cookies)
        .map(([key, value]) => `${key}=${value}`)
        .join("; "),
    );
  const { signal, ...rest } = init;
  return new NextRequest(`http://admin.test${path}`, {
    ...rest,
    headers,
    signal: signal ?? undefined,
  });
}

describe("authentication BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("BACKEND_API_URL", "http://backend.test/api/v1");
  });

  it("serves public brand assets without an authenticated session lookup", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    const response = await proxy(request("/brand/desert-hawks-logo.png"));
    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(backend).not.toHaveBeenCalled();
  });

  it("logs in with secure server-owned cookies and returns no tokens", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ access: "access-token", refresh: "refresh-token" }),
      ),
    );
    const response = await login(
      request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "employee@example.test",
          password: "runtime-value",
        }),
      }),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ authenticated: true });
    expect(response.cookies.get(ACCESS_COOKIE)?.httpOnly).toBe(true);
    expect(response.cookies.get(REFRESH_COOKIE)?.httpOnly).toBe(true);
    expect(response.cookies.get(REFRESH_COOKIE)?.sameSite).toBe("lax");
    expect(response.cookies.get(REFRESH_COOKIE)?.path).toBe("/");
    expect(response.cookies.get(COMPANY_CONTEXT_COOKIE)?.maxAge).toBe(0);
  });

  it("normalizes invalid credentials and backend outages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "backend detail" }, 401)),
    );
    const invalid = await login(
      request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "employee@example.test",
          password: "runtime-value",
        }),
      }),
    );
    expect(invalid.status).toBe(401);
    expect(await invalid.json()).toEqual({
      message: "Email or password is incorrect.",
      fieldErrors: {},
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );
    const unavailable = await login(
      request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "employee@example.test",
          password: "runtime-value",
        }),
      }),
    );
    expect(unavailable.status).toBe(503);
    expect(JSON.stringify(await unavailable.json())).not.toContain("offline");
  });

  it("loads identity, permissions, and scopes with a valid access token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/auth/company-context/")) return json(companyContext);
        if (url.endsWith("/auth/me/permissions/"))
          return json({ permissions: ["billing.view_clientinvoice"] });
        return json(scopes);
      }),
    );
    const response = await session(
      request(
        "/api/auth/session",
        {},
        { [ACCESS_COOKIE]: "access", [REFRESH_COOKIE]: "refresh" },
      ),
    );
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.user.email).toBe(user.email);
    expect(body.permissions).toEqual(["billing.view_clientinvoice"]);
    expect(body.scopes).toEqual(scopes);
    expect(body.company_context.selected_company).toEqual(companyA);
  });

  it("refreshes exactly once, rotates cookies, and retries identity once", async () => {
    let refreshCalls = 0;
    let identityCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/auth/refresh/")) {
          refreshCalls += 1;
          return json({ access: "rotated-access", refresh: "rotated-refresh" });
        }
        identityCalls += 1;
        if (identityCalls <= 3) return json({ detail: "expired" }, 401);
        if (url.endsWith("/auth/company-context/")) return json(companyContext);
        if (url.endsWith("/auth/me/permissions/"))
          return json({ permissions: [] });
        return json(scopes);
      }),
    );
    const response = await session(
      request(
        "/api/auth/session",
        {},
        { [ACCESS_COOKIE]: "expired", [REFRESH_COOKIE]: "refresh" },
      ),
    );
    expect(response.status).toBe(200);
    expect(refreshCalls).toBe(1);
    expect(identityCalls).toBe(6);
    expect(response.cookies.get(ACCESS_COOKIE)?.value).toBe("rotated-access");
    expect(response.cookies.get(REFRESH_COOKIE)?.value).toBe("rotated-refresh");
  });

  it("clears both cookies when refresh fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) =>
        String(input).endsWith("/auth/refresh/")
          ? json({}, 401)
          : json({}, 401),
      ),
    );
    const response = await session(
      request(
        "/api/auth/session",
        {},
        { [ACCESS_COOKIE]: "expired", [REFRESH_COOKIE]: "invalid" },
      ),
    );
    expect(response.status).toBe(401);
    expect(response.cookies.get(ACCESS_COOKIE)?.maxAge).toBe(0);
    expect(response.cookies.get(REFRESH_COOKIE)?.maxAge).toBe(0);
    expect(response.cookies.get(COMPANY_CONTEXT_COOKIE)?.maxAge).toBe(0);
  });

  it("calls backend logout and always clears local cookies", async () => {
    const backend = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return new Response(null, { status: 204 });
      },
    );
    vi.stubGlobal("fetch", backend);
    const response = await logout(
      request(
        "/api/auth/logout",
        { method: "POST" },
        {
          [ACCESS_COOKIE]: "access",
          [REFRESH_COOKIE]: "refresh",
          [COMPANY_CONTEXT_COOKIE]: "context123",
        },
      ),
    );
    expect(response.status).toBe(200);
    expect(backend).toHaveBeenCalledOnce();
    expect(response.cookies.get(ACCESS_COOKIE)?.maxAge).toBe(0);
    expect(response.cookies.get(REFRESH_COOKIE)?.maxAge).toBe(0);
    expect(response.cookies.get(COMPANY_CONTEXT_COOKIE)?.maxAge).toBe(0);
    const requestInit = backend.mock.calls[0]?.[1] as RequestInit;
    expect(requestInit.headers).toMatchObject({
      Cookie: "sessionid=context123",
    });
  });

  it("refreshes an expired access token before revoking the rotated refresh token", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "expired" }, 401))
      .mockResolvedValueOnce(
        json({ access: "rotated-access", refresh: "rotated-refresh" }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", backend);
    const response = await logout(
      request(
        "/api/auth/logout",
        { method: "POST" },
        { [ACCESS_COOKIE]: "expired", [REFRESH_COOKIE]: "old-refresh" },
      ),
    );
    expect(response.status).toBe(200);
    expect(backend).toHaveBeenCalledTimes(3);
    const finalRequest = backend.mock.calls[2]?.[1] as RequestInit;
    expect(finalRequest.headers).toMatchObject({
      Authorization: "Bearer rotated-access",
    });
    expect(finalRequest.body).toBe(
      JSON.stringify({ refresh: "rotated-refresh" }),
    );
    expect(response.cookies.get(REFRESH_COOKIE)?.maxAge).toBe(0);
  });

  it("switches Company through the backend and stores only its opaque session key", async () => {
    const backend = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return new Response(
          JSON.stringify({
            user,
            companies: [companyA, companyB],
            selected_company: companyB,
            selection_required: false,
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Set-Cookie":
                "sessionid=newcontext; Path=/; HttpOnly; SameSite=Lax",
            },
          },
        );
      },
    );
    vi.stubGlobal("fetch", backend);
    const response = await switchCompany(
      request(
        "/api/auth/company-context",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_id: companyB.id }),
        },
        {
          [ACCESS_COOKIE]: "access",
          [REFRESH_COOKIE]: "refresh",
          [COMPANY_CONTEXT_COOKIE]: "oldcontext",
        },
      ),
    );
    expect(response.status).toBe(200);
    expect((await response.json()).selected_company).toEqual(companyB);
    expect(response.cookies.get(COMPANY_CONTEXT_COOKIE)?.value).toBe(
      "newcontext",
    );
    expect(response.cookies.get(COMPANY_CONTEXT_COOKIE)?.httpOnly).toBe(true);
    const backendInit = backend.mock.calls[0]?.[1] as RequestInit;
    const backendHeaders = new Headers(backendInit.headers);
    expect(backendInit.method).toBe("PUT");
    expect(backendHeaders.get("Authorization")).toBe("Bearer access");
    expect(backendHeaders.get("Cookie")).toBe("sessionid=oldcontext");
    expect(backendInit.body).toBe(JSON.stringify({ company_id: companyB.id }));
  });

  it("normalizes inaccessible Company switch failures without storing context", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "Not found." }, 404)),
    );
    const response = await switchCompany(
      request(
        "/api/auth/company-context",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_id: companyB.id }),
        },
        { [ACCESS_COOKIE]: "access", [REFRESH_COOKIE]: "refresh" },
      ),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({
      message: "Company is unavailable.",
    });
    expect(response.cookies.get(COMPANY_CONTEXT_COOKIE)).toBeUndefined();
  });

  it("reads branding from server-selected context without a Company UUID", async () => {
    const branding = {
      display_name: "Alpha Shield",
      tagline: "Always ready",
      primary_color: "#123456",
      accent_color: "#ABCDEF",
      can_manage: false,
    };
    const backend = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return json(branding);
      },
    );
    vi.stubGlobal("fetch", backend);
    const response = await getBranding(
      request(
        "/api/auth/company-branding",
        {},
        { [ACCESS_COOKIE]: "access", [REFRESH_COOKIE]: "refresh" },
      ),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(branding);
    expect(String(backend.mock.calls[0]?.[0])).toMatch(
      /auth\/company-branding\/$/,
    );
    expect(String(backend.mock.calls[0]?.[0])).not.toContain("company_id");
  });

  it("normalizes safe branding updates and rejects browser Company authority", async () => {
    const backend = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return json({
          display_name: "Alpha Shield",
          tagline: "Always ready",
          primary_color: "#A1B2C3",
          accent_color: "#D4E5F6",
          can_manage: true,
        });
      },
    );
    vi.stubGlobal("fetch", backend);
    const response = await updateBranding(
      request(
        "/api/auth/company-branding",
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: " Alpha Shield ",
            tagline: " Always ready ",
            primary_color: "#a1b2c3",
            accent_color: "#d4e5f6",
          }),
        },
        { [ACCESS_COOKIE]: "access", [REFRESH_COOKIE]: "refresh" },
      ),
    );
    expect(response.status).toBe(200);
    const init = backend.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      display_name: "Alpha Shield",
      tagline: "Always ready",
      primary_color: "#A1B2C3",
      accent_color: "#D4E5F6",
    });

    const unsupported = await updateBranding(
      request("/api/auth/company-branding", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: companyB.id }),
      }),
    );
    expect(unsupported.status).toBe(400);
    expect(backend).toHaveBeenCalledOnce();
  });

  it("rejects CSS injection before forwarding branding updates", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);
    const response = await updateBranding(
      request("/api/auth/company-branding", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ primary_color: "url(https://attacker.test)" }),
      }),
    );
    expect(response.status).toBe(400);
    expect(backend).not.toHaveBeenCalled();
  });
});
