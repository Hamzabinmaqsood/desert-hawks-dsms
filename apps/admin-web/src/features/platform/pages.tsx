"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";
import type { ModuleId } from "@/lib/modules";
import { PLATFORM_CAPABILITIES, hasPlatformCapability } from "@/lib/platform";

import {
  activateEntitlements,
  applyPlanRevision,
  createPlan,
  createSubscription,
  getPlanEntitlements,
  getSubscriptionEntitlements,
  listCompanies,
  listModules,
  listPlans,
  listSubscriptions,
  provisionCompany,
  replaceOverrides,
  updatePlanEntitlements,
} from "./api";
import {
  PlanModuleEditor,
  SubscriptionModuleEditor,
  dependencyIssues,
  effectiveFromDraft,
} from "./module-editor";
import type {
  ModuleCatalogItem,
  PlanEntitlements,
  PlatformCompany,
  PlatformPlan,
  PlatformSubscription,
  SubscriptionEntitlements,
  SubscriptionOverride,
} from "./types";

function PlatformNav() {
  const capabilities = useAuth().platform_capabilities.capabilities;
  const showCompanies = [
    PLATFORM_CAPABILITIES.provisionTenant,
    PLATFORM_CAPABILITIES.viewTenantDirectory,
    PLATFORM_CAPABILITIES.viewSubscriptions,
  ].some((capability) => hasPlatformCapability(capabilities, capability));
  return (
    <nav className="platform-nav" aria-label="Platform administration">
      {showCompanies ? <Link href="/platform/companies">Companies</Link> : null}
      {hasPlatformCapability(
        capabilities,
        PLATFORM_CAPABILITIES.viewPlanCatalog,
      ) ? (
        <Link href="/platform/plans">Plans</Link>
      ) : null}
      {hasPlatformCapability(
        capabilities,
        PLATFORM_CAPABILITIES.viewSubscriptions,
      ) ? (
        <Link href="/platform/subscriptions">Subscriptions</Link>
      ) : null}
    </nav>
  );
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function StatusBadge({ value }: { value: string }) {
  return (
    <span className="status-badge status-active">
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function CompanyListPage() {
  const auth = useAuth();
  const capabilities = auth.platform_capabilities.capabilities;
  const [companies, setCompanies] = useState<PlatformCompany[]>([]);
  const [subscriptions, setSubscriptions] = useState<PlatformSubscription[]>(
    [],
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const requests: Promise<unknown>[] = [];
    if (
      hasPlatformCapability(
        capabilities,
        PLATFORM_CAPABILITIES.viewTenantDirectory,
      )
    )
      requests.push(listCompanies().then(setCompanies));
    if (
      hasPlatformCapability(
        capabilities,
        PLATFORM_CAPABILITIES.viewSubscriptions,
      )
    )
      requests.push(listSubscriptions().then(setSubscriptions));
    Promise.all(requests)
      .catch((reason) =>
        setError(errorMessage(reason, "Companies could not be loaded.")),
      )
      .finally(() => setLoading(false));
  }, [capabilities]);
  const subscriptionByCompany = new Map(
    subscriptions.map((subscription) => [
      subscription.company.id,
      subscription,
    ]),
  );
  const rows = companies.length
    ? companies
    : subscriptions.map((subscription) => ({
        ...subscription.company,
        country_code: "",
        timezone: "",
        default_currency: "",
        operational_status: "",
        blocker_count: 0,
        blocker_codes: [],
        created_at: subscription.created_at,
      }));
  return (
    <>
      <PlatformNav />
      <PageHeader
        title="Companies"
        description="Safe tenant directory and commercial module status."
        actions={
          hasPlatformCapability(
            capabilities,
            PLATFORM_CAPABILITIES.provisionTenant,
          ) ? (
            <Link className="button" href="/platform/companies/new">
              Provision Company
            </Link>
          ) : undefined
        }
      />
      {error ? <ErrorState message={error} /> : null}
      {loading ? (
        <LoadingState label="Loading Companies..." />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Company state</th>
                <th>Plan</th>
                <th>Subscription</th>
                <th>Module policy</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((company) => {
                const subscription = subscriptionByCompany.get(company.id);
                return (
                  <tr key={company.id}>
                    <td>
                      <strong>
                        {company.trade_name || company.legal_name}
                      </strong>
                      <br />
                      <small>{company.code}</small>
                    </td>
                    <td>{company.is_active ? "Active" : "Inactive"}</td>
                    <td>{subscription?.plan.name ?? "Not assigned"}</td>
                    <td>{subscription?.status ?? "Not configured"}</td>
                    <td>
                      {subscription
                        ? `${subscription.policy_mode.replaceAll("_", " ")} · ${subscription.effective_module_count} modules`
                        : "Legacy full access · 20 modules"}
                    </td>
                    <td>
                      <Link href={`/platform/companies/${company.id}`}>
                        Open
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function CompanyProvisionPage() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await provisionCompany({
        idempotency_key: crypto.randomUUID(),
        company: {
          code: String(form.get("code") ?? ""),
          legal_name: String(form.get("legal_name") ?? ""),
          country_code: String(form.get("country_code") ?? ""),
          timezone: String(form.get("timezone") ?? "UTC"),
          default_currency: String(form.get("default_currency") ?? "USD"),
        },
        initial_admin: { email: String(form.get("admin_email") ?? "") },
      });
      if (!result.company)
        throw new Error("Provisioning did not return a Company.");
      router.push(`/platform/companies/${result.company.id}`);
    } catch (reason) {
      setError(
        errorMessage(reason, "Company provisioning could not be completed."),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <PlatformNav />
      <PageHeader
        title="Provision Company"
        description="Creates the Company and initial administrator through the existing transactional provisioning service. Commercial setup follows explicitly."
      />
      <form className="invoice-form" onSubmit={submit}>
        <label className="form-field">
          <span>Company code</span>
          <input name="code" required />
        </label>
        <label className="form-field">
          <span>Legal name</span>
          <input name="legal_name" required />
        </label>
        <label className="form-field">
          <span>Country code</span>
          <input name="country_code" maxLength={2} required />
        </label>
        <label className="form-field">
          <span>Timezone</span>
          <input name="timezone" defaultValue="UTC" required />
        </label>
        <label className="form-field">
          <span>Default currency</span>
          <input
            name="default_currency"
            defaultValue="USD"
            maxLength={3}
            required
          />
        </label>
        <label className="form-field">
          <span>Initial administrator email</span>
          <input name="admin_email" type="email" required />
        </label>
        {error ? <ErrorState message={error} /> : null}
        <div className="filter-actions">
          <Button disabled={pending}>
            {pending ? "Provisioning..." : "Provision Company"}
          </Button>
          <Link className="button button-secondary" href="/platform/companies">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}

export function CompanyDetailPage({ companyId }: { companyId: string }) {
  const router = useRouter();
  const [company, setCompany] = useState<PlatformCompany | null>(null);
  const [subscription, setSubscription] = useState<PlatformSubscription | null>(
    null,
  );
  const [plans, setPlans] = useState<PlatformPlan[]>([]);
  const [planId, setPlanId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    Promise.all([listCompanies(), listSubscriptions(), listPlans()])
      .then(([companies, subscriptions, availablePlans]) => {
        setCompany(companies.find((item) => item.id === companyId) ?? null);
        setSubscription(
          subscriptions.find((item) => item.company.id === companyId) ?? null,
        );
        setPlans(availablePlans.filter((item) => item.is_active));
      })
      .catch((value) =>
        setError(errorMessage(value, "Company detail could not be loaded.")),
      );
  }, [companyId]);
  async function addSubscription(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const created = await createSubscription({
        company_id: companyId,
        plan_id: planId,
        status: "ACTIVE",
        reason,
      });
      router.push(`/platform/subscriptions/${created.id}`);
    } catch (value) {
      setError(errorMessage(value, "Subscription could not be created."));
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <PlatformNav />
      <PageHeader
        title={
          company?.trade_name ||
          company?.legal_name ||
          "Company commercial setup"
        }
        description="Company identity, Subscription, and module policy remain separate authorities."
      />
      {error ? <ErrorState message={error} /> : null}
      {!company ? (
        <LoadingState label="Loading Company..." />
      ) : (
        <section className="detail-card">
          <dl className="detail-grid">
            <dt>Company code</dt>
            <dd>{company.code}</dd>
            <dt>Company state</dt>
            <dd>{company.is_active ? "Active" : "Inactive"}</dd>
            <dt>Operational readiness</dt>
            <dd>{company.operational_status}</dd>
            <dt>Subscription</dt>
            <dd>{subscription?.status ?? "Not configured"}</dd>
            <dt>Plan</dt>
            <dd>{subscription?.plan.name ?? "Not assigned"}</dd>
          </dl>
        </section>
      )}
      {subscription ? (
        <p>
          <Link
            className="button"
            href={`/platform/subscriptions/${subscription.id}`}
          >
            Manage business modules
          </Link>
        </p>
      ) : company ? (
        <form className="detail-card invoice-form" onSubmit={addSubscription}>
          <h2>Create Subscription</h2>
          <p>
            The Company remains in recoverable legacy full-access mode until
            module-based access is explicitly activated.
          </p>
          <label className="form-field">
            <span>Plan</span>
            <select
              value={planId}
              onChange={(event) => setPlanId(event.target.value)}
              required
            >
              <option value="">Select a Plan</option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.code} - {plan.name}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span>Reason</span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={255}
            />
          </label>
          <Button disabled={pending}>
            {pending ? "Creating..." : "Create Subscription"}
          </Button>
        </form>
      ) : null}
    </>
  );
}

export function PlanListPage() {
  const auth = useAuth();
  const canManage = hasPlatformCapability(
    auth.platform_capabilities.capabilities,
    PLATFORM_CAPABILITIES.managePlanCatalog,
  );
  const [plans, setPlans] = useState<PlatformPlan[]>([]);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  useEffect(() => {
    listPlans()
      .then(setPlans)
      .catch((value) =>
        setError(errorMessage(value, "Plans could not be loaded.")),
      );
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const plan = await createPlan({
        code: String(form.get("code") ?? ""),
        name: String(form.get("name") ?? ""),
        description: String(form.get("description") ?? ""),
      });
      setPlans((current) =>
        [...current, plan].sort((a, b) => a.code.localeCompare(b.code)),
      );
      setShowCreate(false);
    } catch (value) {
      setError(errorMessage(value, "Plan could not be created."));
    }
  }
  return (
    <>
      <PlatformNav />
      <PageHeader
        title="Plans"
        description="Code-defined business modules assembled into commercial Plan defaults."
        actions={
          canManage ? (
            <Button onClick={() => setShowCreate((value) => !value)}>
              New Plan
            </Button>
          ) : undefined
        }
      />
      {showCreate ? (
        <form className="detail-card invoice-form" onSubmit={submit}>
          <label className="form-field">
            <span>Code</span>
            <input name="code" required />
          </label>
          <label className="form-field">
            <span>Name</span>
            <input name="name" required />
          </label>
          <label className="form-field">
            <span>Description</span>
            <input name="description" />
          </label>
          <Button>Create Plan</Button>
        </form>
      ) : null}
      {error ? <ErrorState message={error} /> : null}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Modules</th>
            </tr>
          </thead>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id}>
                <td>{plan.code}</td>
                <td>{plan.name}</td>
                <td>{plan.is_active ? "Active" : "Inactive"}</td>
                <td>
                  <Link href={`/platform/plans/${plan.id}`}>Configure</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function PlanDetailPage({ planId }: { planId: string }) {
  const auth = useAuth();
  const canManage = hasPlatformCapability(
    auth.platform_capabilities.capabilities,
    PLATFORM_CAPABILITIES.managePlanCatalog,
  );
  const [catalog, setCatalog] = useState<ModuleCatalogItem[]>([]);
  const [state, setState] = useState<PlanEntitlements | null>(null);
  const [enabled, setEnabled] = useState<ModuleId[]>([]);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let cancelled = false;
    Promise.all([listModules(), getPlanEntitlements(planId)])
      .then(([modules, entitlements]) => {
        if (cancelled) return;
        setCatalog(modules);
        setState(entitlements);
        setEnabled(entitlements.enabled_module_ids);
      })
      .catch((value) => {
        if (!cancelled)
          setMessage(errorMessage(value, "Plan modules could not be loaded."));
      });
    return () => {
      cancelled = true;
    };
  }, [planId]);
  const issues = dependencyIssues(catalog, enabled);
  async function save() {
    if (issues.length) return;
    setPending(true);
    setMessage("");
    try {
      const updated = await updatePlanEntitlements(planId, enabled, reason);
      setState(updated);
      setEnabled(updated.enabled_module_ids);
      setMessage(updated.snapshot_notice);
    } catch (value) {
      setMessage(errorMessage(value, "Plan modules could not be saved."));
    } finally {
      setPending(false);
    }
  }
  if (!state)
    return (
      <>
        <PlatformNav />
        {message ? <ErrorState message={message} /> : <LoadingState />}
      </>
    );
  return (
    <>
      <PlatformNav />
      <PageHeader
        title={`${state.plan_code} - ${state.plan_name}`}
        description={`Plan entitlement revision ${state.entitlement_revision}`}
      />
      <div className="notice-card">
        Changing Plan defaults does not update existing Subscription snapshots.
      </div>
      <PlanModuleEditor
        catalog={catalog}
        enabledIds={enabled}
        onChange={setEnabled}
        disabled={!canManage || pending}
      />
      {issues.map((issue) => (
        <p className="field-error" key={issue}>
          {issue}
        </p>
      ))}
      {message ? (
        <div className="state-card" role="status">
          {message}
        </div>
      ) : null}
      {canManage ? (
        <div className="detail-card">
          <label className="form-field">
            <span>Change reason</span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={255}
            />
          </label>
          <Button
            onClick={() => void save()}
            disabled={pending || issues.length > 0}
          >
            {pending ? "Saving..." : "Save Plan modules"}
          </Button>
        </div>
      ) : null}
    </>
  );
}

export function SubscriptionListPage() {
  const [subscriptions, setSubscriptions] = useState<PlatformSubscription[]>(
    [],
  );
  const [error, setError] = useState("");
  useEffect(() => {
    listSubscriptions()
      .then(setSubscriptions)
      .catch((value) =>
        setError(errorMessage(value, "Subscriptions could not be loaded.")),
      );
  }, []);
  return (
    <>
      <PlatformNav />
      <PageHeader
        title="Subscriptions"
        description="Commercial lifecycle and explicit module snapshot administration."
      />
      {error ? <ErrorState message={error} /> : null}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Company</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Modules</th>
            </tr>
          </thead>
          <tbody>
            {subscriptions.map((subscription) => (
              <tr key={subscription.id}>
                <td>
                  {subscription.company.trade_name ||
                    subscription.company.legal_name}
                </td>
                <td>{subscription.plan.name}</td>
                <td>
                  <StatusBadge value={subscription.status} />
                </td>
                <td>
                  <Link href={`/platform/subscriptions/${subscription.id}`}>
                    Manage
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function SubscriptionDetailPage({
  subscriptionId,
}: {
  subscriptionId: string;
}) {
  const auth = useAuth();
  const canManage = hasPlatformCapability(
    auth.platform_capabilities.capabilities,
    PLATFORM_CAPABILITIES.manageSubscriptions,
  );
  const [catalog, setCatalog] = useState<ModuleCatalogItem[]>([]);
  const [state, setState] = useState<SubscriptionEntitlements | null>(null);
  const [overrides, setOverrides] = useState<SubscriptionOverride[]>([]);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let cancelled = false;
    Promise.all([listModules(), getSubscriptionEntitlements(subscriptionId)])
      .then(([modules, entitlements]) => {
        if (cancelled) return;
        setCatalog(modules);
        setState(entitlements);
        setOverrides(entitlements.overrides);
      })
      .catch((value) => {
        if (!cancelled)
          setMessage(
            errorMessage(value, "Subscription modules could not be loaded."),
          );
      });
    return () => {
      cancelled = true;
    };
  }, [subscriptionId]);
  const draftEffective = useMemo(
    () =>
      state
        ? effectiveFromDraft(catalog, state.snapshot_module_ids, overrides)
        : [],
    [catalog, overrides, state],
  );
  const issues = dependencyIssues(catalog, draftEffective);
  async function perform(
    action: () => Promise<SubscriptionEntitlements>,
    success: string,
  ) {
    setPending(true);
    setMessage("");
    try {
      const updated = await action();
      setState(updated);
      setOverrides(updated.overrides);
      setMessage(success);
    } catch (value) {
      setMessage(errorMessage(value, "The module change could not be saved."));
    } finally {
      setPending(false);
    }
  }
  if (!state)
    return (
      <>
        <PlatformNav />
        {message ? <ErrorState message={message} /> : <LoadingState />}
      </>
    );
  const planBehind =
    state.snapshot_initialized &&
    state.snapshot_plan_entitlement_revision !==
      state.plan_entitlement_revision;
  const enabledOverrides = overrides
    .filter((item) => item.state === "ENABLED")
    .map((item) => item.module_id);
  const disabledOverrides = overrides
    .filter((item) => item.state === "DISABLED")
    .map((item) => item.module_id);
  const proposedPlanEffective = effectiveFromDraft(
    catalog,
    state.plan_module_ids,
    overrides,
  );
  const planGains = proposedPlanEffective.filter(
    (moduleId) => !state.effective_module_ids.includes(moduleId),
  );
  const planLosses = state.effective_module_ids.filter(
    (moduleId) => !proposedPlanEffective.includes(moduleId),
  );
  const moduleNames = (moduleIds: ModuleId[]) =>
    moduleIds
      .map(
        (moduleId) =>
          catalog.find((module) => module.id === moduleId)?.display_name ??
          moduleId,
      )
      .join(", ");
  return (
    <>
      <PlatformNav />
      <PageHeader
        title={state.company.trade_name || state.company.legal_name}
        description="Commercial Subscription module policy"
      />
      <section className="detail-card">
        <dl className="detail-grid">
          <dt>Subscription</dt>
          <dd>
            <StatusBadge value={state.subscription_status} />
          </dd>
          <dt>Plan</dt>
          <dd>
            {state.plan.code} - {state.plan.name}
          </dd>
          <dt>Entitlement policy</dt>
          <dd>
            <StatusBadge value={state.policy_mode} />
          </dd>
          <dt>Effective modules</dt>
          <dd>{state.effective_module_ids.length}</dd>
          <dt>Plan revision</dt>
          <dd>{state.plan_entitlement_revision}</dd>
          <dt>Subscription snapshot</dt>
          <dd>
            {state.snapshot_plan_entitlement_revision ?? "Not initialized"}
          </dd>
          <dt>Entitlement revision</dt>
          <dd>{state.entitlement_revision}</dd>
        </dl>
      </section>
      {state.policy_mode === "LEGACY_FULL" ? (
        <div className="notice-card">
          <strong>Legacy full access</strong>
          <p>
            All current legacy modules remain enabled. Opening this page does
            not activate commercial enforcement.
          </p>
          <p>
            Prospective Plan snapshot: {state.plan_module_ids.length} modules.
          </p>
        </div>
      ) : null}
      {planBehind ? (
        <div className="notice-card">
          <strong>Plan update available</strong>
          <p>
            The Subscription retains its current snapshot until explicitly
            updated.
          </p>
          <p>
            Module gains: {planGains.length ? moduleNames(planGains) : "None"}
          </p>
          <p>
            Module losses:{" "}
            {planLosses.length ? moduleNames(planLosses) : "None"}
          </p>
        </div>
      ) : null}
      <SubscriptionModuleEditor
        catalog={catalog}
        snapshotIds={
          state.policy_mode === "LEGACY_FULL"
            ? state.plan_module_ids
            : state.snapshot_module_ids
        }
        overrides={overrides}
        onChange={setOverrides}
        disabled={!canManage || pending}
      />
      {issues.map((issue) => (
        <p className="field-error" key={issue}>
          {issue}
        </p>
      ))}
      <div className="notice-card">
        Disabling a module blocks access but retains its data. Re-enabling
        restores access. Dependencies may prevent a change.
      </div>
      {message ? (
        <div className="state-card" role="status">
          {message}
        </div>
      ) : null}
      {canManage ? (
        <section className="detail-card">
          <label className="form-field">
            <span>Change reason</span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={255}
            />
          </label>
          <div className="filter-actions">
            {state.policy_mode === "LEGACY_FULL" ? (
              <Button
                disabled={pending || issues.length > 0}
                onClick={() =>
                  void perform(
                    () =>
                      activateEntitlements(
                        subscriptionId,
                        enabledOverrides,
                        disabledOverrides,
                        reason,
                      ),
                    "Module-based subscription access activated.",
                  )
                }
              >
                Activate module-based subscription access
              </Button>
            ) : (
              <Button
                disabled={pending || issues.length > 0}
                onClick={() =>
                  void perform(
                    () =>
                      replaceOverrides(
                        subscriptionId,
                        enabledOverrides,
                        disabledOverrides,
                        reason,
                      ),
                    "Subscription overrides saved.",
                  )
                }
              >
                Save overrides
              </Button>
            )}
            {planBehind ? (
              <Button
                className="button-secondary"
                disabled={pending || !reason.trim()}
                onClick={() => {
                  if (
                    window.confirm(
                      "Apply the latest Plan configuration while preserving valid overrides?",
                    )
                  )
                    void perform(
                      () => applyPlanRevision(subscriptionId, reason),
                      "Latest Plan revision applied.",
                    );
                }}
              >
                Apply latest Plan configuration
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}
    </>
  );
}
