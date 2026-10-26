import { CourseDetailPage } from "@/features/people-operations/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <CourseDetailPage id={(await params).id} />;
}
