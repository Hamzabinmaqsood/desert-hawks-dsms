import { VendorDetailPage } from "@/features/vendors/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <VendorDetailPage id={(await params).id} />;
}
