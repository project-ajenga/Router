import asyncio
import inspect
import typing
import warnings
from functools import wraps

from ajenga.typing import (TYPE_CHECKING, Any, AsyncIterable, Awaitable,
                           Callable, Collection, Coroutine, Dict, List, Union)

if TYPE_CHECKING:
    from .state import RouteState


T = typing.TypeVar("T")


class Alias:
    def __init__(self, name) -> None:
        self.name = name


def wrap_function(func: Callable[..., Union[Awaitable[T], T]]) -> Callable[..., Awaitable[T]]:
    _func = func
    _async = asyncio.iscoroutinefunction(func)

    # Generate signature
    sig = inspect.signature(func)
    _args_num = 0
    _args_extra = False
    _kwargs_binds = []

    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            _args_num += 1
        elif param.kind == inspect.Parameter.VAR_POSITIONAL:
            _args_extra = True
            _args_num += len(_kwargs_binds)
            _kwargs_binds.clear()
        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            if isinstance(param.default, Alias):
                _kwargs_binds.append((param.name, param.default.name))
            else:
                _kwargs_binds.append((param.name, param.name))
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            if isinstance(param.default, Alias):
                _kwargs_binds.append((param.name, param.default.name))
            else:
                _kwargs_binds.append((param.name, param.name))
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            warnings.warn("Variational keyword parameter is ignored in handler !")
        else:
            raise TypeError("Invalid parameter declaration !")

    @wraps(func)
    async def wrapper(state: "RouteState", mapping: Dict):

        if len(state.args) > _args_num and not _args_extra:
            kwargs_binds = _kwargs_binds[len(state.args) - _args_num:]
        else:
            kwargs_binds = _kwargs_binds

        kwargs = {}
        for name, key in kwargs_binds:
            if key in mapping:
                kwargs[name] = state.store[mapping[key]]
            elif key in state.store:
                kwargs[name] = state.store[key]
            else:
                raise TypeError(f"Keyword Parameter {key} not found in context !")

        return await _func(*state.args, **kwargs) if _async else _func(*state.args, **kwargs)

    return wrapper


async def run_async(func: Callable[[Any], Union[T, Awaitable[T]]], *args, **kwargs) -> T:
    return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)


def raise_(e: BaseException):
    raise e


async def consume_async_iterator(ait: AsyncIterable[T],
                                 collection_factory: Callable[..., Collection[T]] = list,
                                 collect_function: Callable[[Collection[T], T], Any] = list.append
                                 ) -> Collection[T]:
    collection = collection_factory()
    async for x in ait:
        collect_function(collection, x)
    return collection


async def gather(*coroutines: Coroutine, num_workers: int = 0, return_exceptions: bool = ...):
    if not num_workers:
        return await asyncio.gather(*coroutines, return_exceptions=return_exceptions)

    queue = asyncio.Queue(maxsize=num_workers)
    # lock = asyncio.Lock()
    index = 0
    result: List[Any] = [None] * len(coroutines)
    future = asyncio.Future()

    async def worker():
        while True:
            nonlocal index
            work = await queue.get()
            # async with lock:
            i = index
            index += 1
            try:
                result[i] = await work
            except Exception as e:
                if return_exceptions:
                    result[i] = e
                else:
                    future.set_exception(e)
                    queue.task_done()

            queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(num_workers)]

    for coroutine in coroutines:
        await asyncio.wait([queue.put(coroutine), future], return_when=asyncio.FIRST_COMPLETED)

    await asyncio.wait([queue.join(), future], return_when=asyncio.FIRST_COMPLETED)

    future.cancel()

    for w in workers:
        w.cancel()

    return result


async def as_completed(*coroutines: Coroutine,
                       num_workers: int = 0,
                       return_exceptions: bool = True,
                       ) -> AsyncIterable:
    pending = set()
    index = 0
    while True:
        while index < len(coroutines) and (not num_workers or len(pending) < num_workers):
            pending.add(coroutines[index])
            index += 1
        if pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() and return_exceptions:
                    yield task.exception()
                else:
                    yield await task
        else:
            break
