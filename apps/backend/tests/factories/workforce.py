from datetime import date

import factory
from factory.django import DjangoModelFactory

from dsms.organization.models import Company
from dsms.workforce.enums import EmployeeType, EmploymentStatus, EmploymentType
from dsms.workforce.models import Employee
from tests.factories.organization import CompanyFactory


class EmployeeFactory(DjangoModelFactory[Employee]):
    class Meta:
        model = Employee

    company: Company = factory.SubFactory(CompanyFactory)  # type: ignore[assignment]
    employee_number = factory.Sequence(lambda n: f"DH-{n:06d}")
    first_name = "Ahmed"
    last_name = "Khan"
    mobile_number = "+923001234567"
    employee_type = EmployeeType.SECURITY_GUARD
    employment_type = EmploymentType.PERMANENT
    employment_status = EmploymentStatus.DRAFT
    joining_date = date(2026, 1, 1)
