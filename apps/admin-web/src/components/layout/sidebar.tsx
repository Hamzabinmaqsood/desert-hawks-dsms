"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { canAny } from "@/lib/auth/permissions";

interface NavigationItem {
  label: string;
  href: string;
  permissions?: string[];
}

const navigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard" },
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
        <span className="brand-mark" aria-hidden="true">
          DH
        </span>
        <span>
          Desert Hawks
          <br />
          <small>DSMS Admin</small>
        </span>
      </div>
      <nav>
        <ul>
          {visible.map((item) => (
            <li key={item.href}>
              <Link
                aria-current={pathname === item.href ? "page" : undefined}
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
