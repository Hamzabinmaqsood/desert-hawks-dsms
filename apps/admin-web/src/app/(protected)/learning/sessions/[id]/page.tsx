import { SessionDetailPage } from "@/features/people-operations/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <SessionDetailPage id={(await params).id} />;
}
