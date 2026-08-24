class RecruitmentError(Exception):
    """Base recruitment domain error."""


class InvalidTransition(RecruitmentError):
    pass


class MakerCheckerViolation(RecruitmentError):
    pass


class HiringConflict(RecruitmentError):
    pass


class RecruitmentValidationError(RecruitmentError):
    pass
