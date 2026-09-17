"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";
import {
  createVendor,
  getVendor,
  listVendorPayableAccounts,
  listVendors,
  updateVendor,
} from "./api";
import type { Vendor, VendorPayableAccount } from "./types";

const Status = ({ active }: { active: boolean }) => (
  <span className={`status-badge status-${active ? "active" : "inactive"}`}>
    {active ? "Active" : "Inactive"}
  </span>
);

export function VendorListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const [data, setData] = useState<Awaited<
    ReturnType<typeof listVendors>
  > | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (auth.can("finance.view_vendor"))
      listVendors(searchParams)
        .then(setData)
        .catch(() => setError("Vendors could not be loaded."));
  }, [auth, searchParams]);
  if (!auth.can("finance.view_vendor"))
    return <ErrorState message="You do not have permission to view Vendors." />;
  return (
    <>
      <PageHeader
        title="Vendors"
        description="Manage approved supplier master data."
        actions={
          auth.can("finance.add_vendor") ? (
            <Link className="button" href="/vendors/new">
              New Vendor
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/vendors">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Code, name, tax number or email"
          />
        </label>
        <label>
          Status
          <select name="is_active" defaultValue={searchParams.is_active}>
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </label>
        <div className="filter-actions">
          <Button type="submit">Apply</Button>
          <Link className="button button-secondary" href="/vendors">
            Clear
          </Link>
        </div>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Vendors…" />
      ) : !data.results.length ? (
        <EmptyState message="No Vendors found." />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Vendor</th>
                <th>Tax number</th>
                <th>Contact</th>
                <th>Payment terms</th>
                <th>Payable account</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((v) => (
                <tr key={v.id}>
                  <td>
                    <Link href={`/vendors/${v.id}`}>{v.code}</Link>
                  </td>
                  <td>{v.name}</td>
                  <td>{v.tax_number || "—"}</td>
                  <td>{v.email || v.phone || "—"}</td>
                  <td>{v.payment_terms_days} days</td>
                  <td>
                    {v.payable_account_code} — {v.payable_account_name}
                  </td>
                  <td>
                    <Status active={v.is_active} />
                  </td>
                  <td>
                    {auth.can("finance.change_vendor") ? (
                      <Link href={`/vendors/${v.id}/edit`}>Edit</Link>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

const blank = {
  code: "",
  name: "",
  tax_number: "",
  email: "",
  phone: "",
  payment_terms_days: "30",
  payable_account: "",
  is_active: true,
};

function VendorForm({ vendor }: { vendor?: Vendor }) {
  const auth = useAuth();
  const router = useRouter();
  const permission = vendor ? "finance.change_vendor" : "finance.add_vendor";
  const [accounts, setAccounts] = useState<VendorPayableAccount[]>([]);
  const [values, setValues] = useState({
    ...blank,
    ...(vendor
      ? { ...vendor, payment_terms_days: String(vendor.payment_terms_days) }
      : {}),
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    listVendorPayableAccounts()
      .then(setAccounts)
      .catch(() => setMessage("Payable accounts could not be loaded."));
  }, []);
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage this Vendor." />
    );
  const set = (key: keyof typeof blank, value: string | boolean) =>
    setValues((current) => ({ ...current, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setMessage("");
    try {
      const saved = vendor
        ? await updateVendor(vendor.id, values)
        : await createVendor(values);
      router.push(`/vendors/${saved.id}`);
    } catch (reason) {
      if (reason instanceof ApiError) {
        setErrors(reason.fieldErrors);
        setMessage(reason.message);
      } else setMessage("The Vendor could not be saved.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form
      className="invoice-form"
      aria-label={vendor ? "Edit Vendor" : "New Vendor"}
      onSubmit={submit}
    >
      <FormField
        id="code"
        label="Code"
        required
        value={values.code}
        onChange={(e) => set("code", e.target.value)}
        error={errors.code?.[0]}
      />
      <FormField
        id="name"
        label="Vendor name"
        required
        value={values.name}
        onChange={(e) => set("name", e.target.value)}
        error={errors.name?.[0]}
      />
      <FormField
        id="tax_number"
        label="Tax number"
        value={values.tax_number}
        onChange={(e) => set("tax_number", e.target.value)}
        error={errors.tax_number?.[0]}
      />
      <FormField
        id="email"
        label="Email"
        type="email"
        value={values.email}
        onChange={(e) => set("email", e.target.value)}
        error={errors.email?.[0]}
      />
      <FormField
        id="phone"
        label="Phone"
        value={values.phone}
        onChange={(e) => set("phone", e.target.value)}
        error={errors.phone?.[0]}
      />
      <FormField
        id="payment_terms_days"
        label="Payment terms (days)"
        type="number"
        min="0"
        required
        value={values.payment_terms_days}
        onChange={(e) => set("payment_terms_days", e.target.value)}
        error={errors.payment_terms_days?.[0]}
      />
      <label className="form-field">
        <span>Payable account</span>
        <select
          required
          value={values.payable_account}
          onChange={(e) => set("payable_account", e.target.value)}
        >
          <option value="">Select an account</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.code} — {a.name}
            </option>
          ))}
        </select>
        {errors.payable_account?.[0] ? (
          <span className="field-error">{errors.payable_account[0]}</span>
        ) : null}
      </label>
      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={values.is_active}
          onChange={(e) => set("is_active", e.target.checked)}
        />{" "}
        Active
      </label>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving…" : "Save Vendor"}
        </Button>
        <Link
          className="button button-secondary"
          href={vendor ? `/vendors/${vendor.id}` : "/vendors"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}

export function VendorCreatePage() {
  return (
    <>
      <PageHeader
        title="New Vendor"
        description="Create secure supplier master data."
      />
      <VendorForm />
    </>
  );
}
export function VendorEditPage({ id }: { id: string }) {
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getVendor(id)
      .then(setVendor)
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "Vendor not found."
            : "Vendor could not be loaded.",
        ),
      );
  }, [id]);
  return error ? (
    <ErrorState message={error} />
  ) : !vendor ? (
    <LoadingState label="Loading Vendor…" />
  ) : (
    <>
      <PageHeader
        title={`Edit ${vendor.code}`}
        description="Update supplier master data."
      />
      <VendorForm vendor={vendor} />
    </>
  );
}
export function VendorDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (auth.can("finance.view_vendor"))
      getVendor(id)
        .then(setVendor)
        .catch((e) =>
          setError(
            e instanceof ApiError && e.status === 404
              ? "Vendor not found."
              : "Vendor could not be loaded.",
          ),
        );
  }, [auth, id]);
  if (!auth.can("finance.view_vendor"))
    return <ErrorState message="You do not have permission to view Vendors." />;
  if (error) return <ErrorState message={error} />;
  if (!vendor) return <LoadingState label="Loading Vendor…" />;
  return (
    <>
      <PageHeader
        title={vendor.name}
        description={`Vendor ${vendor.code}`}
        actions={
          auth.can("finance.change_vendor") ? (
            <Link className="button" href={`/vendors/${vendor.id}/edit`}>
              Edit Vendor
            </Link>
          ) : undefined
        }
      />
      <section className="detail-card">
        <dl className="detail-grid">
          <dt>Code</dt>
          <dd>{vendor.code}</dd>
          <dt>Tax number</dt>
          <dd>{vendor.tax_number || "—"}</dd>
          <dt>Email</dt>
          <dd>{vendor.email || "—"}</dd>
          <dt>Phone</dt>
          <dd>{vendor.phone || "—"}</dd>
          <dt>Payment terms</dt>
          <dd>{vendor.payment_terms_days} days</dd>
          <dt>Payable account</dt>
          <dd>
            {vendor.payable_account_code} — {vendor.payable_account_name}
          </dd>
          <dt>Status</dt>
          <dd>
            <Status active={vendor.is_active} />
          </dd>
        </dl>
      </section>
    </>
  );
}
