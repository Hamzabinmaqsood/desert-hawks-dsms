"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { BrandLogo } from "@/components/brand/brand-logo";
import { canAny } from "@/lib/auth/permissions";
import type { CompanyBranding } from "@/lib/auth/types";
import { hasModule, type ModuleId } from "@/lib/modules";

export interface NavigationItem {
  label: string;
  href: string;
  permissions?: string[];
  moduleId?: ModuleId;
  order: number;
}

export interface NavigationGroup {
  id: string;
  label: string;
  order: number;
  items: NavigationItem[];
}

export const navigationGroups: NavigationGroup[] = [
  {
    id: "home",
    label: "Home",
    order: 10,
    items: [{ label: "Dashboard", href: "/dashboard", order: 10 }],
  },
  {
    id: "finance",
    label: "Finance",
    order: 20,
    items: [
      {
        label: "Invoices",
        href: "/invoices",
        permissions: ["billing.view_clientinvoice"],
        moduleId: "billing_receivables",
        order: 10,
      },
      {
        label: "Receipts",
        href: "/receipts",
        permissions: ["billing.view_clientreceipt"],
        moduleId: "billing_receivables",
        order: 20,
      },
      {
        label: "Vendors",
        href: "/vendors",
        permissions: ["finance.view_vendor"],
        moduleId: "procurement_payables",
        order: 30,
      },
      {
        label: "Vendor Bills",
        href: "/vendor-bills",
        permissions: ["finance.view_vendorbill"],
        moduleId: "procurement_payables",
        order: 40,
      },
      {
        label: "Vendor Payments",
        href: "/vendor-payments",
        permissions: ["finance.view_paymentvoucher"],
        moduleId: "procurement_payables",
        order: 50,
      },
    ],
  },
  {
    id: "administration",
    label: "Administration",
    order: 90,
    items: [
      { label: "Company settings", href: "/settings/company", order: 10 },
      { label: "Branding", href: "/settings/branding", order: 20 },
    ],
  },
];

export const navigation = navigationGroups.flatMap((group) => group.items);

export function isNavigationItemVisible(
  item: NavigationItem,
  permissions: readonly string[],
  effectiveModules: readonly ModuleId[],
  isSuperuser: boolean,
) {
  if (item.moduleId && !hasModule(effectiveModules, item.moduleId))
    return false;
  return (
    !item.permissions || canAny(permissions, item.permissions, isSuperuser)
  );
}

export function visibleNavigationGroups(
  permissions: readonly string[],
  effectiveModules: readonly ModuleId[],
  isSuperuser: boolean,
) {
  return navigationGroups
    .map((group) => ({
      ...group,
      items: group.items
        .filter((item) =>
          isNavigationItemVisible(
            item,
            permissions,
            effectiveModules,
            isSuperuser,
          ),
        )
        .sort((a, b) => a.order - b.order),
    }))
    .filter((group) => group.items.length > 0)
    .sort((a, b) => a.order - b.order);
}

export function Sidebar({
  permissions,
  effectiveModules,
  isSuperuser,
  canAccessPlatformAdmin,
  branding,
  platformArea,
}: {
  permissions: string[];
  effectiveModules: ModuleId[];
  isSuperuser: boolean;
  canAccessPlatformAdmin: boolean;
  branding: CompanyBranding;
  platformArea: boolean;
}) {
  const pathname = usePathname();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const groups = visibleNavigationGroups(
    permissions,
    effectiveModules,
    isSuperuser,
  );

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  const closeMenu = () => setMobileOpen(false);

  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="sidebar-heading">
        <div className="brand">
          <BrandLogo className="brand-logo-shell" />
          <span>
            {branding.display_name}
            <br />
            <small>{branding.tagline}</small>
          </span>
        </div>
        <button
          ref={menuButtonRef}
          type="button"
          className="mobile-menu-button"
          aria-expanded={mobileOpen}
          aria-controls="primary-navigation"
          onClick={() => setMobileOpen((current) => !current)}
        >
          {mobileOpen ? "Close menu" : "Menu"}
        </button>
      </div>
      <nav
        id="primary-navigation"
        className={`sidebar-navigation${mobileOpen ? " is-open" : ""}`}
      >
        {platformArea ? (
          <div className="navigation-group">
            <h2>Platform</h2>
            <ul>
              <li>
                <Link
                  aria-current={
                    pathname.startsWith("/platform") ? "page" : undefined
                  }
                  href="/platform/companies"
                  onClick={closeMenu}
                >
                  Platform administration
                </Link>
              </li>
            </ul>
          </div>
        ) : (
          <>
            {groups.map((group) => (
              <div className="navigation-group" key={group.id}>
                <h2>{group.label}</h2>
                <ul>
                  {group.items.map((item) => (
                    <li key={item.href}>
                      <Link
                        aria-current={
                          pathname.startsWith(item.href) ? "page" : undefined
                        }
                        href={item.href}
                        onClick={closeMenu}
                      >
                        {item.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {canAccessPlatformAdmin ? (
              <div className="navigation-group platform-access">
                <h2>Platform access</h2>
                <ul>
                  <li>
                    <Link href="/platform/companies" onClick={closeMenu}>
                      Platform administration
                    </Link>
                  </li>
                </ul>
              </div>
            ) : null}
          </>
        )}
      </nav>
    </aside>
  );
}
