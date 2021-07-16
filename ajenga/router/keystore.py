import asyncio
from ajenga.typing import Any
from ajenga.typing import Dict
from ajenga.typing import Hashable
from ajenga.typing import Mapping
from ajenga.typing import TypeVar
from ajenga.typing import Union

from .keyfunc import KeyFunction

T = TypeVar('T')


class KeyStore:
    _tasks: Dict[Union[Hashable, KeyFunction], asyncio.Task]
    _store: Dict[Union[Hashable, KeyFunction], Any]

    def __init__(self, items: Mapping = None):
        self._tasks = {}
        self._store = {}
        if items:
            self.update(items)

    async def __call__(self, _key_function: KeyFunction[T], state) -> T:
        if _key_function not in self._tasks:
            self._tasks[_key_function] = asyncio.ensure_future(_key_function(state, state.build()))
        task = self._tasks[_key_function]
        if task.done():
            return await task
        else:
            ret = await task
            self._store[_key_function] = ret
            if not isinstance(_key_function.key, KeyFunction):
                state[_key_function.key] = _key_function
            return ret

    def get(self, key: Union[Hashable, KeyFunction], default=None):
        return self._store.get(key, self._tasks.get(key, default))

    def update(self, other):
        self._store.update(other)

    def __getitem__(self, item):
        return self.get(item)

    def __setitem__(self, key, value):
        if isinstance(key, KeyFunction):
            raise TypeError('Cannot use KeyFunction in Keystore key!')
        self._store[key] = value

    def __contains__(self, item):
        return item in self._store

    def items(self):
        return self._store.items()


class NoneKeyStore(KeyStore):
    async def __call__(self, _key_function: KeyFunction[T], *args, **kwargs) -> T:
        return await _key_function(*args, **kwargs)
