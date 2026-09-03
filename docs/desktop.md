# Desktop application

`chronicler/desktop/`

A Flet UI over the same services every other mode uses. `DesktopRuntime` builds
everything the app needs for either deployment mode once at startup from `Settings`.

## Full stack versus thin client

`db_manager` is `None` in thin-client mode — there is no local workspace at all — and
`DesktopApp` uses its presence to decide whether this instance owns a `WorkerManager`.
A thin client has no local tasks to run; the server it points at runs its own.

Full-stack mode is also the one case where the `WorkerManager` and the UI genuinely
share a process and event loop, so a live refresh on task completion is achievable.
`TaskEventBus` itself does not know or care that this is desktop-only.

## Colours are baked in at construction

Every view reads the palette once when it is built. A theme change therefore rebuilds
whichever view is on screen rather than trying to mutate every control in place.

Two things are *not* naturally rebuilt on navigation and need an explicit nudge:

* the **sidebar**, built once in `main()` — hence `Sidebar.set_dark_mode`
* the **content area and divider**, held on `DesktopApp` so `_apply_theme` can recolour
  them

`page.bgcolor` matters even though the sidebar and content area paint themselves: it is
what shows behind and around them — the SafeArea insets, and any gap while a view is
being rebuilt.

Light mode diverged from the original mockup deliberately. `AMBER_100` is a near-white
pale yellow, practically invisible as a border against a white surface, so borders are
`BROWN_200`. An `AMBER_50` sidebar read as an odd yellow-brown tint next to the rest of
the light theme rather than a deliberate accent, so it is the same white as `surface`.
`AMBER_300` reads fine against a dark surface but disappears against a light one, which
is why `accent` differs per theme.

## Scopes per navigation

Each navigation gets a fresh `Container` scope, closed when navigating away, rather
than one held for the app's lifetime. Sequential reuse within one view visit is fine —
Flet handlers run one at a time. What is not safe is sharing it with the background
worker loop, which gets its own session.

Scope creation is per-branch rather than unconditional: `SettingsView` does not touch
the database, so it should not cause a session to be opened and immediately closed for
nothing.

A `RemoteContainer` has no scope to manage — each remote call is already scoped
per-request server-side.

## Re-fetching before rendering the transcript view

`TranscriptView` bakes `speakers_count`, `duration`, `status` and tags into its UI at
construction. `state.selected_chronicle` is a snapshot from whenever the user navigated,
so the chronicle is re-fetched before building the view; otherwise a live refresh after
a background task finishes would still show stale values. A chronicle deleted out from
under the view sends the user back rather than rendering a transcript for something
that no longer exists.

## Dialogs

Flet has no built-in "show a modal and await what the user picked", so
`chronicler/desktop/dialogs.py` uses a Future the action buttons resolve — mirroring how
`ft.FilePicker.pick_files` is implemented internally.

It goes through `page.show_dialog()` / `page.pop_dialog()` rather than appending to
`page.overlay` and toggling `open`. `AlertDialog`'s close is animated client-side, and
`show_dialog()` wraps `on_dismiss` so the dialog is only removed once the client
confirms the animation finished. An earlier version called `page.overlay.remove(dialog)`
immediately after `open = False`, which dropped the post-animation dismiss callback: the
buttons worked, the future resolved, the import proceeded — and the dialog visually never
closed.

The `on_choice` builder takes a zero-argument *getter* rather than a plain value, so a
button can resolve to something only known at click time, such as the current contents
of a `TextField`.

`OverlayForm` in `views/archive/forms.py` is the opposite case and uses the
`overlay` + `open` route on purpose: these forms need to exist, and hold their field
values, before and after being shown rather than for the duration of one await.
`attach`/`detach` are idempotent so mount/unmount can call them without tracking state.

## Flet API notes

* **`FilePicker` is a Service, not a visual control.** It belongs in `page.services`,
  not `page.overlay`. Putting it in overlay makes the client choke with
  `Unknown control: FilePicker`.
* **`ft.Page` has no `snack_bar` attribute** in 0.86.4 — that was a pre-0.70 API. A
  `SnackBar` is shown through the same dialog stack as `ft.AlertDialog`.
* **Async handlers are bound directly.** Flet awaits them itself; wrapping one in a
  lambda swallows the coroutine, which is what used to make card buttons silently do
  nothing.

## Separation of concerns

`ImportCoordinator` is the clearest example of the rule the desktop package follows:
picking a file and reporting the outcome are the view's job, but deciding what an
"import audio" or "import transcript" *does* to the workspace is not. Keeping that in a
Flet-free object means it can be tested without a page attached, and leaves the view
with layout plus event plumbing.

`ChronicleCardHandlers` groups every action a card can trigger into one object, so
adding a card action does not mean threading another positional argument through the
builder.

`_pending_import_action` exists because Flet's picker result arrives without any
indication of which action asked for it.

Picked files can be anywhere on disk, and `handle_import` requires the path be inside
the workspace's `imports/`. `stage_file` copies (local mode) or uploads (thin-client
mode) the picked file there first and returns the path that is actually safe to queue.

## Tasks view

Chronicle titles are resolved once per load rather than per row — the archive is small
and a per-row fetch would be a query per task. A failure there is not worth failing the
whole view over; rows fall back to showing no chronicle name.

`RETRYABLE_STATUSES` excludes `WORKING` on purpose: it is already running, and
re-queueing it would let a second worker claim it while the first is still going.
