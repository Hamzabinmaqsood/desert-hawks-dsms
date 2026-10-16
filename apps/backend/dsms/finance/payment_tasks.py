from celery import shared_task

from dsms.subscriptions.enforcement import ModuleNotEnabled

from .payment_models import PaymentBatch, PaymentInstructionStatus
from .payment_services import process_payment_instruction, require_payment_origin


@shared_task  # type: ignore[untyped-decorator]
def process_payment_instruction_task(instruction_id: str) -> str:
    from .payment_models import PaymentInstruction

    item = PaymentInstruction.objects.get(pk=instruction_id)
    try:
        return process_payment_instruction(instruction=item).status
    except ModuleNotEnabled:
        return "SKIPPED_MODULE_NOT_ENABLED"


@shared_task  # type: ignore[untyped-decorator]
def process_payment_batch_task(batch_id: str, chunk_size: int = 100) -> int:
    batch = PaymentBatch.objects.get(pk=batch_id)
    try:
        require_payment_origin(batch)
    except ModuleNotEnabled:
        return 0
    ids = list(
        batch.instructions.filter(status=PaymentInstructionStatus.QUEUED).values_list(
            "id", flat=True
        )[:chunk_size]
    )
    for instruction_id in ids:
        process_payment_instruction_task.delay(str(instruction_id))
    return len(ids)
