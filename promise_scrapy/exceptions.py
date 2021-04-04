

"""Exceptions."""

from traceback import format_tb


class PromiseRejection(RuntimeError):
    """Wrapper around a non-Exception rejection so that it can be raised."""

    def __init__(self, non_exc):
        """Create an Exception that allows a non-Exception rejection to be raised."""
        self.value = non_exc

    def __str__(self):
        """Print reason of rejection."""
        return self.__class__.__name__ + ': ' + str(self.value)


class PromiseAggregateError(RuntimeError):
    """PromiseAggregateError.

    Raised when the result of a Promise aggregation does not meet the requirements
    of the aggregation strategy, currently only used in `Promise.any`.
    """

    def __str__(self):
        """Print PromiseAggregateError."""
        return self.__class__.__name__ + ': No Promise in Promise.any was resolved.'


class StopEarly(GeneratorExit):
    """Signal an early exit of a promise aggregation, cancelling Promises that have not been evaluated."""

    pass


class PromiseException(Exception):
    """Base class for Exceptions indicating unexpected Promise behaviors."""

    pass


class PromisePending(PromiseException):
    """Attempted to access the value of a Promise when it is still PENDING."""

    def __init__(self, *args, **kwargs):
        super().__init__('Promise has not been settled.', *args, **kwargs)


class PromiseLocked(PromiseException):
    """Attempted to alter the state/value of a Promise when it is already settled (FULFILLED/REJECTED)."""

    def __init__(self, *args, **kwargs):
        super().__init__('Cannot change the state of an already settled Promise.', *args, **kwargs)


class HandlerNotCallableError(PromiseException, TypeError):
    """Attempted to use a non-callable value to create a generator function."""

    pass


class PromiseWarning(RuntimeWarning):
    """Base class for potentially unintended Promise effects that do not warrant an exception but are worth warned."""

    def _print_warning(self):
        return '%s: %s\n' % (self.__class__.__name__, self.__str__())


class AsyncPromiseWarning(PromiseWarning):
    """PromiseWarning related to asyncio."""

    pass


class UnhandledPromiseRejectionWarning(PromiseWarning):
    """Promise was rejected but there were no `on_reject` handlers reacting to the rejection when the Promise was evaluated."""

    def __init__(self, promise, *args, **kwargs):
        """Initialize warning with the Promise that was left rejected."""
        super().__init__(*args, **kwargs)
        self.promise = promise

    def _print_warning(self):
        reason = self.promise._value
        warn = self.__class__.__name__ + ': Unhandled Promise rejection: '
        if isinstance(reason, BaseException):
            tb = format_tb(reason.__traceback__)
            return (
                'Traceback (most recent call last):\n%s%s%s: %s\n  in %s\n'
                % (''.join(tb), warn, reason.__class__.__name__, str(reason), str(self.promise))
            )
        else:
            return '%s%s\n  in %s' % (warn, str(reason), str(self.promise))

    def __str__(self):
        return self.__class__.__name__ + ': ' + str(self.promise._value) + '\n'
