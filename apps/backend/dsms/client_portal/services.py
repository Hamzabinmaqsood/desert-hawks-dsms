# mypy: disable-error-code="no-untyped-def,no-untyped-call"
import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4

from django.db import models, transaction
from django.utils import timezone

from dsms.identity.models import User

from .access import can_access_contract, can_access_site
from .models import (
    ClientPortalAuditEvent,
    ClientPortalInvitation,
    ClientPortalMembership,
    ClientServiceReport,
    ClientServiceReportAcknowledgement,
    ClientServiceRequest,
)
from .tenant_queries import active_memberships, consistent_reports


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


@transaction.atomic
def create_invitation(
    *, client, email, role, invited_by, client_contact=None, lifetime=timedelta(days=7)
):
    if not client.company.is_active:
        raise ValueError("An inactive company cannot invite portal users.")
    if not role.is_active:
        raise ValueError("An inactive portal role cannot be invited.")
    if client_contact and client_contact.client_id != client.id:
        raise ValueError("The portal contact belongs to another client.")
    token = secrets.token_urlsafe(32)
    invitation = ClientPortalInvitation.objects.create(
        client=client,
        email=email.strip().lower(),
        role=role,
        client_contact=client_contact,
        invitation_token_hash=_hash_token(token),
        invited_by=invited_by,
        invited_at=timezone.now(),
        expires_at=timezone.now() + lifetime,
    )
    ClientPortalAuditEvent.objects.create(
        client=client,
        actor_user=invited_by,
        event_type="INVITATION_CREATED",
        resource_type="ClientPortalInvitation",
        resource_id=invitation.id,
        occurred_at=timezone.now(),
    )
    return invitation, token


@transaction.atomic
def accept_client_portal_invitation(*, raw_token, password=None):
    token_hash = _hash_token(raw_token)
    invitation = (
        ClientPortalInvitation.objects.select_for_update()
        .select_related("client", "role")
        .filter(
            invitation_token_hash=token_hash,
            client__company__is_active=True,
            role__is_active=True,
        )
        .filter(
            models.Q(client_contact__isnull=True)
            | models.Q(client_contact__client_id=models.F("client_id"))
        )
        .first()
    )
    if not invitation or invitation.status != "PENDING" or invitation.revoked_at:
        raise ValueError("Invitation is invalid or no longer available.")
    if invitation.expires_at <= timezone.now():
        invitation.status = "EXPIRED"
        invitation.save(update_fields=["status"])
        raise ValueError("Invitation has expired.")
    user = User.objects.filter(email__iexact=invitation.email).first()
    if not user:
        if not password:
            raise ValueError("A password is required for a new portal account.")
        user = User.objects.create_user(email=invitation.email, password=password)
    if not user.is_active:
        raise ValueError("The user account is inactive.")
    membership, _ = ClientPortalMembership.objects.get_or_create(
        user=user,
        client=invitation.client,
        defaults={
            "role": invitation.role,
            "client_contact": invitation.client_contact,
            "status": "ACTIVE",
            "starts_at": timezone.now(),
            "activated_at": timezone.now(),
            "invited_by": invitation.invited_by,
        },
    )
    if membership.status != "ACTIVE":
        membership.role, membership.status, membership.activated_at = (
            invitation.role,
            "ACTIVE",
            timezone.now(),
        )
        membership.save()
    invitation.status, invitation.accepted_at = "ACCEPTED", timezone.now()
    invitation.save(update_fields=["status", "accepted_at"])
    ClientPortalAuditEvent.objects.create(
        client=invitation.client,
        membership=membership,
        actor_user=user,
        event_type="INVITATION_ACCEPTED",
        resource_type="ClientPortalInvitation",
        resource_id=invitation.id,
        occurred_at=timezone.now(),
    )
    return membership


@transaction.atomic
def create_service_request(
    *, membership, request_type, priority, title, description, site=None, contract=None
):
    if (
        membership.status != "ACTIVE"
        or not active_memberships(
            ClientPortalMembership.objects.filter(
                pk=membership.pk,
            )
        ).exists()
    ):
        raise ValueError("Active membership required.")
    if site and not can_access_site(membership, site):
        raise ValueError("Site is unavailable.")
    if contract and not can_access_contract(membership, contract):
        raise ValueError("Contract is unavailable.")
    request = ClientServiceRequest.objects.create(
        request_number=f"CSR-{timezone.now():%Y}-{uuid4().hex[:12].upper()}",
        client=membership.client,
        contract=contract,
        site=site,
        created_by_membership=membership,
        request_type=request_type,
        priority=priority,
        title=title,
        description=description,
    )
    ClientPortalAuditEvent.objects.create(
        client=membership.client,
        membership=membership,
        actor_user=membership.user,
        event_type="SERVICE_REQUEST_CREATED",
        resource_type="ClientServiceRequest",
        resource_id=request.id,
        occurred_at=timezone.now(),
    )
    return request


@transaction.atomic
def acknowledge_report(
    *,
    membership: ClientPortalMembership,
    report: ClientServiceReport,
    comments: str = "",
) -> ClientServiceReportAcknowledgement:
    if (
        not active_memberships(ClientPortalMembership.objects.filter(pk=membership.pk)).exists()
        or not consistent_reports(
            type(report).objects.filter(
                pk=report.pk,
                client_id=membership.client_id,
                status="PUBLISHED",
            )
        ).exists()
    ):
        raise ValueError("Published report is unavailable.")
    acknowledgement, _ = ClientServiceReportAcknowledgement.objects.get_or_create(
        report=report,
        membership=membership,
        defaults={"acknowledged_at": timezone.now(), "comments": comments},
    )
    return acknowledgement
