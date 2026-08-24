class IncidentError(Exception):
    pass


class IncidentValidationError(IncidentError):
    pass


class IncidentPermissionError(IncidentError):
    pass
