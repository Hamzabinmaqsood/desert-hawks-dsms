import type { ReactNode } from "react";

import { LogoutButton } from "@/components/auth/logout-button";
import { Sidebar } from "@/components/layout/sidebar";
import type { SessionData } from "@/lib/auth/types";

export function AppShell({
  session,
  children,
}: {
  session: SessionData;
  children: ReactNode;
}) {
  const name = [session.user.first_name, session.user.last_name]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="app-shell">
      <Sidebar
        permissions={session.permissions}
        isSuperuser={session.user.is_superuser}
      />
      <div className="app-workspace">
        <header className="topbar">
          <div>
            <strong>{name || session.user.email}</strong>
            <span>{session.user.email}</span>
          </div>
          <LogoutButton />
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
