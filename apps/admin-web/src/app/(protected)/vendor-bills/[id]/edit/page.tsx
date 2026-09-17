import { VendorBillEditPage } from "@/features/vendor-bills/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <VendorBillEditPage id={(await params).id} />;
}
