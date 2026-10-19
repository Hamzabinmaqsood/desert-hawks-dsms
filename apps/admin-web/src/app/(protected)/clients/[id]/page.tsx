import { ClientDetailPage } from "@/features/client-contracts/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ClientDetailPage id={(await params).id} />;
}
