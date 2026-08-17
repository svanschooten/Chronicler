import inspect
from collections.abc import Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


class Container:
    def __init__(self):
        # Populated only by register_instance() - always shared, never rebuilt.
        self._explicit_instances: dict[type, Any] = {}
        # Populated lazily by resolve() the first time a factory-backed (or
        # auto-built) type is requested. Kept separate from _explicit_instances so
        # create_scope() can share singletons while still rebuilding everything else.
        self._resolved_cache: dict[type, Any] = {}
        self._factories: dict[type, Callable] = {}

    def register_instance(self, cls: type[T], instance: T):
        self._explicit_instances[cls] = instance

    def register_factory(self, cls: type[T], factory: Callable[..., T]):
        self._factories[cls] = factory

    def is_registered(self, cls: type) -> bool:
        """Whether `cls` has an explicit registration (instance or factory) - as
        opposed to something that would only resolve via the auto-build fallback for
        plain concrete classes. Useful for optional cleanup: e.g. only bother closing
        an AsyncSession if this container was actually set up to build one, rather
        than triggering resolve()'s auto-build attempt on a type that was never meant
        to be resolved here.
        """
        return cls in self._explicit_instances or cls in self._factories

    def create_scope(self) -> "Container":
        """A new Container that shares this one's explicit singletons (register_instance
        - e.g. a DatabaseManager meant to live for the app's lifetime) and factory
        recipes, but starts with an empty resolve cache of its own. Anything resolved
        through the new container that isn't an explicit singleton is therefore built
        fresh - a fresh AsyncSession, fresh repositories, a fresh service instance -
        even if this container already resolved one. Used to give each unit of work
        (an HTTP request, a task execution) its own session rather than sharing one
        across the whole process.

        Registrations added to this container *after* create_scope() is called are not
        visible to the already-created scope.
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

    def _build_instance(self, cls: type[T]) -> T:
        if cls.__init__ is object.__init__:
            return cast(T, cls.__new__(cls))

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

        return cast(T, cls(**kwargs))

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
