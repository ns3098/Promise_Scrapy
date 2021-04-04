
"""The Promise class."""

import warnings
from collections import deque
from inspect import isgenerator

from .base import FULFILLED, PENDING, REJECTED, PromiseState
from .exceptions import (PromiseAggregateError, PromiseException,
                         PromisePending, PromiseRejection, PromiseWarning,
                         UnhandledPromiseRejectionWarning)
from .utils import (_CachedGeneratorFunc, as_generator_func,
                    one_line_warning_format)

try:
    from typing import (Any, Callable, Generator, List, Optional, Tuple, Type,
                        TypeVar, Union)
    PromiseType = TypeVar('PromiseType', bound='Promise')
    NoReturnCallable = Callable[..., None]
    NoReturnGenerator = Generator[Any, Any, None]
    GeneratorFunc = Callable[..., NoReturnGenerator]
except ImportError:
    pass

warnings.simplefilter('always', UnhandledPromiseRejectionWarning)


def _passthrough(value):
    """Return the value unmodified.

    This is the default on-fulfillment handler.
    """
    return value


def _reraise(exc):
    """Re-raise the exception.

    This is the default on-rejection handler.
    """
    if isinstance(exc, BaseException):
        raise exc
    raise PromiseRejection(exc)


class Promise:

    def __init__(self, executor: Union[NoReturnCallable, GeneratorFunc], *, named=None):
       
        self._state: PromiseState = PENDING
        self._value: Any = None

        self.__qualname__ = '%s at %s' % (self.__class__.__name__, hex(id(self)))

        self._exec: NoReturnGenerator
        self._hash: int
        self._name: Optional[str] = None
        self._prepare(executor, named)

        self._resolvers: deque = deque()

    def _prepare(self, executor, named=None):
        self._exec = as_generator_func(executor)(self._make_resolution, self._make_rejection)
        self._hash = hash(self._exec)
        if not self._name or named:
            self._name = named or executor.__name__

    @property
    def state(self) -> PromiseState:
        """Return the state of the Promise."""
        return self._state

    @property
    def value(self) -> Any:
        
        if self._state is PENDING:
            raise PromisePending()
        return self._value

    @property
    def is_pending(self) -> bool:
        """Return True if the Promise's state is PENDING, and False otherwise."""
        return self._state is PENDING

    @property
    def is_settled(self) -> bool:
        """Return True if the Promise's state is either FULFILLED or REJECTED (settled)."""
        return self._state is not PENDING

    @property
    def is_fulfilled(self) -> bool:
        """Return True if the Promise's state is FULFILLED, and False otherwise."""
        return self._state is FULFILLED

    @property
    def is_rejected(self) -> bool:
        """Return True if the Promise's state is REJECTED, and False otherwise."""
        return self._state is REJECTED

    def get(self, default=None) -> Any:
        
        return self._value if self._value is not None else default

    def fulfilled(self, default=None) -> Any:
        """Return the value of the Promise if it is FULFILLED, otherwise return None."""
        if self._state is FULFILLED and self._value is not None:
            return self._value
        return default

    def rejected(self, default=None) -> Any:
        """Return the reason for rejection of the Promise if it is REJECTED, otherwise return None."""
        if self._state is REJECTED and self._value is not None:
            return self._value
        return default

    def is_rejected_due_to(self, exc_class) -> bool:
        """Check whether the Promise was rejected due to a specific type of exception.

        Return True if the Promise is REJECTED and its value is an instance of `exc_class`, and False in
        all other cases.
        """
        return self._state is REJECTED and isinstance(self._value, exc_class)

    def _add_resolver(self, resolver):
        """Add a new resolver to the resolver queue."""
        self._resolvers.append(resolver)

    def _make_resolution(self, value=None):
        """Begin fulfilling this Promise with `value`.

        This is the handler interface exposed to the executor.
        """
        yield from self._resolve_promise(self, value)

    def _make_rejection(self, reason=None):
        """Begin rejecting this Promise with `reason`.

        This is the handler interface exposed to the executor.
        """
        yield from self._reject(reason)

    def _resolve(self, value):
        """Actually fulfill the Promise, and begin processing resolvers."""
        if self._state is PENDING:
            self._state = FULFILLED
            self._value = value
        yield from self._run_resolvers()

    def _reject(self, reason):
        """Actually reject the Promise, and begin processing resolvers."""
        if self._state is PENDING:
            self._state = REJECTED
            if isinstance(reason, PromiseRejection):
                reason = reason.value
            self._value = reason
        yield from self._run_resolvers()

    def _run_resolvers(self):
        """Process resolvers."""
        if not self._resolvers and self._state is REJECTED:
            with one_line_warning_format():
                warnings.warn(UnhandledPromiseRejectionWarning(self))
            return
        while self._resolvers:
            yield from self._resolvers.popleft()(self)

    def _adopt(self, other: PromiseType):
        """Make this Promise copy the state and value of another Promise."""
        if other._state is FULFILLED:
            yield from self._resolve(other._value)
        if other._state is REJECTED:
            yield from self._reject(other._value)

    @classmethod
    def _resolve_promise(cls, this: PromiseType, returned: Any):
        """Follow the Promise Resolution Procedure in the Promise/A+ specification."""
        if this is returned:
            raise PromiseException() from TypeError('A Promise cannot resolve to itself.')

        if isinstance(returned, cls):
            yield from returned
            yield from returned.then(this._make_resolution, this._make_rejection)
            return returned

        if getattr(returned, 'then', None) and callable(returned.then):
            return (yield from cls._resolve_promise_like(this, returned))

        return (yield from this._resolve(returned))

    def _successor_executor(self, resolve=None, reject=None):
        """Executor to be used in Promises created with Promise.then(), etc."""
        if self._state is PENDING:
            yield from self
        else:
            yield from self._run_resolvers()

    def then(self: PromiseType, on_fulfill=_passthrough, on_reject=_reraise) -> PromiseType:
        
        cls: Type[PromiseType] = self.__class__
        promise = cls(
            self._successor_executor,
            named='%s|%s,%s' % (self._name, on_fulfill.__name__, on_reject.__name__),
        )
        handlers = {
            FULFILLED: _CachedGeneratorFunc(on_fulfill),
            REJECTED: _CachedGeneratorFunc(on_reject),
        }

        def resolver(settled: PromiseType):
            try:
                handler = handlers[settled._state](settled._value)
                yield from handler
                yield from self._resolve_promise(promise, handler.result)
            except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e:
                yield from promise._reject(e)
        self._add_resolver(resolver)

        return promise

    def catch(self, on_reject=_reraise) -> PromiseType:
        
        return self.then(_passthrough, on_reject)

    def finally_(self: PromiseType, on_settle=lambda: None) -> PromiseType:
        
        cls: Type[PromiseType] = self.__class__
        promise = cls(self._successor_executor, named='chained:%s' % self._name)
        on_settle = _CachedGeneratorFunc(on_settle)

        def resolver(settled: PromiseType):
            try:
                yield from on_settle()
                yield from promise._adopt(self)
            except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e:
                yield from promise._reject(e)
        self._add_resolver(resolver)

        return promise

    @classmethod
    def resolve(cls: Type[PromiseType], value=None) -> PromiseType:
        """Return a Promise that is already FULFILLED with `value`.

        If the `value` is another Promise, this Promise will adopt the state and value of that Promise.
        """
        return cls(lambda resolve, _: (yield from resolve(value)))

    @classmethod
    def reject(cls: Type[PromiseType], reason=None) -> PromiseType:
        """Return a Promise that is already REJECTED with `reason`."""
        return cls(lambda _, reject: (yield from reject(reason)))

    @classmethod
    def settle(cls, promise: PromiseType) -> PromiseType:
        """Run the Promise until it's settled.

        All intermediate values are discarded.
        """
        if not isinstance(promise, cls):
            raise TypeError(type(promise))
        for i in promise:
            pass
        return promise

    @classmethod
    def _make_multi_executor(cls, promises):
        def executor(resolve, reject):
            for p in promises:
                yield from p._successor_executor()
        return executor

    @classmethod
    def _ensure_promise(cls, promises):
        for p in promises:
            if not isinstance(p, cls):
                raise TypeError('%s is not an instance of %s' % (repr(p), repr(cls)))

    @classmethod
    def all(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        
        cls._ensure_promise(promises)
        fulfillments = {}
        promise = cls(cls._make_multi_executor(promises), named='Promise.all')

        def resolver(settled: PromiseType):
            if settled._state is REJECTED:
                yield from promise._reject(settled._value)
            fulfillments[settled] = settled._value
            if len(fulfillments) == len(promises):
                results = [fulfillments[p] for p in promises]
                yield from promise._resolve(results)

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def race(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        
        cls._ensure_promise(promises)
        promise = cls(cls._make_multi_executor(promises), named='Promise.race')

        def resolver(settled: PromiseType):
            yield from promise._adopt(settled)

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def all_settled(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        """Return a new Promise that fulfills when all the Promises have settled i.e. either FULFILLED or REJECTED.

        This Promise always fulfills with the list of Promises provided.
        """
        cls._ensure_promise(promises)
        settle_count = 0
        promise = cls(cls._make_multi_executor(promises), named='Promise.all_settled')

        def resolver(settled: PromiseType):
            nonlocal settle_count
            settle_count += 1
            if settle_count == len(promises):
                yield from promise._resolve(promises)

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def any(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        """Return a new Promise that ignore rejections among the provided Promises and fulfills upon the first fulfillment.

        If all Promises reject, it will reject with a PromiseAggregateError.

        Note
        ----
        - All Promises are evaluated regardless of fulfillments.
        """
        cls._ensure_promise(promises)
        settle_count = 0
        promise = cls(cls._make_multi_executor(promises), named='Promise.any')

        def resolver(settled: PromiseType):
            nonlocal settle_count
            settle_count += 1
            if settled._state is FULFILLED:
                yield from promise._adopt(settled)
            if settle_count == len(promises) and promise.is_pending:
                yield from promise._reject(PromiseAggregateError())

        for p in promises:
            p._add_resolver(resolver)
        return promise

    def __iter__(self):
        """Return self as the iterable."""
        return self

    def __next__(self):
        return self._dispatch_gen_method(self._exec.__next__)

    def send(self, value):
        return self._dispatch_gen_method(self._exec.send, value)

    def throw(self, typ, val=None, tb=None):
        return self._dispatch_gen_method(self._exec.throw, typ, val, tb)

    def close(self):
        try:
            self.throw(GeneratorExit)
        except (GeneratorExit, StopIteration):
            pass
        else:
            raise RuntimeError('Generator ignored GeneratorExit')

    def _dispatch_gen_method(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (PromiseException, PromiseWarning, StopIteration, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
            self._exec = self._reject(e)
            return self._dispatch_gen_method(self._exec.__next__)

    def __eq__(self, value):
        """Implement == (equality testing).

        Rules:
        -----
        - All PENDING Promises test unequal to all other Promises.
        - Two Promises are equal if they have the same state and their values test equal; if one or both of
        the values do not implement __eq__, return False.
        - Promises do not need to have the same executor to be considered equal.
        """
        try:
            return (
                self.__class__ is value.__class__
                and self._state is not PENDING
                and self._state is value._state
                and self._value == value._value
            )
        except NotImplementedError:
            return False

    def __hash__(self):
        """Implement hashing.

        The hash is produced by hashing the combination (tuple) the Promise class and the hash of the
        executor function.
        """
        return hash((self.__class__, self._hash))

    def __str__(self):
        s1 = "<Promise '%s' at %s (%s)" % (self._name, hex(id(self)), self._state.value)
        if self._state is PENDING:
            return s1 + '>'
        elif self._state is FULFILLED:
            return s1 + ' => ' + str(self._value) + '>'
        else:
            return s1 + ' => ' + repr(self._value) + '>'

    def __repr__(self):
        return '<%s %s at %s (%s): %s>' % (
            self.__class__.__name__, repr(self._exec), hex(id(self)),
            self._state.value, repr(self._value),
        )

    @property
    def __name__(self):
        return self.__str__()

    @classmethod
    def _resolve_promise_like(cls, this: PromiseType, obj):
        calls: List[Tuple[PromiseState, Any]] = []

        def on_fulfill(val):
            calls.append((FULFILLED, val))

        def on_reject(reason):
            calls.append((REJECTED, reason))

        try:
            promise = obj.then(on_fulfill, on_reject)
            if isgenerator(obj):
                yield from promise
        except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
            if not calls:
                calls.append((REJECTED, e))
        finally:
            if not calls:
                return (yield from this._resolve(obj))
            state, value = calls[0]
            if state is FULFILLED:
                return (yield from this._resolve(value))
            return (yield from this._reject(value))

    def _not_async(self, *args, **kwargs):
        raise NotImplementedError(
            '%s is not async-compatible.\n'
            'To enable async functionality, use promise_scrapy.async_.Promise'
            % (repr(self.__class__)),
        )

    def __getattr__(self, name):
        if name in {'awaitable', '__await__', '__aiter__', '__anext__', 'asend', 'athrow', 'aclose'}:
            return self._not_async
        return object.__getattribute__(self, name)
