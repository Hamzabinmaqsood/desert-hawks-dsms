import { ContractDetailPage } from "@/features/client-contracts/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ContractDetailPage id={(await params).id} />;
}
