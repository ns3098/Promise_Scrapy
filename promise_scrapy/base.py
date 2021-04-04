

"""Common definitions."""

from enum import Enum


class PromiseState(Enum):

    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    REJECTED = 'rejected'

    def __str__(self):
        """Print PromiseState."""
        return self.value


PENDING = PromiseState.PENDING
FULFILLED = PromiseState.FULFILLED
REJECTED = PromiseState.REJECTED
