import inspect
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class Container:
    def __init__(self):
        self._instances: dict[type, Any] = {}
        self._factories: dict[type, Callable] = {}

    def register_instance(self, cls: type[T], instance: T):
        self._instances[cls] = instance

    def register_factory(self, cls: type[T], factory: Callable[..., T]):
        self._factories[cls] = factory

    def resolve(self, cls: type[T]) -> T:
        if cls in self._instances:
            return self._instances[cls]

        if cls in self._factories:
            factory = self._factories[cls]
            if inspect.isclass(factory):
                instance = self._build_instance(factory)
            else:
                instance = self._call_with_dependencies(factory)

            self._instances[cls] = instance
            return instance

        if inspect.isclass(cls):
            instance = self._build_instance(cls)
            self._instances[cls] = instance
            return instance

        raise ValueError(f"Could not resolve {cls}")

    def _build_instance(self, cls: type[T]) -> T:
        if cls.__init__ is object.__init__:
            return cls()

        signature = inspect.signature(cls.__init__)
        kwargs = {}
        for name, param in signature.parameters.items():
            if name == "self":
                continue
            if param.annotation is not inspect.Parameter.empty:
                kwargs[name] = self.resolve(param.annotation)
            else:
                raise ValueError(
                    f"Cannot resolve parameter {name} of {cls.__name__}: missing type hint"
                )

        return cls(**kwargs)

    def _call_with_dependencies(self, func: Callable) -> Any:
        signature = inspect.signature(func)
        kwargs = {}
        for name, param in signature.parameters.items():
            if param.annotation is not inspect.Parameter.empty:
                kwargs[name] = self.resolve(param.annotation)
            else:
                raise ValueError(
                    f"Cannot resolve parameter {name} of {func.__name__}: missing type hint"
                )

        return func(**kwargs)
