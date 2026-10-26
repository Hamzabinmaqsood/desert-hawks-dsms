import { RequisitionDetailPage } from "@/features/people-operations/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <RequisitionDetailPage id={(await params).id} />;
}
