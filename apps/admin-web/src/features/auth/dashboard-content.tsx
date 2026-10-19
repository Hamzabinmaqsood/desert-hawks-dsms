"use client";

import { PageHeader } from "@/components/layout/page-header";
import { useAuth } from "@/features/auth/auth-context";
import { DashboardWidgetBoard } from "@/features/auth/dashboard-widgets";
import { resolveCompanyBranding } from "@/lib/branding";

export function DashboardContent() {
  const { company_context: context } = useAuth();
  const branding = resolveCompanyBranding(context.selected_company);
  return (
    <>
      <PageHeader
        title={`${branding.display_name} workspace`}
        description="Your Company tools, setup, and available business modules."
      />
      <DashboardWidgetBoard />
    </>
  );
}
