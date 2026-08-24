class TrainingError(Exception):
    """Base training-domain error."""


class TrainingValidationError(TrainingError):
    pass


class InvalidTrainingTransition(TrainingError):
    pass


class CapacityExceeded(TrainingError):
    pass
