class SupervisionError(Exception):
    pass


class SupervisionValidationError(SupervisionError):
    pass


class SupervisionPermissionError(SupervisionError):
    pass
