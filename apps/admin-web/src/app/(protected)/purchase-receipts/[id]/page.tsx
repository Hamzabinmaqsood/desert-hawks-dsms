import { ReceiptDetailPage } from "@/features/procurement/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ReceiptDetailPage id={(await params).id} />;
}
