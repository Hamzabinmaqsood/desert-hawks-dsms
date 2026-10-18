import { SubscriptionDetailPage } from "@/features/platform/pages";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SubscriptionDetailPage subscriptionId={id} />;
}
