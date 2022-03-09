import heapq
from dataclasses import dataclass, field
from itertools import starmap

from ajenga.typing import Callable, Generic, Iterable, List, TypeVar

_VT = TypeVar('_VT')
_KT = TypeVar('_KT')


class PriorityQueue(Generic[_VT, _KT]):
    @dataclass(order=True)
    class PriorityQueueEntry(Generic[_VT, _KT]):
        key: _KT
        value: _VT = field(compare=False)

    def __init__(self, key_func: Callable[[_VT], _KT]):
        self._container: List[PriorityQueue.PriorityQueueEntry[_VT, _KT]] = []
        self._key_func = key_func

    def top(self, default: _VT = None):
        return self._container[0].value if self._container else default

    def top_key(self, default: _KT = None):
        return self._container[0].key if self._container else default

    def pop(self) -> _VT:
        return heapq.heappop(self._container).value

    def push(self, item: _VT) -> None:
        heapq.heappush(self._container, self.PriorityQueueEntry(self._key_func(item), item))

    def remove(self, item: _VT):
        self._container.remove(self.PriorityQueueEntry(self._key_func(item), item))

    def extend(self, items: Iterable[_VT]) -> None:
        for item in items:
            self.push(item)

    def __bool__(self):
        return bool(self._container)

    def __len__(self):
        return len(self._container)

    def __iter__(self):
        return iter(starmap(lambda _entry: _entry.value, self._container))
