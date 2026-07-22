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
