

"""Utility functions."""

import warnings
from contextlib import contextmanager
from functools import wraps
from inspect import isgeneratorfunction

from .base import REJECTED
from .exceptions import (HandlerNotCallableError,
                         UnhandledPromiseRejectionWarning)


class _CachedGeneratorFunc:

    class _CachedGenerator:
        """A wrapper around a regular or generator function that retains the return value of the wrapped function."""

        def __init__(self, func, *args, **kwargs):
            """Init with a function and any args/kwargs that it requires."""
            self._func = func
            self._result = None
            self._finished = False

            self._func_is_generator = isgeneratorfunction(func)
            if self._func_is_generator:
                self._func = self._func(*args, **kwargs)
            else:
                self._args = args
                self._kwargs = kwargs

        def __iter__(self):
            return self

        def __next__(self):
            if not self._finished:
                if not self._func_is_generator:
                    self._result = self._func(*self._args, **self._kwargs)
                else:
                    try:
                        return next(self._func)
                    except StopIteration as stop:
                        self._result = stop.value
                self._finished = True
            raise StopIteration(self._result)

        def send(self, value):
            if self._func_is_generator:
                return self._func.send(value)
            raise StopIteration(self._result)

        def throw(self, typ, val=None, tb=None):
            if self._func_is_generator:
                return self._func.throw(typ, val, tb)
            if val is None:
                if tb is None:
                    raise typ
                val = typ()
            if tb is not None:
                val = val.with_traceback(tb)
            raise val

        def close(self):
            try:
                self.throw(GeneratorExit)
            except (GeneratorExit, StopIteration):
                pass
            else:
                raise RuntimeError('Generator ignored GeneratorExit')

        @property
        def result(self):
            """Return the return value of the function.

            If the function has not been run or has not finished running, raise a ValueError.
            """
            if not self._finished:
                raise ValueError('Generator has not been run.')
            return self._result

    def __init__(self, func):
        """Init with a callable.

        If the callable is a regular function, the generators this produces will
        immediately raise StopIteration with the return value when iterated over.
        """
        if not callable(func):
            raise HandlerNotCallableError(repr(func) + ' is not callable.')
        if isinstance(func, self.__class__):
            self._func = func._func
        else:
            self._func = func

    def __call__(self, *args, **kwargs):
        """Produce a generator."""
        return self._CachedGenerator(self._func, *args, **kwargs)

    @classmethod
    def wrap(cls, func):
        """Decorate a function turning it into a Cached Generator Function."""
        return wraps(func)(cls(func))


def as_generator_func(func):
    """Turn a regular function into a generator function, whose generator will yield the return value of the function.

    If the function passed is already a generator function, return it as-is.
    """
    if isgeneratorfunction(func):
        return func

    @wraps(func)
    def gen(*args, **kwargs):
        yield func(*args, **kwargs)
    return gen


def _formatwarning(message, category, filename, lineno, file=None, line=None):
    return message._print_warning()


@contextmanager
def one_line_warning_format():
    """Temporarily change warning format."""
    fmt = warnings.formatwarning
    warnings.formatwarning = _formatwarning
    try:
        yield
    finally:
        warnings.formatwarning = fmt


@as_generator_func
def _unhandled_rejection_warning(promise):
    if promise._warn_unhandled and promise._state is REJECTED:
        with one_line_warning_format():
            warnings.warn(UnhandledPromiseRejectionWarning(promise))
