# Dependency injection

`chronicler/core/container.py`, `chronicler/core/local_container.py`

`Container` is a small constructor-injection resolver. It reads type hints off
`__init__` and builds what it needs, so a service declares its dependencies in its
signature and nothing has to be wired by hand at each call site.

## Three ways a type resolves

| Registration | Lifetime | Used for |
| ------------ | -------- | -------- |
| `register_instance` | Shared forever, never rebuilt | `DatabaseManager` — one per process |
| `register_factory` | Rebuilt per scope | `AsyncSession` |
| No registration | Auto-built per scope, from type hints | Repositories and services |

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

## `register_local_storage`

Server mode and desktop full-stack mode need the workspace's `DatabaseManager` and archive
session wired identically, so those two registrations live in one function.

Nothing else needs registering. Services name the SQLite repositories they use, and each
repository takes only an `AsyncSession`, so `Container` builds it from the scope's session.
Every archive repository in a scope therefore shares that scope's one session.

`TranscriptService` does not take a `SQLiteTranscriptRepository`. It depends on
`DatabaseManager` and `SQLiteChronicleRepository` and opens each chronicle's own database
as it needs it (see [storage.md](storage.md)).

An optional dependency, such as `SystemService`'s `SQLiteChronicleRepository | None`,
resolves to `None` in a container that cannot build an `AsyncSession`.

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
