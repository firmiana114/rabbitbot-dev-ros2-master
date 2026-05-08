from enum import Enum


class MoveType(Enum):
    STOP = 0
    FORWARD = 1
    LEFT = 2
    RIGHT = 3


class NavigationStatus(Enum):
    PENDING = 0
    ACTIVE = 1
    PREEMPTED = 2
    SUCCEEDED = 3
    ABORTED = 4
    MID = 99
