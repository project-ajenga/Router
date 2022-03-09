from collections import deque
from typing import Optional

from ajenga.typing import Iterable, Set

from ..exceptions import RouteException
from . import RouteResult_T
from .node import IdentityNode, Node, NonterminalNode, TerminalNode


class Graph:
    """State Transition Graph

    To inherit this class, should override the following:
        __init__
        copy
        __call__
    """
    _start: IdentityNode
    _closed: bool

    def __init__(self, start=None, closed=False):
        self._start = start or IdentityNode()
        self._closed = closed

    @property
    def start(self) -> IdentityNode:
        """Start node

        :return:
        """
        return self._start

    @property
    def closed(self) -> bool:
        """Indicate the graph is close thus cannot concentrate other graph

        :return:
        """
        return self._closed

    @property
    def entries(self) -> Iterable[Node]:
        """First layer nodes, successors of start node

        :return:
        """
        return self.start.successors

    def remove_terminals(self, terminals: Iterable[TerminalNode]):
        """Remove given terminals and eliminate unused nonterminals in path

        :param terminals:
        :return:
        """
        for terminal in terminals:
            terminal.remove()

    def traverse(self) -> Iterable[Node]:
        """Traverse the graph in DFS

        :return:
        """
        queue = deque()
        queue.append(self.start)
        while queue:
            node = queue.popleft()
            if isinstance(node, NonterminalNode):
                for successor in node.successors:
                    queue.append(successor)
            yield node

    @property
    def curve(self) -> Set[NonterminalNode]:
        """Curve nonterminals for open graph

        :return:
        """
        ret = set()
        for node in self.traverse():
            if isinstance(node, NonterminalNode) and node.empty:
                ret.add(node)
        return ret

    @property
    def terminals(self) -> Set[TerminalNode]:
        """Terminals for closed graph

        :return:
        """
        ret = set()
        for node in self.traverse():
            if isinstance(node, TerminalNode):
                ret.add(node)
        return ret

    def verify(self) -> bool:
        for node in self.traverse():
            if isinstance(node, NonterminalNode):
                for nn in node.successors:
                    if node not in nn.predecessor_nodes:
                        print('-------------------Verify-------------------------')
                        print(f'---------Current Node: {node}--------------------')
                        print(f'---------Succ Node:  {nn}----------------')
                        print(f'---------Succ Pred Nodes: {nn.predecessors}-----')
                        return False
        return True

    def add_edge(self, u: NonterminalNode, v: Node):
        """Util function for add an edge

        :param u: node from
        :param v: node to
        :return:
        """
        u.add_successor(v)

    def clear(self):
        """Clear graph

        :return:
        """
        self.start.clear()

    def copy(self):
        """Copy of graph

        :return:
        """
        return type(self)(start=self.start.copy(), closed=self.closed)

    def __copy__(self):
        return self.copy()

    def apply(self, terminal: Optional[TerminalNode] = None) -> "Graph":
        """Apply graph to function, make the function terminal and create closed graph

        :param terminal:
        :return: Closed graph
        """
        # assert self.verify()

        if self.closed:
            raise ValueError("Cannot apply on a closed graph!")
        g = self.copy()
        if terminal:
            for node in g.curve:
                node.add_successor(terminal)
        g._closed = True
        return g

    def __call__(self, *args, **kwargs):
        raise NotImplementedError

    def _and(self, other):
        if self.closed:
            raise ValueError("Cannot apply on a closed graph!")
        elif isinstance(other, Graph):
            us = list(self.curve)
            vs = list(other.entries)
            if len(us) > 1 and len(vs) > 1:
                [self.add_edge(u, other.start) for u in us]
            else:
                [self.add_edge(u, v) for u in us for v in vs]

        elif isinstance(other, NonterminalNode):
            for node in self.curve:
                self.add_edge(node, other)
        else:
            raise ValueError(f"Cannot apply operator and between {type(self)} and {type(other)}")

    def __iand__(self, other):
        """Concentrate with graph

        :param other:
        :return:
        """
        self._and(other)
        return self

    def __and__(self, other):
        """Concentrate two graphs

        :param other:
        :return:
        """
        g = self.copy()
        g._and(other)
        return g

    def _or(self, other):
        if isinstance(other, Graph):
            for node in other.entries:
                self.add_edge(self.start, node)
        elif isinstance(other, NonterminalNode):
            self.add_edge(self.start, other)
        else:
            raise ValueError(f"Cannot apply operator or between {type(self)} and {type(other)}")

    def __ior__(self, other):
        """Conjunct with graph

        :param other:
        :return:
        """
        self._or(other)
        return self

    def __or__(self, other):
        """Conjunct two graphs

        :param other:
        :return:
        """
        g = self.copy()
        g._or(other)
        return g

    async def route(self, *args, **kwargs) -> Set[RouteResult_T]:
        """Forward input to the graph, asynchronous invoke terminals and yield

        :param args:
        :param kwargs:
        :return:
        """
        if not self.closed:
            raise ValueError("Cannot apply on a open graph!")

        return await self.start.route(*args, **kwargs)

        # res = set()

        # for routed in await self.start.route(*args, **kwargs):
        #     if isinstance(routed, TerminalNode):
        #         res.add(routed)
        #     elif isinstance(routed, RouteException):
        #         res.add(routed)
        #     else:
        #         raise ValueError(routed)

        # return set(res)

    def debug_fmt(self, indent=1) -> str:
        """Format the debug string

        :param indent:
        :return:
        """
        return f'{" ":{indent}}<Graph: \n{self.start.debug_fmt(indent + 2)}>'
