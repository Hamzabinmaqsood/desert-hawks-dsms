import { OrderEditPage } from "@/features/procurement/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <OrderEditPage id={(await params).id} />;
}
