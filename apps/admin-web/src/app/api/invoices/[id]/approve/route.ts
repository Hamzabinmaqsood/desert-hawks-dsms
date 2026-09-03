import { invoiceWorkflowRoute } from "@/lib/api/workflow-route";

export const POST = invoiceWorkflowRoute(
  "approve",
  "The invoice could not be approved.",
);
