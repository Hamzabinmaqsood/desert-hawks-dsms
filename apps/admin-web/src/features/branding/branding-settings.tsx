"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { useAuth } from "@/features/auth/auth-context";
import {
  isBrandColor,
  normalizeBrandColor,
  resolveCompanyBranding,
} from "@/lib/branding";
import type { CompanyBranding, SelectedCompany } from "@/lib/auth/types";

type EditableBranding = Pick<
  CompanyBranding,
  "display_name" | "tagline" | "primary_color" | "accent_color"
>;

function BrandingForm({ company }: { company: SelectedCompany }) {
  const router = useRouter();
  const branding = resolveCompanyBranding(company);
  const [draft, setDraft] = useState<EditableBranding>({
    display_name: branding.display_name,
    tagline: branding.tagline,
    primary_color: branding.primary_color,
    accent_color: branding.accent_color,
  });
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function update(field: keyof EditableBranding, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: "" }));
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!branding.can_manage || pending) return;
    const errors: Record<string, string> = {};
    if (!draft.display_name.trim())
      errors.display_name = "Enter a display name.";
    for (const field of ["primary_color", "accent_color"] as const) {
      if (!isBrandColor(draft[field]))
        errors[field] = "Enter a color in #RRGGBB format.";
    }
    if (Object.keys(errors).length) {
      setFieldErrors(errors);
      return;
    }
    setPending(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/auth/company-branding", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...draft,
          display_name: draft.display_name.trim(),
          tagline: draft.tagline.trim(),
          primary_color: normalizeBrandColor(draft.primary_color),
          accent_color: normalizeBrandColor(draft.accent_color),
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        message?: string;
        fieldErrors?: Record<string, string[] | string>;
      };
      if (!response.ok) {
        setError(payload.message ?? "Company branding could not be saved.");
        setFieldErrors(
          Object.fromEntries(
            Object.entries(payload.fieldErrors ?? {}).map(([field, value]) => [
              field,
              Array.isArray(value) ? (value[0] ?? "Invalid value.") : value,
            ]),
          ),
        );
        return;
      }
      setMessage("Company branding saved.");
      router.refresh();
    } catch {
      setError("Company branding is temporarily unavailable.");
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Company branding"
        description="Manage the selected Company’s safe display identity."
      />
      {!branding.can_manage ? (
        <div className="branding-readonly" role="status">
          You can view this branding, but you do not have permission to change
          it.
        </div>
      ) : null}
      <div className="branding-layout">
        <form className="branding-form" onSubmit={submit} noValidate>
          <FormField
            id="branding-display-name"
            label="Display name"
            value={draft.display_name}
            maxLength={255}
            disabled={!branding.can_manage || pending}
            error={fieldErrors.display_name}
            onChange={(event) => update("display_name", event.target.value)}
          />
          <FormField
            id="branding-tagline"
            label="Short tagline"
            value={draft.tagline}
            maxLength={160}
            disabled={!branding.can_manage || pending}
            error={fieldErrors.tagline}
            onChange={(event) => update("tagline", event.target.value)}
          />
          <FormField
            id="branding-primary-color"
            label="Primary color (#RRGGBB)"
            value={draft.primary_color}
            maxLength={7}
            pattern="#[0-9A-Fa-f]{6}"
            disabled={!branding.can_manage || pending}
            error={fieldErrors.primary_color}
            onChange={(event) => update("primary_color", event.target.value)}
          />
          <FormField
            id="branding-accent-color"
            label="Accent color (#RRGGBB)"
            value={draft.accent_color}
            maxLength={7}
            pattern="#[0-9A-Fa-f]{6}"
            disabled={!branding.can_manage || pending}
            error={fieldErrors.accent_color}
            onChange={(event) => update("accent_color", event.target.value)}
          />
          <FormError message={error} />
          {message ? (
            <div className="form-success" role="status">
              {message}
            </div>
          ) : null}
          {branding.can_manage ? (
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save branding"}
            </Button>
          ) : null}
        </form>
        <section className="branding-preview" aria-label="Branding preview">
          <div
            className="branding-preview-colors"
            style={{
              background: isBrandColor(draft.primary_color)
                ? normalizeBrandColor(draft.primary_color)
                : branding.primary_color,
              borderColor: isBrandColor(draft.accent_color)
                ? normalizeBrandColor(draft.accent_color)
                : branding.accent_color,
            }}
          />
          <small>Preview</small>
          <strong>{draft.display_name.trim() || branding.display_name}</strong>
          <span>{draft.tagline.trim() || "Digital Transformation System"}</span>
          <p>Colors are applied only to controlled decorative accents.</p>
        </section>
      </div>
    </>
  );
}

export function BrandingSettings() {
  const { company_context: context } = useAuth();
  const company = context.selected_company;
  if (!company)
    return (
      <section className="company-context-notice">
        <h1>No active Company</h1>
        <p>Select an active Company before viewing branding.</p>
      </section>
    );
  const branding = resolveCompanyBranding(company);
  return (
    <BrandingForm
      key={`${company.id}:${branding.display_name}:${branding.primary_color}:${branding.accent_color}`}
      company={company}
    />
  );
}
