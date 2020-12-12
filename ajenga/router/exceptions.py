class RouteException(Exception):
    pass


class RouteInternalException(RouteException):
    def __init__(self, e):
        super().__init__(e)
