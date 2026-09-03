import { InvoiceEditPage } from "@/features/invoices/edit-page";

export default async function InvoiceEditRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <InvoiceEditPage id={(await params).id} />;
}
