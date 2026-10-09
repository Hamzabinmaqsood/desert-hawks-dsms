import type { CompanyBranding, SelectedCompany } from "@/lib/auth/types";

export const DEFAULT_BRANDING: CompanyBranding = {
  display_name: "DSMS",
  tagline: "Digital Transformation System",
  primary_color: "#174D34",
  accent_color: "#D6A84F",
  can_manage: false,
};

export function resolveCompanyBranding(
  company: SelectedCompany | null,
): CompanyBranding {
  if (!company) return DEFAULT_BRANDING;
  return (
    company.branding ?? {
      ...DEFAULT_BRANDING,
      display_name: company.display_name,
    }
  );
}

export function normalizeBrandColor(value: string) {
  return value.trim().toUpperCase();
}

export function isBrandColor(value: string) {
  return /^#[0-9A-F]{6}$/.test(normalizeBrandColor(value));
}
