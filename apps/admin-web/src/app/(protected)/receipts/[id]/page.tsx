import { ReceiptDetailPage } from "@/features/receipts/pages";

export default async function ReceiptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ReceiptDetailPage id={(await params).id} />;
}
