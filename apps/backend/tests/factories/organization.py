import factory
from factory.django import DjangoModelFactory

from dsms.organization.enums import DepartmentScope
from dsms.organization.models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)


class CompanyFactory(DjangoModelFactory[Company]):
    class Meta:
        model = Company

    code = factory.Sequence(lambda n: f"CO{n:04d}")
    legal_name = factory.Sequence(lambda n: f"Company Legal Name {n}")
    trade_name = factory.Sequence(lambda n: f"Company Trade Name {n}")


class RegionFactory(DjangoModelFactory[Region]):
    class Meta:
        model = Region

    company: Company = factory.SubFactory(CompanyFactory)  # type: ignore[assignment]
    code = factory.Sequence(lambda n: f"REG{n:04d}")
    name = factory.Sequence(lambda n: f"Region {n}")


class CityFactory(DjangoModelFactory[City]):
    class Meta:
        model = City

    region: Region = factory.SubFactory(RegionFactory)  # type: ignore[assignment]
    company: Company = factory.LazyAttribute(lambda o: o.region.company)  # type: ignore[assignment]
    code = factory.Sequence(lambda n: f"CTY{n:04d}")
    name = factory.Sequence(lambda n: f"City {n}")
    province_or_state = "Punjab"


class BranchFactory(DjangoModelFactory[Branch]):
    class Meta:
        model = Branch

    region: Region = factory.SubFactory(RegionFactory)  # type: ignore[assignment]
    company: Company = factory.LazyAttribute(lambda o: o.region.company)  # type: ignore[assignment]
    city: City = factory.LazyAttribute(  # type: ignore[assignment]
        lambda o: CityFactory.create(region=o.region, company=o.region.company)
    )
    code = factory.Sequence(lambda n: f"BR{n:04d}")
    name = factory.Sequence(lambda n: f"Branch {n}")
    address_line_1 = "123 Main Street"


class DepartmentFactory(DjangoModelFactory[Department]):
    class Meta:
        model = Department

    company: Company = factory.SubFactory(CompanyFactory)  # type: ignore[assignment]
    code = factory.Sequence(lambda n: f"DEPT{n:04d}")
    name = factory.Sequence(lambda n: f"Department {n}")
    scope = DepartmentScope.COMPANY


class DesignationFactory(DjangoModelFactory[Designation]):
    class Meta:
        model = Designation

    company: Company = factory.SubFactory(CompanyFactory)  # type: ignore[assignment]
    code = factory.Sequence(lambda n: f"DSG{n:04d}")
    name = factory.Sequence(lambda n: f"Designation {n}")
    level = factory.Sequence(lambda n: n + 1)


class OperationalZoneFactory(DjangoModelFactory[OperationalZone]):
    class Meta:
        model = OperationalZone

    branch: Branch = factory.SubFactory(BranchFactory)  # type: ignore[assignment]
    company: Company = factory.LazyAttribute(lambda o: o.branch.company)  # type: ignore[assignment]
    code = factory.Sequence(lambda n: f"ZN{n:04d}")
    name = factory.Sequence(lambda n: f"Zone {n}")
