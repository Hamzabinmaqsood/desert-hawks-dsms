"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-field";
import { ErrorState } from "@/components/ui/states";
import { ApiError } from "@/lib/api/client";

import { createInvoice } from "./api";
import { InvoiceHeaderFields, validateHeaderDates } from "./header-fields";
import { listBillingProfiles, listContracts } from "./reference-api";
import { INVOICE_TYPE_OPTIONS } from "./types";
import type { BillingProfile, Contract } from "./types";

const emptyValues = {
  billing_profile: "",
  invoice_type: "",
  contract: "",
  invoice_date: "",
  service_period_start: "",
  service_period_end: "",
  client_po_reference: "",
  client_reference: "",
};

export function InvoiceCreateForm() {
  const router = useRouter();
  const [profiles, setProfiles] = useState<BillingProfile[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [refError, setRefError] = useState("");
  const [values, setValues] = useState(emptyValues);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [nonFieldError, setNonFieldError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([listBillingProfiles(), listContracts()])
      .then(([profileList, contractList]) => {
        if (!active) return;
        setProfiles(profileList);
        setContracts(contractList);
      })
      .catch(() => {
        if (active) setRefError("Reference data could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedProfile = profiles.find(
    (profile) => profile.id === values.billing_profile,
  );
  const availableContracts = selectedProfile
    ? contracts.filter((contract) => contract.client === selectedProfile.client)
    : [];

  function set(key: keyof typeof emptyValues, value: string) {
    setValues((current) => {
      const next = { ...current, [key]: value };
      if (key === "billing_profile") next.contract = "";
      return next;
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const dateErrors = validateHeaderDates(values);
    if (Object.keys(dateErrors).length) {
      setErrors(dateErrors);
      return;
    }
    setSubmitting(true);
    setErrors({});
    setNonFieldError(undefined);
    try {
      const created = await createInvoice({
        billing_profile: values.billing_profile,
        invoice_date: values.invoice_date,
        invoice_type: values.invoice_type,
        contract: values.contract || undefined,
        service_period_start: values.service_period_start || undefined,
        service_period_end: values.service_period_end || undefined,
        client_po_reference: values.client_po_reference || undefined,
        client_reference: values.client_reference || undefined,
      });
      router.push(`/invoices/${created.id}/edit`);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setErrors(caught.fieldErrors);
        setNonFieldError(caught.message);
      } else {
        setNonFieldError("The invoice could not be created.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (refError) return <ErrorState message={refError} />;

  return (
    <form className="invoice-form" onSubmit={submit} aria-label="New invoice">
      <label className="form-field">
        <span>Billing profile</span>
        <select
          required
          value={values.billing_profile}
          onChange={(event) => set("billing_profile", event.target.value)}
          disabled={submitting}
        >
          <option value="">Select a billing profile</option>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.billing_name} ({profile.currency})
            </option>
          ))}
        </select>
        {errors.billing_profile?.[0] ? (
          <span className="field-error">{errors.billing_profile[0]}</span>
        ) : null}
      </label>
      {selectedProfile ? (
        <p className="form-hint">
          Payment terms: {selectedProfile.payment_terms_days} days · Currency:{" "}
          {selectedProfile.currency}
        </p>
      ) : null}
      <label className="form-field">
        <span>Invoice type</span>
        <select
          required
          value={values.invoice_type}
          onChange={(event) => set("invoice_type", event.target.value)}
          disabled={submitting}
        >
          <option value="">Select an invoice type</option>
          {INVOICE_TYPE_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {errors.invoice_type?.[0] ? (
          <span className="field-error">{errors.invoice_type[0]}</span>
        ) : null}
      </label>
      <InvoiceHeaderFields
        values={values}
        errors={errors}
        onChange={set}
        contracts={availableContracts}
        disabled={submitting}
      />
      <FormError message={nonFieldError} />
      <div className="filter-actions">
        <Button type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create draft"}
        </Button>
        <Link className="button button-secondary" href="/invoices">
          Cancel
        </Link>
      </div>
    </form>
  );
}
