from django.db import models


class LeaveRequestStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCEL_REQUESTED = "CANCEL_REQUESTED", "Cancel requested"
    CANCELLED = "CANCELLED", "Cancelled"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    RECALLED = "RECALLED", "Recalled"


class TransactionType(models.TextChoices):
    OPENING = "OPENING", "Opening"
    ENTITLEMENT = "ENTITLEMENT", "Entitlement"
    ACCRUAL = "ACCRUAL", "Accrual"
    RESERVATION = "RESERVATION", "Reservation"
    RESERVATION_RELEASE = "RESERVATION_RELEASE", "Reservation release"
    LEAVE_TAKEN = "LEAVE_TAKEN", "Leave taken"
    ADJUSTMENT_CREDIT = "ADJUSTMENT_CREDIT", "Adjustment credit"
    ADJUSTMENT_DEBIT = "ADJUSTMENT_DEBIT", "Adjustment debit"
    CARRY_FORWARD = "CARRY_FORWARD", "Carry forward"
    EXPIRY = "EXPIRY", "Expiry"
    REVERSAL = "REVERSAL", "Reversal"
