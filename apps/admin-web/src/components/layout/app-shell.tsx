"use client";

import { usePathname } from "next/navigation";
import { useEffect, type CSSProperties, type ReactNode } from "react";

import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/features/auth/auth-context";
import { resolveCompanyBranding } from "@/lib/branding";
import { PLATFORM_DOCUMENT_TITLE, tenantDocumentTitle } from "@/lib/product";

export function AppShell({ children }: { children: ReactNode }) {
  const session = useAuth();
  const pathname = usePathname();
  const platformArea = pathname.startsWith("/platform");
  const name = [session.user.first_name, session.user.last_name]
    .filter(Boolean)
    .join(" ");
  const selectedCompany = session.company_context.selected_company;
  const branding = resolveCompanyBranding(
    platformArea ? null : selectedCompany,
  );
  const tenantStyle = {
    "--tenant-brand": branding.primary_color,
    "--tenant-accent": branding.accent_color,
  } as CSSProperties;
  useEffect(() => {
    document.title = platformArea
      ? PLATFORM_DOCUMENT_TITLE
      : tenantDocumentTitle(selectedCompany ? branding.display_name : null);
  }, [branding.display_name, platformArea, selectedCompany]);
  return (
    <div className="app-shell" style={tenantStyle}>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <Sidebar
        permissions={session.permissions}
        effectiveModules={session.company_context.effective_modules}
        isSuperuser={session.user.is_superuser}
        canAccessPlatformAdmin={
          session.platform_capabilities.can_access_platform_admin
        }
        branding={branding}
        platformArea={platformArea}
      />
      <div className="app-workspace">
        <header className="topbar">
          <div className="topbar-identity">
            <strong>{name || session.user.email}</strong>
            <span>{session.user.email}</span>
          </div>
          <div className="topbar-actions">
            {!platformArea ? <CompanySwitcher /> : null}
            <LogoutButton />
          </div>
        </header>
        <main className="content" id="main-content" tabIndex={-1}>
          {platformArea ? (
            children
          ) : session.company_context.companies.length === 0 ? (
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
