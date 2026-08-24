class ContractDomainError(Exception):
    pass


class InvalidContractTransition(ContractDomainError):
    pass


class ContractValidationError(ContractDomainError):
    pass


class ContractMakerCheckerViolation(ContractDomainError):
    pass
