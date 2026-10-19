export const PRODUCT_NAME = "Business Operations Platform";
export const PRODUCT_SHORT_NAME = "BOP";
export const PRODUCT_DESCRIPTION =
  "Modular business operations for growing Companies.";

export function tenantDocumentTitle(displayName?: string | null) {
  return displayName ? `${displayName} — ${PRODUCT_NAME}` : PRODUCT_NAME;
}

export const PLATFORM_DOCUMENT_TITLE = `Platform administration — ${PRODUCT_NAME}`;
