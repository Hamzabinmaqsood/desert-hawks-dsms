import { VendorPaymentDetailPage } from "@/features/vendor-payments/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <VendorPaymentDetailPage id={(await params).id} />;
}
