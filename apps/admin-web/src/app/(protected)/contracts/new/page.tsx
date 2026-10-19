import { ContractCreatePage } from "@/features/client-contracts/pages";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ client?: string }>;
}) {
  return <ContractCreatePage initialClient={(await searchParams).client} />;
}
