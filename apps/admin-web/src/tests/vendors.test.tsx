import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import {
  VendorCreatePage,
  VendorDetailPage,
  VendorEditPage,
  VendorListPage,
} from "@/features/vendors/pages";
import type { SessionData } from "@/lib/auth/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/vendors",
}));

const session: SessionData = {
  authenticated: true,
  user: {
    id: "u",
    email: "vendor@test",
    first_name: "Vendor",
    last_name: "User",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    last_login: null,
    date_joined: "",
    created_at: "",
    updated_at: "",
  },
  permissions: [
    "finance.view_vendor",
    "finance.add_vendor",
    "finance.change_vendor",
  ],
  scopes: {
    is_superuser: false,
    accessible_company_ids: ["c"],
    accessible_region_ids: [],
    accessible_branch_ids: [],
    accessible_department_ids: [],
    accessible_operational_zone_ids: [],
    assignments: [],
  },
};

const vendor = {
  id: "v",
  code: "V-001",
  name: "Desert Supplier",
  tax_number: "NTN-1",
  email: "vendor@example.test",
  phone: "03000000000",
  payment_terms_days: 30,
  payable_account: "a",
  payable_account_code: "2000",
  payable_account_name: "Trade Payables",
  is_active: false,
  created_at: "",
  updated_at: "",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function withAuth(node: React.ReactNode, permissions = session.permissions) {
  return render(
    <AuthProvider session={{ ...session, permissions }}>{node}</AuthProvider>,
  );
}

describe("Vendor screens", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    push.mockReset();
  });
  afterEach(() => cleanup());

  it("renders list data, inactive status, and permission-aware controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ count: 1, next: null, previous: null, results: [vendor] }),
      ),
    );
    withAuth(
      <VendorListPage
        searchParams={{ search: "Desert", is_active: "false" }}
      />,
    );
    expect(await screen.findByRole("link", { name: "V-001" })).toBeTruthy();
    expect(screen.getAllByText("Inactive")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "New Vendor" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Edit" })).toBeTruthy();
    expect((screen.getByLabelText("Search") as HTMLInputElement).value).toBe(
      "Desert",
    );
    expect((screen.getByLabelText("Status") as HTMLSelectElement).value).toBe(
      "false",
    );
  });

  it("creates with the least-privilege payable-account selector", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(
        json([{ id: "a", code: "2000", name: "Trade Payables" }]),
      )
      .mockResolvedValueOnce(json({ ...vendor, is_active: true }, 201));
    vi.stubGlobal("fetch", backend);
    withAuth(<VendorCreatePage />);
    await screen.findByRole("option", { name: /2000.*Trade Payables/ });
    fireEvent.change(screen.getByLabelText("Code"), {
      target: { value: "V-001" },
    });
    fireEvent.change(screen.getByLabelText("Vendor name"), {
      target: { value: "Desert Supplier" },
    });
    fireEvent.change(screen.getByLabelText("Payable account"), {
      target: { value: "a" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Vendor" }));
    await waitFor(() => expect(backend).toHaveBeenCalledTimes(2));
    const body = JSON.parse(
      String(
        (backend.mock.calls[1] as unknown as [unknown, RequestInit])[1].body,
      ),
    );
    expect(body).toMatchObject({ code: "V-001", payable_account: "a" });
    expect(body.company).toBeUndefined();
    expect(body.bank_details_encrypted).toBeUndefined();
    expect(push).toHaveBeenCalledWith("/vendors/v");
  });

  it("edits safe fields and preserves payable-account field errors", async () => {
    const backend = vi
      .fn()
      .mockResolvedValueOnce(json(vendor))
      .mockResolvedValueOnce(
        json([{ id: "a", code: "2000", name: "Trade Payables" }]),
      )
      .mockResolvedValueOnce(
        json(
          { payable_account: ["Select the configured payable account."] },
          400,
        ),
      );
    vi.stubGlobal("fetch", backend);
    withAuth(<VendorEditPage id="v" />);
    await screen.findByRole("heading", { name: "Edit V-001" });
    fireEvent.change(screen.getByLabelText("Vendor name"), {
      target: { value: "Updated Supplier" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Vendor" }));
    expect(
      await screen.findByText("Select the configured payable account."),
    ).toBeTruthy();
  });

  it("normalizes missing detail and blocks controls without permissions", async () => {
    const backend = vi.fn(async () => json({ detail: "hidden" }, 404));
    vi.stubGlobal("fetch", backend);
    withAuth(<VendorDetailPage id="missing" />);
    expect(await screen.findByText("Vendor not found.")).toBeTruthy();
    cleanup();
    withAuth(<VendorListPage searchParams={{}} />, []);
    expect(screen.getByRole("alert").textContent).toContain("permission");
  });
});
