"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandLogo } from "@/components/brand/brand-logo";
import { canAny } from "@/lib/auth/permissions";

interface NavigationItem {
  label: string;
  href: string;
  permissions?: string[];
}

const navigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard" },
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
];

export function Sidebar({
  permissions,
  isSuperuser,
}: {
  permissions: string[];
  isSuperuser: boolean;
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
          Desert Hawks
          <br />
          <small>Digital Transformation System</small>
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
