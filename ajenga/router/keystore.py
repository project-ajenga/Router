import asyncio
from ajenga.typing import Any
from ajenga.typing import Dict
from ajenga.typing import Hashable
from ajenga.typing import Mapping
from ajenga.typing import TypeVar
from ajenga.typing import Union

from .keyfunc import KeyFunction

T = TypeVar('T')

KEY_ARGUMENT_STORE = '_store'


class KeyStore:
    _tasks: Dict[Union[Hashable, KeyFunction], Any]

    def __init__(self, items: Mapping = None):
        self._tasks = {}
        if items:
            self._tasks.update(items)
        self._tasks[KEY_ARGUMENT_STORE] = self

    async def __call__(self, _key_function: KeyFunction[T], *args, **kwargs) -> T:
        if _key_function not in self._tasks:
            self._tasks[_key_function] = asyncio.ensure_future(_key_function(*args, **kwargs))
        task = self._tasks[_key_function]
        if task.done():
            return await task
        else:
            ret = await task
            if not isinstance(_key_function.key, KeyFunction):
                self._tasks[_key_function.key] = ret
            return ret

    def get(self, key: Union[Hashable, KeyFunction], default=None):
        return self._tasks.get(key, default)

    def update(self, other):
        self._tasks.update(other)

    def __getitem__(self, item):
        return self.get(item)

    def __setitem__(self, key, value):
        if isinstance(key, KeyFunction):
            raise TypeError('Cannot use KeyFunction in Keystore key!')
        self._tasks[key] = value

    def __contains__(self, item):
        return item in self._tasks

    def items(self):
        return self._tasks.items()


class NoneKeyStore(KeyStore):
    async def __call__(self, _key_function: KeyFunction[T], *args, **kwargs) -> T:
        return await _key_function(*args, **kwargs)
