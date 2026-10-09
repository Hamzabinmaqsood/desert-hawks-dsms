"use client";

import { useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { useAuth } from "@/features/auth/auth-context";
import type {
  CompanyBusinessSettings as Settings,
  SelectedCompany,
} from "@/lib/auth/types";

type EditableSettings = Omit<Settings, "can_manage">;
const prefixPattern = /^[A-Z0-9](?:[A-Z0-9_-]{0,8}[A-Z0-9])?$/;

function messageFor(value: unknown) {
  return Array.isArray(value)
    ? String(value[0] ?? "Invalid value.")
    : String(value ?? "Invalid value.");
}

function editableSettings(settings: Settings): EditableSettings {
  return {
    default_currency: settings.default_currency,
    timezone: settings.timezone,
    invoice_number_prefix: settings.invoice_number_prefix,
    receipt_number_prefix: settings.receipt_number_prefix,
    credit_note_number_prefix: settings.credit_note_number_prefix,
    debit_note_number_prefix: settings.debit_note_number_prefix,
  };
}

function CompanyBusinessSettingsForm({
  company,
}: {
  company: SelectedCompany;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [draft, setDraft] = useState<EditableSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    fetch("/api/auth/company-business-settings")
      .then(async (response) => {
        const payload = (await response.json().catch(() => ({}))) as
          Settings | { message?: string };
        if (!active) return;
        if (!response.ok || !("default_currency" in payload)) {
          setError(
            "message" in payload && payload.message
              ? payload.message
              : "Company business settings could not be loaded.",
          );
          return;
        }
        setSettings(payload);
        setDraft(editableSettings(payload));
      })
      .catch(() => {
        if (active)
          setError("Company business settings are temporarily unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [company]);

  function update(field: keyof EditableSettings, value: string) {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
    setFieldErrors((current) => ({ ...current, [field]: "" }));
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !settings?.can_manage || pending) return;
    const normalized = {
      ...draft,
      default_currency: draft.default_currency.trim().toUpperCase(),
      timezone: draft.timezone.trim(),
      invoice_number_prefix: draft.invoice_number_prefix.trim().toUpperCase(),
      receipt_number_prefix: draft.receipt_number_prefix.trim().toUpperCase(),
      credit_note_number_prefix: draft.credit_note_number_prefix
        .trim()
        .toUpperCase(),
      debit_note_number_prefix: draft.debit_note_number_prefix
        .trim()
        .toUpperCase(),
    };
    const errors: Record<string, string> = {};
    if (!/^[A-Z]{3}$/.test(normalized.default_currency))
      errors.default_currency = "Enter a three-letter currency code.";
    if (!normalized.timezone) errors.timezone = "Enter an IANA timezone.";
    for (const field of [
      "invoice_number_prefix",
      "receipt_number_prefix",
      "credit_note_number_prefix",
      "debit_note_number_prefix",
    ] as const) {
      if (!prefixPattern.test(normalized[field]))
        errors[field] = "Enter a valid 1-10 character prefix.";
    }
    const prefixFields = [
      "invoice_number_prefix",
      "receipt_number_prefix",
      "credit_note_number_prefix",
      "debit_note_number_prefix",
    ] as const;
    for (const field of prefixFields) {
      if (
        prefixFields.some(
          (candidate) =>
            candidate !== field && normalized[candidate] === normalized[field],
        )
      )
        errors[field] = "Use a unique prefix for each document family.";
    }
    if (Object.keys(errors).length) {
      setFieldErrors(errors);
      return;
    }
    setPending(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/auth/company-business-settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(normalized),
      });
      const payload = (await response.json().catch(() => ({}))) as
        Settings | { message?: string; fieldErrors?: Record<string, unknown> };
      if (!response.ok || !("default_currency" in payload)) {
        setError(
          "message" in payload && payload.message
            ? payload.message
            : "Company business settings could not be saved.",
        );
        if ("fieldErrors" in payload)
          setFieldErrors(
            Object.fromEntries(
              Object.entries(payload.fieldErrors ?? {}).map(
                ([field, value]) => [field, messageFor(value)],
              ),
            ),
          );
        return;
      }
      setSettings(payload);
      setDraft(editableSettings(payload));
      setMessage("Company business settings saved.");
    } catch {
      setError("Company business settings are temporarily unavailable.");
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Company business settings"
        description={`Defaults and customer-facing numbering for ${company.display_name}.`}
      />
      <FormError message={error} />
      {loading ? (
        <p role="status">Loading Company business settings...</p>
      ) : null}
      {settings && !settings.can_manage ? (
        <div className="branding-readonly" role="status">
          You can view these settings, but you do not have permission to change
          them.
        </div>
      ) : null}
      {draft && settings ? (
        <form className="branding-form" onSubmit={submit} noValidate>
          <FormField
            id="company-default-currency"
            label="Default currency"
            value={draft.default_currency}
            maxLength={3}
            disabled={!settings.can_manage || pending}
            error={fieldErrors.default_currency}
            onChange={(event) => update("default_currency", event.target.value)}
          />
          <FormField
            id="company-timezone"
            label="Timezone"
            value={draft.timezone}
            maxLength={64}
            disabled={!settings.can_manage || pending}
            error={fieldErrors.timezone}
            onChange={(event) => update("timezone", event.target.value)}
          />
          {(
            [
              ["invoice_number_prefix", "Invoice prefix"],
              ["receipt_number_prefix", "Receipt prefix"],
              ["credit_note_number_prefix", "Credit note prefix"],
              ["debit_note_number_prefix", "Debit note prefix"],
            ] as const
          ).map(([field, label]) => (
            <FormField
              key={field}
              id={`company-${field}`}
              label={label}
              value={draft[field]}
              maxLength={10}
              disabled={!settings.can_manage || pending}
              error={fieldErrors[field]}
              onChange={(event) => update(field, event.target.value)}
            />
          ))}
          {message ? (
            <div className="form-success" role="status">
              {message}
            </div>
          ) : null}
          {settings.can_manage ? (
            <Button type="submit" disabled={pending}>
              {pending ? "Saving..." : "Save business settings"}
            </Button>
          ) : null}
        </form>
      ) : null}
    </>
  );
}

export function CompanyBusinessSettings() {
  const { company_context: context } = useAuth();
  const company = context.selected_company;
  if (!company)
    return (
      <section className="company-context-notice">
        <h1>No active Company</h1>
        <p>Select an active Company before viewing business settings.</p>
      </section>
    );
  return <CompanyBusinessSettingsForm key={company.id} company={company} />;
}
