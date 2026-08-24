# mypy: disable-error-code="arg-type,misc"
from datetime import date

import pytest

from dsms.patrol.models import PatrolCheckpoint
from dsms.patrol.services import rotate_checkpoint_qr, verify_checkpoint_qr
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory

pytestmark = pytest.mark.django_db


def test_checkpoint_qr_rotation_hashes_secret_and_invalidates_old_credential() -> None:
    from dsms.contracts.models import Client, ClientIndustry, SecuritySite, ServiceContract

    branch = BranchFactory()
    actor = UserFactory()
    industry = ClientIndustry.objects.create(company=branch.company, code="PAT", name="Patrol")
    client = Client.objects.create(
        company=branch.company,
        client_code="PAT",
        legal_name="Patrol Client",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=branch.company,
        client=client,
        contract_number="PAT-CTR",
        contract_type="FIXED_TERM",
        title="Patrol",
        start_date=date.today(),
        status="ACTIVE",
        created_by=actor,
    )
    site = SecuritySite.objects.create(
        company=branch.company,
        client=client,
        contract=contract,
        site_code="PAT-SITE",
        name="Patrol Site",
        managing_branch=branch,
        address_line_1="Street",
        city_name="Islamabad",
        risk_level="HIGH",
        status="ACTIVE",
    )
    checkpoint = PatrolCheckpoint.objects.create(
        company=branch.company,
        client=client,
        site=site,
        checkpoint_code="rear-gate",
        name="Rear Gate",
        checkpoint_type="GATE",
    )
    first, first_token = rotate_checkpoint_qr(checkpoint=checkpoint, actor=actor)
    assert first_token not in first.token_hash
    assert verify_checkpoint_qr(credential=first, checkpoint=checkpoint, token=first_token)
    second, second_token = rotate_checkpoint_qr(checkpoint=checkpoint, actor=actor)
    first.refresh_from_db()
    assert not first.is_active
    assert not verify_checkpoint_qr(credential=first, checkpoint=checkpoint, token=first_token)
    assert verify_checkpoint_qr(credential=second, checkpoint=checkpoint, token=second_token)
    assert checkpoint.checkpoint_code == "REAR-GATE"
