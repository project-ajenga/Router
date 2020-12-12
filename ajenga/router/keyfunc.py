from abc import ABC
from ajenga.typing import Awaitable
from ajenga.typing import Callable
from ajenga.typing import Generic
from ajenga.typing import Hashable
from ajenga.typing import TypeVar
from ajenga.typing import Union

from .utils import wrap_function

T = TypeVar('T')


class KeyFunction(ABC, Generic[T]):
    def __init__(self, id_=None):
        self.___id___ = id_

    async def __call__(self, *args, **kwargs) -> T:
        raise NotImplementedError

    @property
    def key(self) -> "Union[Hashable, KeyFunction]":
        return self

    @property
    def __id__(self) -> Hashable:
        return self.___id___ or id(self)

    def __hash__(self):
        return self.__id__.__hash__()

    def __eq__(self, other):
        return isinstance(other, KeyFunction) and self.__id__ == other.__id__


class RawKeyFunctionImpl(KeyFunction[T]):
    def __init__(self, func: Callable[..., Awaitable[T]], *, key=None, id_=None):
        super().__init__(id_)
        self._func = func
        self._key = key

    async def __call__(self, *args, **kwargs) -> T:
        return await self._func(*args, **kwargs)

    @property
    def key(self) -> Union[Hashable, KeyFunction]:
        return self._key or self

    @property
    def __id__(self) -> Hashable:
        return self.___id___ or id(self._func)

    def __str__(self):
        return f'<{type(self).__name__}: {self._func}>'


class KeyFunctionImpl(RawKeyFunctionImpl[T]):
    def __init__(self, func: Callable[..., Union[Awaitable[T], T]], *, key=None, id_=None):
        super().__init__(wrap_function(func), key=key, id_=id_)


class PredicateFunction(KeyFunctionImpl[bool]):
    def __init__(self, func: Callable[..., Union[Awaitable[bool], bool]], *, id_=None, notation=None):
        super().__init__(func, id_=id_)
        self._notation = notation

    def __str__(self):
        if self._notation:
            return f'<{type(self).__name__}: {self._func} with {self._notation}>'
        else:
            return f'<{type(self).__name__}: {self._func}>'


KeyFunction_T = Union[KeyFunction[T], Callable[..., Union[Awaitable[T], T]]]
PredicateFunction_T = KeyFunction_T[bool]

first_argument = KeyFunctionImpl(lambda _x_: _x_)
