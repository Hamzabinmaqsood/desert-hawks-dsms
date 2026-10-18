"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandLogo } from "@/components/brand/brand-logo";
import { canAny } from "@/lib/auth/permissions";
import type { CompanyBranding } from "@/lib/auth/types";
import { hasModule, type ModuleId } from "@/lib/modules";

interface NavigationItem {
  label: string;
  href: string;
  permissions?: string[];
  moduleId?: ModuleId;
  platformOnly?: boolean;
}

const navigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Branding", href: "/settings/branding" },
  { label: "Business settings", href: "/settings/company" },
  {
    label: "Platform administration",
    href: "/platform/companies",
    platformOnly: true,
  },
  {
    label: "Invoices",
    href: "/invoices",
    permissions: ["billing.view_clientinvoice"],
    moduleId: "billing_receivables",
  },
  {
    label: "Receipts",
    href: "/receipts",
    permissions: ["billing.view_clientreceipt"],
    moduleId: "billing_receivables",
  },
  {
    label: "Vendors",
    href: "/vendors",
    permissions: ["finance.view_vendor"],
    moduleId: "procurement_payables",
  },
  {
    label: "Vendor Bills",
    href: "/vendor-bills",
    permissions: ["finance.view_vendorbill"],
    moduleId: "procurement_payables",
  },
  {
    label: "Vendor Payments",
    href: "/vendor-payments",
    permissions: ["finance.view_paymentvoucher"],
    moduleId: "procurement_payables",
  },
];

export function isNavigationItemVisible(
  item: NavigationItem,
  permissions: readonly string[],
  effectiveModules: readonly ModuleId[],
  isSuperuser: boolean,
  canAccessPlatformAdmin: boolean,
) {
  if (item.platformOnly && !canAccessPlatformAdmin) return false;
  if (item.moduleId && !hasModule(effectiveModules, item.moduleId))
    return false;
  return (
    !item.permissions || canAny(permissions, item.permissions, isSuperuser)
  );
}

export function Sidebar({
  permissions,
  effectiveModules,
  isSuperuser,
  canAccessPlatformAdmin,
  branding,
}: {
  permissions: string[];
  effectiveModules: ModuleId[];
  isSuperuser: boolean;
  canAccessPlatformAdmin: boolean;
  branding: CompanyBranding;
}) {
  const pathname = usePathname();
  const visible = navigation.filter((item) =>
    isNavigationItemVisible(
      item,
      permissions,
      effectiveModules,
      isSuperuser,
      canAccessPlatformAdmin,
    ),
  );
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="brand">
        <BrandLogo className="brand-logo-shell" />
        <span>
          {branding.display_name}
          <br />
          <small>{branding.tagline}</small>
        </span>
      </div>
      <nav>
        <ul>
          {visible.map((item) => (
            <li key={item.href}>
              <Link
                aria-current={
                  pathname.startsWith(item.href) ? "page" : undefined
                }
                href={item.href}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}

export { navigation };
