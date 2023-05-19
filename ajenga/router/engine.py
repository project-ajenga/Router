from typing import Optional, Tuple

from ajenga.typing import AsyncIterable, Callable, Iterable, Set, Type, final

from .exceptions import RouteException
from .keystore import KeyStore
from .models import Executor, Graph, Priority, TerminalNode
from .models.execution import PriorityExecutor
from .state import RouteResult, RouteState
from .std import HandlerNode


class Engine:
    """ A wrapper for decorator based graph applying

    """
    _graph: Graph
    _dirty: bool
    _graph_impl: Graph
    _handler_cls: Type[TerminalNode]

    def __init__(self, *,
                 handler_cls: Type[TerminalNode] = HandlerNode,
                 executor_factory: Callable[..., Executor] = PriorityExecutor,
                 ):
        self._graph = Graph().apply()
        self._dirty = True
        self._handler_cls = handler_cls
        self._executor_factory = executor_factory

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def handler_cls(self) -> Type[TerminalNode]:
        return self._handler_cls

    def on(self, graph: Graph) -> Graph:
        return GraphImpl(engine=self) & graph

    def subscribe(self, graph: Graph) -> None:
        # TODO: Subscribe does not copy the graph, thus returned frozen graph can change!
        if graph.closed:
            self._graph |= graph
            self._dirty = True
        else:
            raise ValueError("Cannot subscribe an open graph!")

    def unsubscribe_terminals(self, terminals: Iterable[TerminalNode]):
        self._graph.remove_terminals(terminals)
        self._dirty = True

    async def forward(self, *args, **kwargs) -> AsyncIterable:
        if self._dirty:
            self._graph_impl = self._graph.copy()
            self._dirty = False

        state = RouteState(args, KeyStore(kwargs))
        state.store['_store'] = state.store
        state.store['_state'] = state
        routed = await self._graph_impl.route(state)
        terminals: Iterable[RouteResult] = []
        exceptions: Iterable[RouteException] = []
        for routed_result in routed:
            if isinstance(routed_result, RouteResult):
                terminals.append(routed_result)
            elif isinstance(routed_result, RouteException):
                exceptions.append(routed_result)

        for e in exceptions:
            yield e.args[0]

        executor = self._executor_factory()

        for r in terminals:
            terminal = r.node
            mapping = r.mapping
            executor.create_task(terminal.forward,
                                 priority=getattr(terminal, 'priority', Priority.Default),
                                 count_finished=getattr(terminal, 'count_finished', True),
                                 args=(state, mapping,),
                                 )
    
        async for res in executor.run():
            yield res

    def clear(self):
        self._graph.clear()
        self._graph_impl = self._graph.copy()


@final
class GraphImpl(Graph):
    """Graph implementation supports __call__ as decorator

    """

    def __init__(self, engine: Engine, **kwargs):
        super().__init__(**kwargs)
        self._engine = engine

    def apply(self, terminal: Optional[TerminalNode] = None) -> "Graph":
        return super().apply(terminal)

    def __call__(self, func) -> TerminalNode:
        if self.closed:
            raise ValueError("Cannot call on a closed graph!")
        if not isinstance(func, TerminalNode):
            func = self._engine.handler_cls(func)
        g = self.apply(func)
        self._engine.subscribe(g)
        return func

    def copy(self):
        return GraphImpl(engine=self._engine, start=self.start.copy(), closed=self.closed)
