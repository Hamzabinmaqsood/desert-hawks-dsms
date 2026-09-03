import { InvoiceDetailPage } from "@/features/invoices/detail-page";

export default async function InvoicePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <InvoiceDetailPage id={(await params).id} />;
}
