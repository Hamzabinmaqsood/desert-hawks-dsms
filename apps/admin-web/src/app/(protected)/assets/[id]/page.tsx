import { AssetDetailPage } from "@/features/assets/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <AssetDetailPage id={(await params).id} />;
}
