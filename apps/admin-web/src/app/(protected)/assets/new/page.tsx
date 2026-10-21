import { AssetRegistrationPage } from "@/features/assets/pages";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ receipt?: string }>;
}) {
  return (
    <AssetRegistrationPage
      initialReceipt={(await searchParams).receipt ?? ""}
    />
  );
}
