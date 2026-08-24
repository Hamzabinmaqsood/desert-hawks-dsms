def invoice_pdf_upload_to(instance: object, filename: str) -> str:
    company_id = getattr(instance, "company_id", "unknown")
    invoice_id = getattr(instance, "invoice_id", "unknown")
    revision = getattr(instance, "revision_number", 1)
    return f"billing/{company_id}/invoices/{invoice_id}/revision-{revision}.pdf"
