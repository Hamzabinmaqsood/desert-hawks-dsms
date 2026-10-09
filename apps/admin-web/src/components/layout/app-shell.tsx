"use client";

import { useEffect, type CSSProperties, type ReactNode } from "react";

import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/features/auth/auth-context";
import { resolveCompanyBranding } from "@/lib/branding";

export function AppShell({ children }: { children: ReactNode }) {
  const session = useAuth();
  const name = [session.user.first_name, session.user.last_name]
    .filter(Boolean)
    .join(" ");
  const selectedCompany = session.company_context.selected_company;
  const branding = resolveCompanyBranding(selectedCompany);
  const tenantStyle = {
    "--tenant-brand": branding.primary_color,
    "--tenant-accent": branding.accent_color,
  } as CSSProperties;
  useEffect(() => {
    document.title = selectedCompany
      ? `${branding.display_name} — DSMS`
      : "DSMS — Security Management Platform";
    return () => {
      document.title = "DSMS — Security Management Platform";
    };
  }, [branding.display_name, selectedCompany]);
  return (
    <div className="app-shell" style={tenantStyle}>
      <Sidebar
        permissions={session.permissions}
        isSuperuser={session.user.is_superuser}
        branding={branding}
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
