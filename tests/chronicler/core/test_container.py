import pytest

from chronicler.core.container import Container


class Dependency:
    pass


class Service:
    def __init__(self, dep: Dependency):
        self.dep = dep


def test_container_resolves_class_with_dependencies():
    container = Container()
    container.register_instance(Dependency, Dependency())
    service = container.resolve(Service)
    assert isinstance(service, Service)
    assert isinstance(service.dep, Dependency)


def test_container_resolves_factory_function_with_hints():
    container = Container()
    container.register_instance(Dependency, Dependency())

    def factory(dep: Dependency) -> Service:
        return Service(dep)

    container.register_factory(Service, factory)
    service = container.resolve(Service)
    assert isinstance(service, Service)
    assert isinstance(service.dep, Dependency)


def test_container_fails_on_missing_type_hint_in_factory():
    container = Container()

    def factory(dep):  # No type hint
        return Service(dep)

    container.register_factory(Service, factory)

    with pytest.raises(ValueError, match="missing type hint"):
        container.resolve(Service)


def test_container_resolves_parameterless_lambda():
    container = Container()
    instance = Dependency()
    container.register_factory(Dependency, lambda: instance)

    resolved = container.resolve(Dependency)
    assert resolved is instance


def test_scope_shares_explicit_singletons():
    container = Container()
    dep = Dependency()
    container.register_instance(Dependency, dep)

    scope = container.create_scope()

    assert scope.resolve(Dependency) is dep
    assert scope.resolve(Dependency) is container.resolve(Dependency)


def test_scope_rebuilds_factory_backed_types_fresh():
    container = Container()
    container.register_instance(Dependency, Dependency())

    build_count = 0

    def factory(dep: Dependency) -> Service:
        nonlocal build_count
        build_count += 1
        return Service(dep)

    container.register_factory(Service, factory)

    # Resolving on the root container once...
    root_service = container.resolve(Service)
    assert build_count == 1

    # ...does not poison a later scope: each new scope rebuilds its own instance.
    scope1 = container.create_scope()
    scope2 = container.create_scope()
    service1 = scope1.resolve(Service)
    service2 = scope2.resolve(Service)

    assert build_count == 3
    assert service1 is not service2
    assert service1 is not root_service
    # But resolving twice *within* the same scope still caches, same as a plain
    # Container would - a scope is just a Container with a fresh cache.
    assert scope1.resolve(Service) is service1
    assert build_count == 3


def test_scope_registrations_are_independent_of_parent_after_creation():
    container = Container()
    container.register_instance(Dependency, Dependency())

    def factory(dep: Dependency) -> Service:
        return Service(dep)

    container.register_factory(Service, factory)

    scope = container.create_scope()

    # Registered on the parent *after* the scope already exists.
    later_dep = Dependency()
    container.register_instance(Service, later_dep)

    # The scope's snapshot predates this registration, so it still builds Service via
    # the factory it captured at create_scope() time, not the later override.
    assert scope.resolve(Service) is not later_dep
    assert isinstance(scope.resolve(Service), Service)
