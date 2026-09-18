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
  VendorPaymentCreatePage,
  VendorPaymentDetailPage,
  VendorPaymentListPage,
} from "@/features/vendor-payments/pages";
import type { SessionData } from "@/lib/auth/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/vendor-payments",
}));

const session: SessionData = {
  authenticated: true,
  user: {
    id: "maker",
    email: "maker@test",
    first_name: "Payment",
    last_name: "Maker",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    last_login: null,
    date_joined: "",
    created_at: "",
    updated_at: "",
  },
  permissions: [
    "finance.view_paymentvoucher",
    "finance.add_paymentvoucher",
    "finance.change_paymentvoucher",
    "finance.approve_finance",
    "finance.post_journal",
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
const payment = {
  id: "p",
  vendor_bill: "b",
  bill_number: "B-1",
  vendor_name: "Desert Supply",
  voucher_number: "PV-1",
  payment_date: "2026-09-18",
  amount: "70.00",
  status: "DRAFT",
  payment_status: "PENDING",
  payment_reference: "",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const withAuth = (node: React.ReactNode) =>
  render(<AuthProvider session={session}>{node}</AuthProvider>);

describe("Vendor Payment screens", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ count: 1, next: null, previous: null, results: [payment] }),
      ),
    );
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the payment register and create action", async () => {
    withAuth(<VendorPaymentListPage />);
    expect(await screen.findByText("PV-1")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "New Vendor Payment" }),
    ).toBeTruthy();
    expect(screen.getByText("70.00")).toBeTruthy();
  });

  it("creates a draft from an eligible Bill with server errors preserved", async () => {
    const backend = vi.fn(
      async (url: RequestInfo | URL, init?: RequestInit) => {
        if (String(url).includes("payable-bills"))
          return json([
            {
              id: "b",
              bill_number: "B-1",
              vendor_invoice_number: "S-1",
              vendor_name: "Desert Supply",
              total_amount: "100.00",
              paid_amount: "0.00",
              outstanding_amount: "100.00",
              status: "POSTED",
            },
          ]);
        if (init?.method === "POST") return json(payment, 201);
        return json({});
      },
    );
    vi.stubGlobal("fetch", backend);
    withAuth(<VendorPaymentCreatePage />);
    await screen.findByRole("option", { name: /B-1/ });
    fireEvent.change(screen.getByLabelText("Vendor Bill"), {
      target: { value: "b" },
    });
    fireEvent.change(screen.getByLabelText("Voucher number"), {
      target: { value: "PV-1" },
    });
    fireEvent.change(screen.getByLabelText("Payment date"), {
      target: { value: "2026-09-18" },
    });
    fireEvent.change(screen.getByLabelText("Amount"), {
      target: { value: "70.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/vendor-payments/p"),
    );
  });

  it("submits and refetches authoritative Voucher state", async () => {
    let submitted = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        if (String(url).endsWith("/submit")) {
          submitted = true;
          return json({ ...payment, status: "SUBMITTED" });
        }
        return json(submitted ? { ...payment, status: "SUBMITTED" } : payment);
      }),
    );
    withAuth(<VendorPaymentDetailPage id="p" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Submit for approval" }),
    );
    await waitFor(() => expect(screen.getByText("SUBMITTED")).toBeTruthy());
  });
});
