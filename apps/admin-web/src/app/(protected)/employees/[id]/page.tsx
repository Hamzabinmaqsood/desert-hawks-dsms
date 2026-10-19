import { EmployeeDetailPage } from "@/features/people/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <EmployeeDetailPage id={(await params).id} />;
}
