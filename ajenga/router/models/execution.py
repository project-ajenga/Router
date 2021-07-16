import asyncio
import contextvars
import time
from abc import ABC
from asyncio import CancelledError
from ajenga.typing import AsyncIterable
from ajenga.typing import Optional
from ajenga.typing import Set

from ..pqueue import PriorityQueue


class Priority:
    """
    TODO: More complete priority
    Max
     |          Preprocess events or reject
    Pre
     |          Process then suspend
    Session
     |
     |          Free to process, free to suspend
     |
    Post
     |          Postprocess events even if suspended,
     |          will not execute if rejected
    Min
     |          Will never execute
    """
    Max = 100000
    Pre = 60000
    Session = 30000
    # ? Should session be in routing or in handler
    Wakeup = 29999
    Default = 0
    Post = -50000
    Min = -100000
    Never = -999999


class Task:
    args: tuple
    kwargs: dict
    state: dict

    def __init__(self, fn, *,
                 loop=None,
                 priority=Priority.Default,
                 state=None,
                 args=None,
                 kwargs=None,
                 **_kwargs) -> None:
        self.fn = fn
        self.loop = loop or asyncio.get_event_loop()
        self.priority = priority
        self.state = state or {}
        for key, value in _kwargs.items():
            setattr(self, key, value)

        self.args = args or ()
        self.kwargs = kwargs or {}

        self._task = None
        self.executor = None
        self.last_active_time = time.time()
        self._future_return = None
        self._future_pause = None
        self.cancelled = False

    def run(self, *args, **kwargs):
        if not args and not kwargs:
            args, kwargs = self.args, self.kwargs
        if self.running and self.paused:
            return self.resume(*args, **kwargs)
        elif self.running:
            raise InvalidStateError('Task is already running!')
        elif self.done:
            raise InvalidStateError('Task is already done!')

        async def _wrapper():
            token = _task_context.set(self)
            try:
                res = await self.fn(*args, **kwargs)
                if not self.cancelled:
                    self._future_return.set_result(res)
            except Exception as e:
                # print(f'? {e} {type(e)}')
                if not self.cancelled:
                    self._future_return.set_exception(e)
            finally:
                _task_context.reset(token)

        self.args = args
        self.kwargs = kwargs
        self.last_active_time = time.time()
        self.executor = _executor_context.get(None)
        self._future_return = self.loop.create_future()
        self._task = self.loop.create_task(_wrapper())
        return self._future_return

    @property
    def started(self):
        return bool(self._task)

    @property
    def done(self):
        return self._task and self._task.done()

    @property
    def running(self):
        return self._task and not self._task.done()

    @property
    def paused(self):
        return bool(self._future_pause)

    @property
    def cancelled(self):
        return self._cancelled or (self._task and self._task.cancelled())

    @cancelled.setter
    def cancelled(self, value):
        self._cancelled = value

    async def pause(self):
        # Check current context
        if _task_context.get() != self:
            raise InvalidStateError('Cannot pause a task from outside context!')
        elif self.cancelled:
            return

        self._future_pause = self.loop.create_future()
        self._future_return.set_exception(_PauseException(self))
        try:
            res = await self._future_pause
        except CancelledError:
            self.cancelled = True
            raise
        finally:
            self._future_pause = None
        return res

    def resume(self, *args, **kwargs):
        if not self.paused:
            raise InvalidStateError('Cannot resume a task which is not paused!')

        self.args = args
        self.kwargs = kwargs
        self.last_active_time = time.time()
        self.executor = _executor_context.get(None)
        self._future_return = self.loop.create_future()
        self._future_pause.set_result((args, kwargs))
        return self._future_return

    def raise_(self, exception):
        if not self.paused:
            raise InvalidStateError('Cannot raise a task which is not paused!')

        self.last_active_time = time.time()
        self.executor = _executor_context.get(None)
        self._future_return = self.loop.create_future()
        self._future_pause.set_exception(exception)
        return self._future_return

    @staticmethod
    def current() -> "Task":
        return _task_context.get()


class Executor(ABC):

    def create_task(self, fn, **kwargs) -> Task:
        raise NotImplementedError

    def add_task(self, task: Task):
        raise NotImplementedError

    async def run(self, *args, **kwargs) -> AsyncIterable:
        raise NotImplementedError
        yield

    @staticmethod
    def current() -> "Executor":
        return Task.current().executor


class SimpleExecutor(Executor):

    def __init__(self) -> None:
        self.tasks = []

    def create_task(self, fn, **kwargs):
        task = Task(fn, **kwargs)
        self.tasks.append(task)
        return task

    def add_task(self, task):
        self.tasks.append(task)

    async def run(self, *args, **kwargs):
        pending = [task.run(*args, **kwargs) for task in self.tasks]
        self.tasks.clear()
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for future in done:
                try:
                    yield await future
                except _PauseException:
                    pass
                except _ReturnException as e:
                    yield e.args[0] if e.args else None
                except Exception as e:
                    yield e


class PriorityExecutor(Executor):

    def __init__(self, max_workers=20) -> None:
        self.max_workers = max_workers
        self.waiting_tasks: PriorityQueue[Task, int] = PriorityQueue(lambda x: -x.priority)
        self.running_priority = Priority.Max
        self.running_futures: Set[asyncio.Future] = set()
        self.next_priority = True

    def create_task(self, fn, *, priority: int = 0, **kwargs):
        task = Task(fn, priority=priority, **kwargs)
        self.waiting_tasks.push(task)
        return task

    def add_task(self, task):
        self.waiting_tasks.push(task)

    @property
    def waiting_priority(self):
        return -self.waiting_tasks.top_key(-Priority.Never)

    async def run(self, *args, **kwargs):
        self.next_priority = True
        token = _executor_context.set(self)
        try:
            while self.waiting_tasks or self.running_futures:
                while self.waiting_tasks \
                        and len(self.running_futures) < self.max_workers \
                        and self.waiting_priority >= self.running_priority:
                    task = self.waiting_tasks.pop()
                    self.running_priority = task.priority
                    self.running_futures.add(task.run(*args, **kwargs))
                else:
                    if self.next_priority and self.waiting_priority > Priority.Never:
                        self.running_priority = self.waiting_priority

                        while self.waiting_tasks \
                                and len(self.running_futures) < self.max_workers \
                                and self.waiting_priority >= self.running_priority:
                            task = self.waiting_tasks.pop()
                            self.running_priority = task.priority
                            self.running_futures.add(task.run(*args, **kwargs))

                if not self.running_futures:
                    break

                done, self.running_futures = await asyncio.wait(self.running_futures,
                                                                return_when=asyncio.FIRST_COMPLETED)
                for future in done:
                    try:
                        yield await future
                    except _PauseException:
                        pass
                    except _ReturnException as e:
                        yield e.args[0] if e.args else None
                    except Exception as e:
                        yield e
        finally:
            _executor_context.reset(token)


_task_context: contextvars.ContextVar[Task] = contextvars.ContextVar('_task_context')
_executor_context: contextvars.ContextVar[Optional[Executor]] = contextvars.ContextVar('_executor_context')


class InvalidStateError(Exception):
    pass


class _ExecutorException(BaseException):
    pass


class _PauseException(_ExecutorException):
    pass


class _ReturnException(_ExecutorException):
    pass
