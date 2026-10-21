import { OrderDetailPage } from "@/features/procurement/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <OrderDetailPage id={(await params).id} />;
}
