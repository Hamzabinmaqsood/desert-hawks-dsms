import { RequisitionEditPage } from "@/features/procurement/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <RequisitionEditPage id={(await params).id} />;
}
