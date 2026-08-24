class AttendanceError(Exception):
    pass


class AttendancePermissionError(AttendanceError):
    pass


class AttendanceValidationError(AttendanceError):
    pass
