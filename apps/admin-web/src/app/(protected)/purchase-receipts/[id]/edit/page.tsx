import { ReceiptEditPage } from "@/features/procurement/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ReceiptEditPage id={(await params).id} />;
}
