from dataclasses import dataclass, field
from typing import Any, Tuple, List, Dict, TYPE_CHECKING
from .keystore import KeyStore

if TYPE_CHECKING:
    from .models import TerminalNode


@dataclass
class RouteState:
    args: Tuple
    store: KeyStore
    keystack: List[Dict] = field(default_factory=list)


    def __enter__(self):
        self.keystack.append({})
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.keystack.pop()

    def __setitem__(self, key, value):
        self.keystack[-1][key] = value

    def build(self):
        res = {}
        for km in self.keystack:
            res.update(km)
        return res

    def wrap(self, node):
        return RouteResult(node, self.build())


@dataclass
class RouteResult:
    node: "TerminalNode"
    mapping: Dict = field(hash=False, compare=False)

    def __hash__(self) -> int:
        return self.node.__hash__()

    def __eq__(self, o: object) -> bool:
        return isinstance(o, RouteResult) and self.node == o.node

