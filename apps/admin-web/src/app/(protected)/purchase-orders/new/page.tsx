import { OrderCreatePage } from "@/features/procurement/pages";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ requisition?: string }>;
}) {
  return (
    <OrderCreatePage requisition={(await searchParams).requisition ?? ""} />
  );
}
