import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { visibleNavigationGroups } from "@/components/layout/sidebar";
import { AuthProvider } from "@/features/auth/auth-context";
import {
  LearningPage,
  LeavePage,
  RecruitmentPage,
} from "@/features/people-operations/pages";
import type { SessionData } from "@/lib/auth/types";
import type { ModuleId } from "@/lib/modules";

vi.mock("next/navigation", () => ({
  usePathname: () => "/recruitment",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

const company = {
  id: "11111111-1111-4111-8111-111111111111",
  code: "ACME",
  display_name: "Acme Company",
  legal_name: "Acme Company Limited",
  is_active: true,
};

function session(
  permissions: string[],
  modules: ModuleId[] = ["people", "recruitment", "leave", "learning"],
): SessionData {
  return {
    authenticated: true,
    user: {
      id: "user-1",
      email: "people@example.test",
      first_name: "People",
      last_name: "Admin",
      is_active: true,
      is_staff: false,
      is_superuser: false,
      last_login: null,
      date_joined: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    permissions,
    scopes: {
      is_superuser: false,
      accessible_company_ids: [company.id],
      accessible_region_ids: [],
      accessible_branch_ids: [],
      accessible_department_ids: [],
      accessible_operational_zone_ids: [],
      assignments: [],
    },
    platform_capabilities: {
      capabilities: [],
      can_access_platform_admin: false,
    },
    company_context: {
      companies: [company],
      selected_company: company,
      selection_required: false,
      effective_modules: modules,
      entitlement_revision: 1,
    },
  };
}

function withSession(node: React.ReactNode, permissions: string[]) {
  return render(
    <AuthProvider session={session(permissions)}>{node}</AuthProvider>,
  );
}

function response(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("Recruitment, Leave, and Learning workspaces", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => cleanup());

  it("gates all three People navigation items by module and exact RBAC", () => {
    const permissions = [
      "recruitment.view_manpowerrequisition",
      "leave.view_own_leave_request",
      "training.view_trainingcourse",
    ];
    const all = visibleNavigationGroups(
      permissions,
      ["people", "recruitment", "leave", "learning"],
      false,
    );
    expect(
      all
        .find((group) => group.id === "people")
        ?.items.map((item) => item.label),
    ).toEqual(["Recruitment", "Leave", "Learning & Qualifications"]);
    const leaveOnly = visibleNavigationGroups(
      permissions,
      ["people", "leave"],
      false,
    );
    expect(
      leaveOnly
        .find((group) => group.id === "people")
        ?.items.map((item) => item.label),
    ).toEqual(["Leave"]);
  });

  it("renders Recruitment lists with customer-facing Job Requisition terminology", async () => {
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("manpower-requisitions"))
        return response({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "req-1",
              reason: "New finance analyst",
              requested_headcount: 1,
              status: "DRAFT",
            },
          ],
        });
      if (url.includes("candidates"))
        return response({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "candidate-1",
              first_name: "Amina",
              last_name: "Khan",
              status: "ACTIVE",
            },
          ],
        });
      if (url.includes("applications"))
        return response({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "application-1",
              application_number: "APP-1",
              status: "SCREENING",
            },
          ],
        });
      return response({ count: 0, next: null, previous: null, results: [] });
    });
    withSession(<RecruitmentPage searchParams={{}} />, [
      "recruitment.view_manpowerrequisition",
      "recruitment.view_candidate",
      "recruitment.view_candidateapplication",
      "recruitment.add_manpowerrequisition",
    ]);
    expect(await screen.findByText("New finance analyst")).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Job Requisitions" }),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain("ManpowerRequisition");
  });

  it("keeps generic Leave and Learning independent from security readiness APIs", async () => {
    const requested: string[] = [];
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      requested.push(String(input));
      return response({ count: 0, next: null, previous: null, results: [] });
    });
    const leave = withSession(<LeavePage />, ["leave.view_own_leave_request"]);
    expect(
      await screen.findByRole("heading", { name: "Request Leave" }),
    ).toBeTruthy();
    leave.unmount();
    withSession(<LearningPage searchParams={{}} />, [
      "training.view_trainingcourse",
    ]);
    expect(
      await screen.findByRole("heading", { name: "Course catalog" }),
    ).toBeTruthy();
    await waitFor(() => expect(requested.length).toBeGreaterThan(3));
    expect(requested.some((url) => url.includes("readiness/guards"))).toBe(
      false,
    );
    expect(requested.some((url) => url.includes("deployment"))).toBe(false);
  });
});
