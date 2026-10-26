import { CandidateDetailPage } from "@/features/people-operations/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <CandidateDetailPage id={(await params).id} />;
}
