import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { AppShell } from "@/components/layout/app-shell";
import LoginPage from "@/app/(auth)/login/page";
import type { SessionData } from "@/lib/auth/types";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  usePathname: () => "/dashboard",
}));

const session: SessionData = {
  authenticated: true,
  user: {
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
  },
  permissions: [],
  scopes: {
    is_superuser: false,
    accessible_company_ids: [],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
};

describe("authentication components", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("renders the official logo and product identity on the login page", () => {
    render(<LoginPage />);
    const logo = screen.getByRole("img", {
      name: "Desert Hawks official logo",
    });
    expect(
      new URL(logo.getAttribute("src")!, "http://admin.test").searchParams.get(
        "url",
      ),
    ).toBe("/brand/desert-hawks-logo.png");
    expect(screen.getByText("Digital Transformation System")).toBeTruthy();
  });

  it("renders an accessible login form and disables it while submitting", async () => {
    let finish: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    render(<LoginForm />);
    expect(screen.getByLabelText("Work email")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Work email"), {
      target: { value: "employee@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Sign in" }).closest("form")!,
    );
    expect(
      (screen.getByRole("button", { name: "Signing in…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await act(async () =>
      finish?.(
        new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    expect(replace).toHaveBeenCalledWith("/dashboard");
  });

  it("shows a stable authentication error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ message: "Email or password is incorrect." }),
            { status: 401, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Work email"), {
      target: { value: "employee@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    await act(async () =>
      fireEvent.submit(
        screen.getByRole("button", { name: "Sign in" }).closest("form")!,
      ),
    );
    expect(screen.getByRole("alert").textContent).toContain("incorrect");
  });

  it("renders the authenticated shell, user, and permitted navigation", () => {
    render(
      <AppShell session={session}>
        <p>Protected content</p>
      </AppShell>,
    );
    expect(screen.getByText("Test Employee")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(screen.getByText("Protected content")).toBeTruthy();
    const logo = screen.getByRole("img", {
      name: "Desert Hawks official logo",
    });
    expect(
      new URL(logo.getAttribute("src")!, "http://admin.test").searchParams.get(
        "url",
      ),
    ).toBe("/brand/desert-hawks-logo.png");
    expect(screen.queryByRole("link", { name: "Invoices" })).toBeNull();
  });

  it("shows Invoice navigation only with Invoice view permission", () => {
    render(
      <AppShell
        session={{ ...session, permissions: ["billing.view_clientinvoice"] }}
      >
        <p>Protected content</p>
      </AppShell>,
    );
    expect(
      screen.getByRole("link", { name: "Invoices" }).getAttribute("href"),
    ).toBe("/invoices");
  });
});
