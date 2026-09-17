import { VendorEditPage } from "@/features/vendors/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <VendorEditPage id={(await params).id} />;
}
