import { invoiceWorkflowRoute } from "@/lib/api/workflow-route";

export const POST = invoiceWorkflowRoute(
  "issue",
  "The invoice could not be issued.",
);
