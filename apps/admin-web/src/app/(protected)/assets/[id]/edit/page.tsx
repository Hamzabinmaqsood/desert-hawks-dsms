import { AssetEditPage } from "@/features/assets/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <AssetEditPage id={(await params).id} />;
}
