"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import type { AuthContextValue } from "@/features/auth/auth-context";
import { apiFetch } from "@/lib/api/client";
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

interface ReceivablesSummary {
  ageing: Record<string, string>;
}

function BillingWidget({ auth }: { auth: AuthContextValue }) {
  const [summary, setSummary] = useState<ReceivablesSummary | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    apiFetch<ReceivablesSummary>("/api/billing-summary", {
      signal: controller.signal,
    })
      .then((value) => current && setSummary(value))
      .catch(() => undefined);
    return () => {
      current = false;
      controller.abort();
    };
  }, []);
  const overdue = summary
    ? ["1-30", "31-60", "61-90", "91-120", "120+"].reduce(
        (total, bucket) => total + Number(summary.ageing[bucket] ?? 0),
        0,
      )
    : null;
  return (
    <div>
      {overdue !== null ? (
        <p>
          <strong>{overdue.toFixed(2)}</strong> overdue across AR ageing buckets
        </p>
      ) : (
        <p>Review invoices and Company billing prerequisites.</p>
      )}
      <div className="quick-actions">
        <Link href="/invoices">View invoices</Link>
        {auth.can("billing.add_clientinvoice") ? (
          <Link href="/invoices/new">Create an invoice</Link>
        ) : null}
      </div>
    </div>
  );
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
    render: ({ auth }) => (
      <ul className="setup-list">
        <li>
          <Link href="/settings/company">Review Company settings</Link>
        </li>
        <li>
          <Link href="/settings/branding">Configure Company branding</Link>
        </li>
        {auth.hasModule("people") && auth.can("workforce.add_employee") ? (
          <li>
            <Link href="/employees/new">Add the first employee</Link>
          </li>
        ) : null}
        {auth.hasModule("client_contracts") &&
        auth.can("contracts.add_client") ? (
          <li>
            <Link href="/clients/new">Add the first client</Link>
          </li>
        ) : null}
        {auth.hasModule("client_contracts") &&
        auth.can("contracts.add_servicecontract") ? (
          <li>
            <Link href="/contracts/new">Create the first contract</Link>
          </li>
        ) : null}
        {auth.hasModule("billing_receivables") &&
        auth.can("billing.view_clientbillingprofile") ? (
          <li>
            <Link href="/clients">
              Review Client Billing Profiles and accounting prerequisites
            </Link>
          </li>
        ) : null}
        {auth.hasModule("procurement_payables") &&
        auth.can("finance.add_purchaserequisition") ? (
          <li>
            <Link href="/purchase-requisitions/new">
              Create a Purchase Requisition
            </Link>
          </li>
        ) : null}
        {auth.hasModule("asset_management") &&
        auth.canAny("assets.register_asset", "assets.receive_asset_stock") ? (
          <li>
            <Link href="/assets/new">Register received Assets</Link>
          </li>
        ) : null}
        {auth.hasModule("recruitment") &&
        auth.can("recruitment.add_manpowerrequisition") ? (
          <li>
            <Link href="/recruitment/requisitions/new">
              Create the first Job Requisition
            </Link>
          </li>
        ) : null}
        {auth.hasModule("learning") &&
        auth.can("training.add_trainingcourse") ? (
          <li>
            <Link href="/learning/courses/new">Create the first course</Link>
          </li>
        ) : null}
      </ul>
    ),
  },
  {
    id: "people-actions",
    title: "People",
    order: 25,
    moduleId: "people",
    permissions: ["workforce.view_employee"],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/employees">View employees</Link>
        {auth.can("workforce.add_employee") ? (
          <Link href="/employees/new">Add employee</Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "recruitment-actions",
    title: "Recruitment",
    order: 26,
    moduleId: "recruitment",
    permissions: [
      "recruitment.view_manpowerrequisition",
      "recruitment.view_candidateapplication",
    ],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/recruitment">View Recruitment</Link>
        {auth.can("recruitment.add_manpowerrequisition") ? (
          <Link href="/recruitment/requisitions/new">
            Create Job Requisition
          </Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "leave-actions",
    title: "Leave",
    order: 27,
    moduleId: "leave",
    permissions: [
      "leave.view_own_leave_request",
      "leave.view_team_availability",
    ],
    render: ({ auth }) => (
      <div className="quick-actions">
        {auth.can("leave.view_own_leave_request") ? (
          <Link href="/leave">Request Leave</Link>
        ) : null}
        {auth.can("leave.view_team_availability") ? (
          <Link href="/leave">Review Leave requests</Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "learning-actions",
    title: "Learning & Qualifications",
    order: 28,
    moduleId: "learning",
    permissions: ["training.view_trainingcourse"],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/learning">View Learning</Link>
        {auth.can("training.add_trainingcourse") ? (
          <Link href="/learning/courses/new">Create course</Link>
        ) : null}
        {auth.can("training.add_trainingsession") ? (
          <Link href="/learning/sessions/new">Create session</Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "client-actions",
    title: "Clients & contracts",
    order: 27,
    moduleId: "client_contracts",
    permissions: ["contracts.view_client", "contracts.view_servicecontract"],
    render: ({ auth }) => (
      <div className="quick-actions">
        {auth.can("contracts.view_client") ? (
          <Link href="/clients">View clients</Link>
        ) : null}
        {auth.can("contracts.add_client") ? (
          <Link href="/clients/new">Add client</Link>
        ) : null}
        {auth.can("contracts.view_servicecontract") ? (
          <Link href="/contracts">View contracts</Link>
        ) : null}
        {auth.can("contracts.add_servicecontract") ? (
          <Link href="/contracts/new">Create contract</Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "billing-actions",
    title: "Billing & receivables",
    order: 30,
    moduleId: "billing_receivables",
    permissions: ["billing.view_clientinvoice"],
    render: ({ auth }) => <BillingWidget auth={auth} />,
  },
  {
    id: "payables-actions",
    title: "Procurement & payables",
    order: 40,
    moduleId: "procurement_payables",
    permissions: ["finance.view_vendor"],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/vendors">View vendors</Link>
        {auth.can("finance.add_vendor") ? (
          <Link href="/vendors/new">Add a vendor</Link>
        ) : null}
        {auth.can("finance.view_purchaserequisition") ? (
          <Link href="/purchase-requisitions">Purchase Requisitions</Link>
        ) : null}
        {auth.can("finance.add_purchaserequisition") ? (
          <Link href="/purchase-requisitions/new">
            New Purchase Requisition
          </Link>
        ) : null}
        {auth.can("finance.view_purchaseorder") ? (
          <Link href="/purchase-orders">Purchase Orders</Link>
        ) : null}
        {auth.can("finance.view_purchasereceipt") ? (
          <Link href="/purchase-receipts">Purchase Receipts</Link>
        ) : null}
      </div>
    ),
  },
  {
    id: "asset-actions",
    title: "Asset Management",
    order: 50,
    moduleId: "asset_management",
    permissions: ["assets.view_asset"],
    render: ({ auth }) => (
      <div className="quick-actions">
        <Link href="/assets">View Assets</Link>
        {auth.canAny("assets.register_asset", "assets.receive_asset_stock") ? (
          <Link href="/assets/new">Register received Assets</Link>
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
