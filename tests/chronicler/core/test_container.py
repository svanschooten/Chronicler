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

    def factory(dep):
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

    root_service = container.resolve(Service)
    assert build_count == 1

    scope1 = container.create_scope()
    scope2 = container.create_scope()
    service1 = scope1.resolve(Service)
    service2 = scope2.resolve(Service)

    assert build_count == 3
    assert service1 is not service2
    assert service1 is not root_service
    assert scope1.resolve(Service) is service1
    assert build_count == 3


def test_scope_registrations_are_independent_of_parent_after_creation():
    container = Container()
    container.register_instance(Dependency, Dependency())

    def factory(dep: Dependency) -> Service:
        return Service(dep)

    container.register_factory(Service, factory)

    scope = container.create_scope()

    later_dep = Dependency()
    container.register_instance(Service, later_dep)

    assert scope.resolve(Service) is not later_dep
    assert isinstance(scope.resolve(Service), Service)


class TestOptionalDependencies:
    def test_an_optional_dependency_resolves_when_registered(self):
        class Thing:
            pass

        class Needs:
            def __init__(self, thing: Thing | None):
                self.thing = thing

        container = Container()
        registered = Thing()
        container.register_instance(Thing, registered)

        assert container.resolve(Needs).thing is registered

    def test_an_optional_dependency_becomes_none_when_unresolvable(self):
        class Unbuildable:
            def __init__(self, untyped):
                pass

        class Needs:
            def __init__(self, thing: Unbuildable | None):
                self.thing = thing

        assert Container().resolve(Needs).thing is None

    def test_a_required_dependency_that_cannot_resolve_still_raises(self):
        class Needs:
            def __init__(self, untyped):
                pass

        container = Container()
        with pytest.raises(ValueError, match="missing type hint"):
            container.resolve(Needs)

    def test_an_optional_abstract_dependency_becomes_none(self):
        from abc import ABC, abstractmethod

        class Port(ABC):
            @abstractmethod
            def go(self) -> None: ...

        class Needs:
            def __init__(self, port: Port | None):
                self.port = port

        assert Container().resolve(Needs).port is None
