import { InvoiceListPage } from "@/features/invoices/list-page";

export default async function InvoicesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const values = Object.fromEntries(
    Object.entries(raw).flatMap(([key, value]) =>
      typeof value === "string" ? [[key, value]] : [],
    ),
  );
  return <InvoiceListPage searchParams={values} />;
}
