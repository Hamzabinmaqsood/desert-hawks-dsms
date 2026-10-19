import { EmployeeEditPage } from "@/features/people/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <EmployeeEditPage id={(await params).id} />;
}
