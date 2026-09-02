"use client";

import { PageHeader } from "@/components/layout/page-header";
import { useAuth } from "@/features/auth/auth-context";

export function DashboardContent() {
  const { user, permissions, scopes } = useAuth();
  return (
    <>
      <PageHeader
        title={`Welcome, ${user.first_name || user.email}`}
        description="Your secure administration workspace is ready."
      />
      <section className="dashboard-grid" aria-label="Session overview">
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
