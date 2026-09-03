import { invoiceWorkflowRoute } from "@/lib/api/workflow-route";

export const POST = invoiceWorkflowRoute(
  "submit",
  "The invoice could not be submitted for review.",
);
