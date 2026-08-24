class DeploymentError(Exception):
    pass


class IneligibleEmployee(DeploymentError):
    pass


class AssignmentConflict(DeploymentError):
    pass


class RosterTransitionError(DeploymentError):
    pass
