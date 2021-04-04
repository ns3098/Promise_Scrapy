

"""Promise with asyncio."""

import asyncio
import warnings

from .exceptions import (AsyncPromiseWarning, PromiseException,
                         PromiseRejection, PromiseWarning)
from .promise import Promise as BasePromise
from .utils import one_line_warning_format

try:
    from .promise import PromiseType
except ImportError:
    pass


class Promise(BasePromise):

    @classmethod
    def _ensure_future(cls, item):
        try:
            return asyncio.ensure_future(item)
        except TypeError:
            future = asyncio.Future()
            future.set_result(item)
            return future

    async def awaitable(self):
        
        value = None
        while True:
            try:
                try:
                    value = await self._ensure_future(self.send(value))
                except asyncio.CancelledError:
                    break
                except BaseException as e:
                    value = self.throw(e)
            except StopIteration:
                break
        if self.is_fulfilled:
            return self._value
        elif self.is_rejected:
            reason = self.value
            if isinstance(reason, BaseException):
                raise reason
            raise PromiseRejection(reason)
        with one_line_warning_format():
            warnings.warn(AsyncPromiseWarning(
                'Future is done but Promise was not settled:\n%s'
                % self.__str__(),
            ))

    @classmethod
    async def _ensure_completion(cls, promise):
        try:
            return await promise.awaitable()
        except (PromiseException, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            pass

    @classmethod
    def _make_concurrent_executor(cls, this: PromiseType, promises):
        def executor(resolve, reject):
            futures = [asyncio.ensure_future(cls._ensure_completion(p)) for p in promises]
            awaitables = asyncio.as_completed(futures)
            yield from awaitables
        return executor

    @classmethod
    def _dispatch_aggregate_methods(cls, func, *promises, concurrently=False):
        promise = func(*promises)
        if not concurrently:
            return promise
        promise._prepare(cls._make_concurrent_executor(promise, promises))
        return promise

    @classmethod
    def all(cls, *args, **kwargs) -> PromiseType:
        
        return cls._dispatch_aggregate_methods(super().all, *args, **kwargs)

    @classmethod
    def race(cls, *args, **kwargs) -> PromiseType:
       
        return cls._dispatch_aggregate_methods(super().race, *args, **kwargs)

    @classmethod
    def all_settled(cls, *args, **kwargs) -> PromiseType:
        
        return cls._dispatch_aggregate_methods(super().all_settled, *args, **kwargs)

    @classmethod
    def any(cls, *args, **kwargs) -> PromiseType:
        
        return cls._dispatch_aggregate_methods(super().any, *args, **kwargs)

    async def _dispatch_async_gen_method(self, func, *args, **kwargs):
        try:
            item = self._dispatch_gen_method(func, *args, **kwargs)
        except StopIteration:
            raise StopAsyncIteration()
        try:
            future = asyncio.ensure_future(item)
        except TypeError:
            return item
        try:
            return await self.asend(await future)
        except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
            return await self.athrow(e)

    def __await__(self):
        return self.awaitable().__await__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._dispatch_async_gen_method(self._exec.__next__)

    async def asend(self, val):
        return await self._dispatch_async_gen_method(self._exec.send, val)

    async def athrow(self, typ, val=None, tb=None):
        return await self._dispatch_async_gen_method(self._exec.throw, typ, val, tb)

    async def aclose(self):
        try:
            i = await self.athrow(GeneratorExit)
            while True:
                try:
                    await asyncio.ensure_future(i)
                except TypeError:
                    raise RuntimeError('Generator cannot yield non-awaitables during exit.')
                i = await self.__anext__()
        except (GeneratorExit, StopAsyncIteration):
            pass
        else:
            raise RuntimeError('Generator ignored GeneratorExit')
