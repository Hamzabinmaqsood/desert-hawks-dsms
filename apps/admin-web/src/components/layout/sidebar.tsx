"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandLogo } from "@/components/brand/brand-logo";
import { canAny } from "@/lib/auth/permissions";
import type { CompanyBranding } from "@/lib/auth/types";

interface NavigationItem {
  label: string;
  href: string;
  permissions?: string[];
}

const navigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Branding", href: "/settings/branding" },
  {
    label: "Invoices",
    href: "/invoices",
    permissions: ["billing.view_clientinvoice"],
  },
  {
    label: "Receipts",
    href: "/receipts",
    permissions: ["billing.view_clientreceipt"],
  },
  {
    label: "Vendors",
    href: "/vendors",
    permissions: ["finance.view_vendor"],
  },
  {
    label: "Vendor Bills",
    href: "/vendor-bills",
    permissions: ["finance.view_vendorbill"],
  },
  {
    label: "Vendor Payments",
    href: "/vendor-payments",
    permissions: ["finance.view_paymentvoucher"],
  },
];

export function Sidebar({
  permissions,
  isSuperuser,
  branding,
}: {
  permissions: string[];
  isSuperuser: boolean;
  branding: CompanyBranding;
}) {
  const pathname = usePathname();
  const visible = navigation.filter(
    (item) =>
      !item.permissions || canAny(permissions, item.permissions, isSuperuser),
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
