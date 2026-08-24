class PatrolError(Exception):
    pass


class PatrolValidationError(PatrolError):
    pass


class PatrolPermissionError(PatrolError):
    pass
