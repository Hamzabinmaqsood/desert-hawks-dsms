import { describe, expect, it } from "vitest";

import { can, canAll, canAny } from "@/lib/auth/permissions";

describe("permission helpers", () => {
  const permissions = [
    "billing.view_clientinvoice",
    "finance.manage_procurement",
  ];

  it("supports single, any, all, and superuser checks", () => {
    expect(can(permissions, "billing.view_clientinvoice")).toBe(true);
    expect(
      canAny(permissions, [
        "finance.manage_payroll",
        "finance.manage_procurement",
      ]),
    ).toBe(true);
    expect(
      canAll(permissions, [
        "billing.view_clientinvoice",
        "finance.manage_procurement",
      ]),
    ).toBe(true);
    expect(can(permissions, "finance.manage_payroll")).toBe(false);
    expect(can([], "finance.manage_payroll", true)).toBe(true);
  });
});
