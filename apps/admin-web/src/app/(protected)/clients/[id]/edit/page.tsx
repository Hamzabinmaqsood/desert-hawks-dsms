import { ClientEditPage } from "@/features/client-contracts/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ClientEditPage id={(await params).id} />;
}
