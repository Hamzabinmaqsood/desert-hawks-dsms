"use client";

import type { ReactNode } from "react";

import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/features/auth/auth-context";

export function AppShell({ children }: { children: ReactNode }) {
  const session = useAuth();
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
          <div className="topbar-identity">
            <strong>{name || session.user.email}</strong>
            <span>{session.user.email}</span>
          </div>
          <div className="topbar-actions">
            <CompanySwitcher />
            <LogoutButton />
          </div>
        </header>
        <main className="content">
          {session.company_context.companies.length === 0 ? (
            <section className="company-context-notice">
              <h1>No Company access</h1>
              <p>
                Your account is authenticated but has no active Company
                assignment. Contact an administrator if you need tenant access.
              </p>
            </section>
          ) : session.company_context.selection_required ||
            !session.company_context.selected_company ? (
            <section className="company-context-notice">
              <h1>Select a Company</h1>
              <p>
                Choose an active Company from the switcher before opening the
                tenant workspace.
              </p>
            </section>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
