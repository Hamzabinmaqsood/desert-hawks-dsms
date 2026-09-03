export function formatMoney(value: string, currency: string) {
  const safeDecimal = /^-?\d+(\.\d+)?$/.test(value) ? Number(value) : null;
  if (safeDecimal === null || !Number.isFinite(safeDecimal))
    return `${currency} ${value}`;
  return new Intl.NumberFormat("en-PK", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    minimumFractionDigits: 2,
  }).format(safeDecimal);
}

export function formatDate(value: string | null) {
  if (!value) return "—";
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("en-PK", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatTimestamp(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-PK", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
