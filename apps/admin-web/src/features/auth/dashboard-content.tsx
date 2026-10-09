"use client";

import { PageHeader } from "@/components/layout/page-header";
import { useAuth } from "@/features/auth/auth-context";
import { resolveCompanyBranding } from "@/lib/branding";

export function DashboardContent() {
  const { user, permissions, scopes, company_context: context } = useAuth();
  const branding = resolveCompanyBranding(context.selected_company);
  return (
    <>
      <PageHeader
        title={`${branding.display_name} workspace`}
        description={branding.tagline}
      />
      <section className="dashboard-grid" aria-label="Session overview">
        <article className="summary-card">
          <span>Signed in as</span>
          <strong>{user.first_name || user.email}</strong>
          <small>Your secure administration workspace is ready.</small>
        </article>
        <article className="summary-card">
          <span>Account</span>
          <strong>{user.email}</strong>
          <small>
            {user.is_superuser ? "Superuser" : "Authorized employee"}
          </small>
        </article>
        <article className="summary-card">
          <span>Permissions</span>
          <strong>{permissions.length}</strong>
          <small>Effective permission codes loaded</small>
        </article>
        <article className="summary-card">
          <span>Company access</span>
          <strong>{scopes.accessible_company_ids.length}</strong>
          <small>Accessible company scopes loaded</small>
        </article>
      </section>
    </>
  );
}
