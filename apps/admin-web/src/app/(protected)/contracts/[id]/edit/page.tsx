import { ContractEditPage } from "@/features/client-contracts/pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ContractEditPage id={(await params).id} />;
}
