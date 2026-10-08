"use client";

import { useAuth } from "@/features/auth/auth-context";

export function CompanySwitcher() {
  const {
    company_context: context,
    switchingCompany,
    companySwitchError,
    switchCompany,
  } = useAuth();

  if (context.companies.length === 0) {
    return (
      <div className="company-switcher company-switcher-empty">
        <span>Active Company</span>
        <strong>No Company access</strong>
      </div>
    );
  }

  return (
    <div className="company-switcher">
      <label htmlFor="active-company">Active Company</label>
      <select
        id="active-company"
        value={context.selected_company?.id ?? ""}
        disabled={switchingCompany || context.companies.length === 1}
        onChange={(event) => void switchCompany(event.target.value)}
      >
        {!context.selected_company && (
          <option value="">Select a Company</option>
        )}
        {context.companies.map((company) => (
          <option key={company.id} value={company.id}>
            {company.code} — {company.display_name}
          </option>
        ))}
      </select>
      {switchingCompany && <small role="status">Switching Company…</small>}
      {companySwitchError && <small role="alert">{companySwitchError}</small>}
    </div>
  );
}
