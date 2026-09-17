import { VendorBillDetailPage } from "@/features/vendor-bills/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <VendorBillDetailPage id={(await params).id} />;
}
