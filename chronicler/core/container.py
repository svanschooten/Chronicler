import inspect
import types
from collections.abc import Callable
from typing import Any, TypeVar, Union, cast, get_args, get_origin

T = TypeVar("T")


class Container:
    def __init__(self):
        self._explicit_instances: dict[type, Any] = {}
        self._resolved_cache: dict[type, Any] = {}
        self._factories: dict[type, Callable] = {}

    def register_instance(self, cls: type[T], instance: T):
        self._explicit_instances[cls] = instance

    def register_factory(self, cls: type[T], factory: Callable[..., T]):
        self._factories[cls] = factory

    def is_registered(self, cls: type) -> bool:
        """
        Whether `cls` has an explicit registration (instance or factory) - as opposed to
        something that would only resolve via the auto-build fallback for plain concrete
        classes.
        """
        return cls in self._explicit_instances or cls in self._factories

    def create_scope(self) -> "Container":
        """
        A new Container that shares this one's explicit singletons (register_instance -
        e.g. a DatabaseManager meant to live for the app's lifetime) and factory
        recipes, but starts with an empty resolve cache of its own.
        """
        scope = Container()
        scope._explicit_instances = dict(self._explicit_instances)
        scope._factories = dict(self._factories)
        return scope

    def resolve(self, cls: type[T]) -> T:
        if cls in self._explicit_instances:
            return self._explicit_instances[cls]

        if cls in self._resolved_cache:
            return cast(T, self._resolved_cache[cls])

        if cls in self._factories:
            factory = self._factories[cls]
            if inspect.isclass(factory):
                instance = self._build_instance(factory)
            else:
                instance = self._call_with_dependencies(factory)

            self._resolved_cache[cls] = instance
            return cast(T, instance)

        if inspect.isclass(cls):
            instance = self._build_instance(cls)
            self._resolved_cache[cls] = instance
            return cast(T, instance)

        raise ValueError(f"Could not resolve {cls}")

    @staticmethod
    def _optional_inner(annotation: Any) -> Any | None:
        """The `T` of a `T | None` annotation, or None if it is not optional."""
        if get_origin(annotation) not in (Union, types.UnionType):
            return None
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) != 1 or type(None) not in get_args(annotation):
            return None
        return args[0]

    def _resolve_parameter(self, annotation: Any) -> Any:
        """Resolves a constructor parameter, treating `T | None` as best-effort."""
        inner = self._optional_inner(annotation)
        if inner is None:
            return self.resolve(annotation)
        try:
            return self.resolve(inner)
        except (ValueError, TypeError):
            return None

    def _build_instance(self, cls: type[T]) -> T:
        if cls.__init__ is object.__init__:
            return cast(T, cls.__new__(cls))

        signature = inspect.signature(cls.__init__)
        kwargs = {}
        for name, param in signature.parameters.items():
            if name == "self":
                continue
            if param.annotation is not inspect.Parameter.empty:
                kwargs[name] = self._resolve_parameter(param.annotation)
            else:
                raise ValueError(
                    f"Cannot resolve parameter {name} of {cls.__name__}: missing type hint"
                )

        return cast(T, cls(**kwargs))

    def _call_with_dependencies(self, func: Callable) -> Any:
        signature = inspect.signature(func)
        kwargs = {}
        for name, param in signature.parameters.items():
            if param.annotation is not inspect.Parameter.empty:
                kwargs[name] = self._resolve_parameter(param.annotation)
            else:
                raise ValueError(
                    f"Cannot resolve parameter {name} of {func.__name__}: missing type hint"
                )

        return func(**kwargs)
