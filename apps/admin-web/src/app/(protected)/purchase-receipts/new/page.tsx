import { ReceiptCreatePage } from "@/features/procurement/pages";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ purchase_order?: string }>;
}) {
  return (
    <ReceiptCreatePage
      purchaseOrder={(await searchParams).purchase_order ?? ""}
    />
  );
}
