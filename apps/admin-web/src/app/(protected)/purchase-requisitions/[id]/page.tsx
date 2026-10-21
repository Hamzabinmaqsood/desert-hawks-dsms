import { RequisitionDetailPage } from "@/features/procurement/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <RequisitionDetailPage id={(await params).id} />;
}
