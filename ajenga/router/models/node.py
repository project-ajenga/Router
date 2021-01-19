from abc import ABC
from ajenga.typing import Any
from ajenga.typing import AsyncIterable
from ajenga.typing import Dict
from ajenga.typing import Hashable
from ajenga.typing import Iterable
from ajenga.typing import Set
from ajenga.typing import Tuple
from ajenga.typing import final, TYPE_CHECKING

from ..state import RouteState
from . import RouteResult_T


class Node(ABC):
    """Abstraction class for Node
    """

    @property
    def __id__(self) -> Hashable:
        """Identity for node

        Used for merging two equal nodes

        :return: Hashable id_
        """
        return type(self).__name__

    def copy(self, **kwargs) -> "Node":
        """Copy of node

        :param kwargs: For internal use
        :return: Copy
        """
        raise NotImplementedError

    @property
    def predecessors(self) -> "Set[Tuple[NonterminalNode, Hashable]]":
        """Predecessors, in_edges

        :return:
        """
        raise NotImplementedError

    @property
    def predecessor_nodes(self) -> "Set[Tuple[NonterminalNode]]":
        """Predecessors, in_nodes

        :return:
        """
        raise NotImplementedError

    def add_predecessor(self, node: "Tuple[NonterminalNode, Hashable]"):
        raise NotImplementedError

    def remove(self):
        raise NotImplementedError

    # def __eq__(self, other):
    #     raise NotImplementedError
    #
    # def __hash__(self):
    #     return hash(self.__id__)

    def debug_fmt(self, indent=1, verbose=False) -> str:
        """Format the debug string

        :param indent: Increment indent for each layer of nodes
        :param verbose: Show object id_
        :return: Formatted string
        """
        raise NotImplementedError


class TerminalNode(Node, ABC):
    """Abstraction class for TerminalNode

    Last layer of nodes, to close a graph
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def __id__(self) -> Hashable:
        return id(self)

    async def forward(self, *args, **kwargs) -> Any:
        """Forward input to terminal and invoke

        In particular, to call the handler

        :param args:
        :param kwargs:
        :return:
        """
        raise NotImplementedError

    def debug_fmt(self, indent=1, verbose=False) -> str:
        if verbose:
            return f'{" ":{indent}}<{type(self).__name__} {str(self)}>'
        else:
            return f'{" ":{indent}}<{type(self).__name__}>'


class NonterminalNode(Node, ABC):
    """Abstraction class for NonterminalNode

    Contains a layer of successor nodes
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def route(self, state: RouteState) -> Set[RouteResult_T]:
        """Get terminals routing from the node given arguments

        :param args:
        :param kwargs:
        :return: AsyncIterator of Terminals
        """
        # print(f'<DEBUG> {type(self).__name__}')
        with state:
            return await self._route(state)

    async def _route(self, state: RouteState) -> Set[RouteResult_T]:
        """Get terminals routing from the node given arguments

        :param args:
        :param kwargs:
        :return: AsyncIterator of Terminals
        """
        raise NotImplementedError

    def copy(self, node_map: Dict[Node, Node] = ...) -> "NonterminalNode":
        raise NotImplementedError

    @property
    def empty(self) -> bool:
        """Indicate the node has not added terminals

        :return:
        """
        raise NotImplementedError

    def clear(self):
        """Reinitialize the node, clear all successors

        :return:
        """
        raise NotImplementedError

    @property
    def successors(self) -> Iterable[Node]:
        """Successors

        :return:
        """
        raise NotImplementedError

    # def add_key(self, key):
    #     raise NotImplementedError

    def add_successor(self, node):
        """Add a successor

        :param node: Successor node
        :return:
        """
        raise NotImplementedError

    def remove_successor(self, node):
        """Remove a successor

        :param node:
        :return:
        """
        raise NotImplementedError

    def __ior__(self, other):
        """Merge with other equal node

        :param other: Other node (with same type and id_)
        :return: Self
        """
        raise NotImplementedError

    def debug_fmt(self, indent=1, verbose=False) -> str:
        if verbose:
            return f'{" ":{indent}}<{type(self).__name__} {str(self)}>'
        else:
            return f'{" ":{indent}}<{type(self).__name__}>'


class AbsNode(Node, ABC):
    _predecessors: Set[Tuple[NonterminalNode, Hashable]]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._predecessors = set()

    @property
    def predecessors(self) -> "Set[Tuple[NonterminalNode, Hashable]]":
        return self._predecessors.copy()

    @property
    def predecessor_nodes(self) -> "Set[Tuple[NonterminalNode]]":
        return set(map(lambda e: e[0], self._predecessors))

    def add_predecessor(self, node: "Tuple[NonterminalNode, Hashable]"):
        if node in self._predecessors:
            self._predecessors.remove(node)
        self._predecessors.add(node)

    def remove(self):
        pre_nodes = list(map(lambda e: e[0], self._predecessors))
        for pre_node in pre_nodes:
            pre_node.remove_successor(self)
            if not pre_node.successors:
                pre_node.remove()
        self._predecessors.clear()

    def __eq__(self, other):
        return (type(self) == type(other) and
                self.__id__ == other.__id__ and
                self.predecessors == other.predecessors
                )

    def __hash__(self):
        return hash(self.__id__)


@final
class IdentityNode(NonterminalNode, AbsNode):
    _successors: Set[Node]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._successors = set()

    def copy(self, node_map: Dict[Node, Node] = ...) -> "IdentityNode":
        ret = IdentityNode()
        if node_map is ...:
            node_map = {}
        for node in self._successors:
            ret.add_successor(node_map.setdefault(node, node.copy(node_map=node_map)))
        return ret

    @property
    def empty(self) -> bool:
        return not bool(self._successors)

    def clear(self):
        self._successors.clear()

    @property
    def successors(self) -> Iterable[Node]:
        return self._successors.copy()

    def add_successor(self, node):
        for u in self._successors:
            if isinstance(u, NonterminalNode) and u == node:
                u |= node
                break
        else:
            self._successors.add(node)
            node.add_predecessor((self,))

    def remove_successor(self, node):
        if node in self._successors:
            self._successors.remove(node)

    def __ior__(self, other):
        if isinstance(other, IdentityNode):
            for node in other._successors:
                self.add_successor(node)
            return self
        else:
            raise ValueError(f"Cannot apply operator ior between {type(self)} and {type(other)}")

    def debug_fmt(self, indent=1, verbose=False) -> str:
        out_str = ''
        inner_str = '\n'.join(node.debug_fmt(indent=2) for node in self._successors)
        inner_str = '\n'.join(map(lambda x: f'{" ":{indent + 2}}' + x, inner_str.split('\n')))
        out_str += f'{" ":{indent + 2}}[ \n{inner_str} \n{" ":{indent + 2}}]' + '\n'
        if verbose:
            return f'{" ":{indent}}<{type(self).__name__} : \n{out_str}{" ":{indent}}>'
        else:
            return f'{" ":{indent}}<{type(self).__name__} {str(self)}: \n{out_str}{" ":{indent}}>'

    async def _route(self, state: RouteState) -> Set[RouteResult_T]:
        res = set()
        for node in self._successors:
            if isinstance(node, TerminalNode):
                res.add(state.wrap(node))
            elif isinstance(node, NonterminalNode):
                res |= await node.route(state)
        return res
