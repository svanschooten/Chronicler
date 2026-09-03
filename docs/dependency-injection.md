# Dependency injection

`chronicler/core/container.py`, `chronicler/core/local_container.py`

`Container` is a small constructor-injection resolver. It reads type hints off
`__init__` and builds what it needs, so a service declares its dependencies in its
signature and nothing has to be wired by hand at each call site.

## Three ways a type resolves

| Registration | Lifetime | Used for |
| ------------ | -------- | -------- |
| `register_instance` | Shared forever, never rebuilt | `DatabaseManager` — one per process |
| `register_factory` | Rebuilt per scope | `AsyncSession`, repositories |
| No registration | Auto-built per scope, from type hints | Services |

`_explicit_instances` and `_resolved_cache` are kept separate precisely so
`create_scope()` can share the singletons while rebuilding everything else.

## Scopes

`create_scope()` returns a new `Container` sharing this one's explicit singletons and
factory recipes, but with an empty resolve cache of its own. Anything that is not an
explicit singleton is therefore built fresh: a fresh `AsyncSession`, fresh
repositories, a fresh service instance.

This is what gives each unit of work its own session. Without it, every HTTP request
would share one `AsyncSession` for the server's entire lifetime, which is not safe
under concurrent use.

Registrations added to a container *after* `create_scope()` was called are not visible
to the already-created scope.

Scopes are created in two places:

* `RpcServer._add_route`'s wrapper — one per HTTP request, closed in a `finally`.
* `DesktopApp._new_scope` — one per navigation, closed when navigating away.

## `is_registered`

Answers "does this container have an explicit registration for `cls`", as opposed to
something that would only resolve through the auto-build fallback.

It exists for optional cleanup. `RpcServer` only closes an `AsyncSession` if the scope
was actually set up to build one — a service with no database dependency (a test using
a bare `Container()`, say) should not trigger the auto-build fallback for
`AsyncSession`, which is not constructible without a bound engine and would raise.

## `register_local_repositories`

Server mode and desktop full-stack mode need the archive session and repository
factories wired identically, so that mapping lives in one function.

`TranscriptService` is deliberately *not* registered there. It depends on
`DatabaseManager` and `ChronicleRepository` directly rather than a pre-bound
`TranscriptRepository` (see [storage.md](storage.md)), so it needs no factory of its
own — `Container` builds it from what is already registered.

## A known typing wart

`register_factory(ChronicleRepository, SQLiteChronicleRepository)` needs
`# type: ignore[type-abstract]`. `Container.register_factory`'s generics do not fully
accommodate the interface-to-implementation registration pattern it is designed for:
mypy treats passing an ABC as the `type[T]` key as if `T` itself were being
instantiated. This is tension in `Container`'s typing, not a bug in the registration.

## Nothing session-shaped belongs on the root container

`resolve` caches, and `create_scope()` copies the *recipes* rather than the results. So
anything resolved on the root container lives as long as the process - which is right for
a `DatabaseManager` and wrong for an `AsyncSession`.

Resolving a service off the root is therefore enough to leak a session, because building
it resolves its repository, which resolves a session. That is exactly what startup model
discovery did; see [troubleshooting.md](troubleshooting.md).

`cached(cls)` is the shutdown-side counterpart: it returns what a scope already built
without building anything. `resolve` cannot be used for this, because asking it whether a
session exists creates one.
