"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import type { AuthContextValue } from "@/features/auth/auth-context";
import type { ModuleId } from "@/lib/modules";

export interface DashboardWidgetContext {
  auth: AuthContextValue;
  companyId: string;
}

export interface DashboardWidgetDefinition {
  id: string;
  title: string;
  order: number;
  moduleId?: ModuleId;
  permissions?: string[];
  load?: (
    context: DashboardWidgetContext,
    signal: AbortSignal,
  ) => Promise<unknown>;
  render: (context: DashboardWidgetContext, data: unknown) => ReactNode;
}

export function isDashboardWidgetVisible(
  widget: DashboardWidgetDefinition,
  auth: AuthContextValue,
) {
  if (widget.moduleId && !auth.hasModule(widget.moduleId)) return false;
  return !widget.permissions || auth.canAny(...widget.permissions);
}

function AsyncWidgetContent({
  widget,
  context,
}: {
  widget: DashboardWidgetDefinition;
  context: DashboardWidgetContext;
}) {
  const [data, setData] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    widget.load!(context, controller.signal)
      .then((result) => {
        if (current) setData(result);
      })
      .catch(() => {
        if (current && !controller.signal.aborted) setFailed(true);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [context, widget]);

  if (loading)
    return <LoadingState label={`Loading ${widget.title.toLowerCase()}…`} />;
  if (failed)
    return (
      <ErrorState
        title={`${widget.title} unavailable`}
        message="This information could not be loaded. Other workspace tools remain available."
      />
    );
  return widget.render(context, data);
}

function WidgetSlot({
  widget,
  context,
}: {
  widget: DashboardWidgetDefinition;
  context: DashboardWidgetContext;
}) {
  return (
    <article
      className="dashboard-widget"
      aria-labelledby={`widget-${widget.id}`}
    >
      <h2 id={`widget-${widget.id}`}>{widget.title}</h2>
      {widget.load ? (
        <AsyncWidgetContent widget={widget} context={context} />
      ) : (
        widget.render(context, undefined)
      )}
    </article>
  );
}

export const defaultDashboardWidgets: DashboardWidgetDefinition[] = [
  {
    id: "workspace-overview",
    title: "Workspace overview",
    order: 10,
    render: ({ auth }) => (
      <div>
        <strong>
          {auth.company_context.selected_company?.display_name ??
            "Selected Company"}
        </strong>
        <p>
          Use the navigation to manage the business areas available to your
          Company and role.
        </p>
      </div>
    ),
  },
  {
    id: "setup-guidance",
    title: "Company setup",
    order: 20,
    render: () => (
      <ul className="setup-list">
        <li>
          <Link href="/settings/company">Review Company settings</Link>
        </li>
        <li>
          <Link href="/settings/branding">Configure Company branding</Link>
        </li>
      </ul>
    ),
  },
  {
    id: "billing-actions",
    title: "Billing & receivables",
    order: 30,
    moduleId: "billing_receivables",
    permissions: ["billing.view_clientinvoice"],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/invoices">View invoices</Link>
        {auth.can("billing.add_clientinvoice") ? (
          <Link href="/invoices/new">Create an invoice</Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "payables-actions",
    title: "Vendors & payables",
    order: 40,
    moduleId: "procurement_payables",
    permissions: ["finance.view_vendor"],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/vendors">View vendors</Link>
        {auth.can("finance.add_vendor") ? (
          <Link href="/vendors/new">Add a vendor</Link>
        ) : null}
      </div>
    ),
  },
];

export function DashboardWidgetBoard({
  widgets = defaultDashboardWidgets,
}: {
  widgets?: DashboardWidgetDefinition[];
}) {
  const auth = useAuth();
  const companyId = auth.company_context.selected_company?.id;
  if (!companyId) return null;
  const context = { auth, companyId };
  const visible = widgets
    .filter((widget) => isDashboardWidgetVisible(widget, auth))
    .sort((a, b) => a.order - b.order);
  return (
    <section className="dashboard-grid" aria-label="Company workspace">
      {visible.map((widget) => (
        <WidgetSlot
          key={`${companyId}:${widget.id}`}
          widget={widget}
          context={context}
        />
      ))}
    </section>
  );
}
