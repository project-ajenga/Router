from abc import ABC
from functools import partial
from ajenga.typing import Any
from ajenga.typing import AsyncIterable
from ajenga.typing import Awaitable
from ajenga.typing import Callable
from ajenga.typing import Dict
from ajenga.typing import Hashable
from ajenga.typing import Iterable
from ajenga.typing import Set
from ajenga.typing import Tuple
from ajenga.typing import Type
from ajenga.typing import final

from .exceptions import RouteException
from .exceptions import RouteInternalException
from .models import AbsNode
from .models import Graph
from .models import IdentityNode
from .models import Node
from .models import NonterminalNode
from .models import TerminalNode
from .keyfunc import KeyFunction
from .keyfunc import KeyFunctionImpl
from .keyfunc import KeyFunction_T
from .keyfunc import PredicateFunction_T
from .keyfunc import first_argument
from .keystore import KeyStore
from .utils import wrap_function
from .state import RouteState
from .models import RouteResult_T


class RawHandlerNode(TerminalNode, AbsNode):
    args: Tuple
    kwargs: Dict

    def __init__(self, func: Callable[..., Awaitable], *args, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def __repr__(self):
        return repr(self._func)

    def copy(self, node_map: Dict[Node, Node] = ...) -> "RawHandlerNode":
        return RawHandlerNode(self._func, *self._args, **self._kwargs)

    def __call__(self, *args, **kwargs):
        return self._func(*args, **kwargs)

    async def forward(self, *args, **kwargs) -> Any:
        return await self._func(*args, **kwargs)

    def debug_fmt(self, indent=1, verbose=False) -> str:
        if verbose:
            return f'{" ":{indent}}<Func {str(self)}: {self._func.__name__}>'
        else:
            return f'{" ":{indent}}<Func : {self._func.__name__}>'


@final
class HandlerNode(RawHandlerNode):
    args: Tuple
    kwargs: Dict

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__(wrap_function(func), *args, **kwargs)
        self._original_func = func

    def copy(self, node_map: Dict[Node, Node] = ...) -> "HandlerNode":
        return HandlerNode(self._original_func, *self._args, **self._kwargs)

    def __call__(self, *args, **kwargs):
        return self._original_func(*args, **kwargs)


class AbsNonterminalNode(NonterminalNode, AbsNode, ABC):
    """Nonterminal Node Implementation
    empty / open to contain terminals, or non-empty / closed

    To inherit this class, should override the following:
        route
        __init__
        copy <- new
        __id__
        clear
    """
    _successors: Dict[Any, Set[Node]]
    _empty: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._successors = {}
        self._empty = True

    def new(self) -> "AbsNonterminalNode":
        return type(self)()

    def copy(self, node_map: Dict[Node, Node] = ...) -> "AbsNonterminalNode":
        ret = self.new()
        if node_map is ...:
            node_map = {}
        for key, nodes in self._successors.items():
            if not nodes:
                ret.add_key(key)
            for node in nodes:
                ret._add_successor(key, node_map.setdefault(node, node.copy(node_map=node_map)))
        return ret

    @property
    def empty(self) -> bool:
        return self._empty

    def clear(self):
        self.__init__()

    @property
    def successors(self) -> Iterable[Node]:
        return set(node for nodes in self._successors.values() for node in nodes)

    def add_key(self, key):
        if not isinstance(key, Hashable):
            raise ValueError(f"Cannot add {type(key)} to {type(self)} as key of transition")
        if key not in self._successors:
            self._successors[key] = set()

    def add_successor(self, node):
        for key in self._successors:
            self._add_successor(key, node)

    def remove_successor(self, node):
        removed_keys = set()
        for key, nodes in self._successors.items():
            if node in nodes:
                nodes.remove(node)
            if not nodes:
                removed_keys.add(key)
        for key in removed_keys:
            del self._successors[key]

    def _add_successor(self, key, node: Node):
        self._empty = False
        if key not in self._successors:
            self._successors[key] = {node}
            node.add_predecessor((self, key))
        else:
            for u in self._successors[key]:
                if isinstance(u, NonterminalNode) and u == node:
                    u |= node
                    break
            else:
                self._successors[key].add(node)
                node.add_predecessor((self, key))

    def __ior__(self, other):
        if isinstance(other, AbsNonterminalNode):
            for key, nodes in other._successors.items():
                if not nodes:
                    self.add_key(key)
                for node in nodes:
                    self._add_successor(key, node)
            return self
        else:
            raise ValueError(f"Cannot apply operator ior between {type(self)} and {type(other)}")

    def debug_fmt(self, indent=1, verbose=False) -> str:
        out_str = ''
        for key, value in self._successors.items():
            prefix = f'{key}: '
            inner_str = '\n'.join(node.debug_fmt(indent=2) for node in value)
            inner_str = '\n'.join(map(lambda x: f'{" ":{indent + 2}}' + x, inner_str.split('\n')))
            out_str += f'{" ":{indent + 2}}{prefix}[ \n{inner_str} \n{" ":{indent + 2}}]' + '\n'
        if verbose:
            return f'{" ":{indent}}<{type(self).__name__} : \n{out_str}{" ":{indent}}>'
        else:
            return f'{" ":{indent}}<{type(self).__name__} {str(self)}: \n{out_str}{" ":{indent}}>'


class PredicateNode(AbsNonterminalNode):
    def __init__(self, *predicates: PredicateFunction_T):
        super().__init__()
        for predicate in predicates:
            if isinstance(predicate, KeyFunction):
                self.add_key(predicate)
            else:
                self.add_key(KeyFunctionImpl(predicate))

    async def _route(self, state: RouteState) -> Set[RouteResult_T]:
        res = set()
        for predicate, nodes in self._successors.items():
            try:
                pred_res = await state.store(predicate, state)
            except RouteException as e:
                res.add(e)
                continue
            except Exception as e:
                res.add(RouteInternalException(e))
                continue
            if pred_res:
                for node in nodes:
                    if isinstance(node, TerminalNode):
                        res.add(state.wrap(node))
                    elif isinstance(node, NonterminalNode):
                        res |= await node.route(state)
        return res

class EqualNode(AbsNonterminalNode):
    def __init__(self, *values, key: KeyFunction_T = first_argument, key_id=None):
        super().__init__()
        if isinstance(key, KeyFunction):
            self._key = key
        else:
            self._key = KeyFunctionImpl(key, id_=key_id)
        for value in values:
            self.add_key(value)

    @property
    def __id__(self) -> Hashable:
        return super(EqualNode, self).__id__, self._key.__id__

    def new(self) -> "EqualNode":
        return EqualNode(key=self._key)

    async def _route(self, state: RouteState) -> Set[RouteResult_T]:
        res = set()
        try:
            key = await state.store(self._key, state)
        except RouteException as e:
            return {e}
        except Exception as e:
            return {RouteInternalException(e)}

        if not isinstance(key, Hashable):
            raise ValueError(f'Key {key} to EqualNode must be Hashable!')

        if key not in self._successors:
            return res

        for node in self._successors[key]:
            if isinstance(node, TerminalNode):
                res.add(state.wrap(node))
            elif isinstance(node, NonterminalNode):
                res |= await node.route(state)
        return res


@final
class ProcessorNode(AbsNonterminalNode):
    def __init__(self, *processors: KeyFunction_T, **kwargs):
        super().__init__(**kwargs)
        for processor in processors:
            if isinstance(processor, KeyFunction):
                self.add_key(processor)
            else:
                self.add_key(KeyFunctionImpl(processor))

    async def _route(self, state: RouteState) -> Set[RouteResult_T]:
        res = set()
        for processor, nodes in self._successors.items():
            try:
                await state.store(processor, state)
            except RouteException as e:
                res.add(e)
            except Exception as e:
                res.add(RouteInternalException(e))
            for node in nodes:
                if isinstance(node, TerminalNode):
                    res.add(state.wrap(node))
                elif isinstance(node, NonterminalNode):
                    res |= await node.route(state)
        return res


def make_graph_deco(node_cls: Type[NonterminalNode]) -> Callable[..., Graph]:
    def deco(*args, **kwargs):
        return Graph() & node_cls(*args, **kwargs)

    return deco


true = make_graph_deco(IdentityNode)()
equals = make_graph_deco(EqualNode)
if_ = make_graph_deco(PredicateNode)
is_ = partial(make_graph_deco(EqualNode), key=KeyFunctionImpl(lambda _x_: type(_x_)))
process = make_graph_deco(ProcessorNode)


def store_(_name: str = None, _func: Callable = None, **kwargs) -> Graph:
    g = Graph()
    if _name and _func:
        g |= make_graph_deco(ProcessorNode)(KeyFunctionImpl(_func, key=_name))
    for name, func in kwargs.items():
        g |= make_graph_deco(ProcessorNode)(KeyFunctionImpl(func, key=name))
    return g


def handler(*args, **kwargs) -> Callable:
    def deco(func: Callable) -> HandlerNode:
        return HandlerNode(func, *args, **kwargs)

    return deco
