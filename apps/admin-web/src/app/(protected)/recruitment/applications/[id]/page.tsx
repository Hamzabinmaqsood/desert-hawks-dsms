import { ApplicationDetailPage } from "@/features/people-operations/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ApplicationDetailPage id={(await params).id} />;
}
