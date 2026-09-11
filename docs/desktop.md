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

`OverlayForm` in `desktop/forms.py` is the opposite case and uses the
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
* **`Dropdown` fires `on_select`, not `on_change`** in 0.86.
* **`Dropdown.text` is reported by the client, not written to it.** Assigning it
  server-side changes nothing on screen — clearing the field has to go through `value`,
  which is the selection and does repaint. See the searchable dropdown below.
* **Validation messages are spelled differently per control.** A `TextField` carries
  `error` (from `FormFieldControl`); a `Dropdown` carries `error_text`. Setting the wrong
  one appears to work at runtime and fails `mypy`.
* **`Control.disabled`** is what greys a button out, and `tooltip` still shows while
  disabled — which is what makes "explain why this is unavailable" possible.

## Dropdowns for lists nobody wants to scroll

`searchable_dropdown()` in `desktop/widgets.py` backs every open-ended picker: the
summary model, the transcribe dialog's speaker, and the per-line speaker in the
transcript editor. Fixed sets — locale, Whisper model size, provider — stay plain.

`editable` and `enable_filter` were already set on some of them and were not enough. Two
things had to be added.

**`menu_height`.** Without it the menu grows to fit every option. A provider offering
seventy models produced a menu taller than the window, covering the text field you would
have typed a filter into — so the list could not be narrowed at all, which is the state
"this is not searchable" described. Capped, the menu scrolls and the field stays put.

**Emptying the field on focus.** It arrives holding the current selection, so typing
inserts into the middle of it (`venice/llama-3b` + `qwen`) and matches nothing. The clear
goes through `value`, not `text`: `text` is client-reported and writing it back does not
repaint. Leaving without choosing restores the selection.

`chosen_value()` is the other half. An editable Dropdown keeps `text` (what is in the
field) and `value` (the option last *selected*) apart, so reading `value` alone ignores a
name typed over it — that is how a transcription could run as the wrong speaker. Typed
text wins where there is any; otherwise the selection does, which is what makes the
focus-clear safe: a field emptied for filtering and left alone still reports what the
user can see.

One consequence worth knowing: a speaker dropdown can no longer be *emptied*, because
blurring an untouched field puts the name back. The dialog requires a speaker anyway, and
the TextField shown when no speakers are known yet still validates normally.

## Separation of concerns

`ImportCoordinator` is the clearest example of the rule the desktop package follows:
picking a file and reporting the outcome are the view's job, but deciding what an
"import audio" or "import transcript" *does* to the workspace is not. Keeping that in a
Flet-free object means it can be tested without a page attached, and leaves the view
with layout plus event plumbing.

It lives in `desktop/imports.py` rather than inside the archive package because both the
archive and the chronicle view import into a chronicle. `desktop/forms.py` moved out for
the same reason.

`ChronicleCardHandlers` groups every action a card can trigger into one object, so
adding a card action does not mean threading another positional argument through the
builder. `ChronicleActionCallbacks` does the same for the chronicle view's action row.

Picked files can be anywhere on disk, and the import handler requires the path be inside
the workspace's `imports/`. `stage_file` copies (local mode) or uploads (thin-client
mode) the picked file there first and returns the path that is actually safe to queue.

## One file-dialog flow

`desktop/picking.py` owns opening a native dialog and explaining a failure.

The archive view used to hold a `picker_action` string and a `current_chronicle_id`,
because Flet's picker result arrives with no indication of which action asked for it.
Awaiting `pick_files()` directly removes the need: the caller still has its own
variables in scope. The state machine is gone, and with two views now picking files it
is not duplicated either.

The other reason it is one place: a file dialog goes through the XDG desktop portal over
the session D-Bus, and when that is missing the raw error is an errno against a path
that means nothing to the reader. `describe_desktop_integration_error` turns it into
something actionable — see [troubleshooting.md](troubleshooting.md).

## Chronicle actions in the chronicle view

`views/transcript/actions.py` puts import audio, import transcript, clean, identify
speakers, generate summary, edit and delete above the transcript. Every one of them also
exists on the archive card; the duplication is the point, because the chronicle view is
where a chronicle is actually worked on, and going back to the list to clean the thing
already open is the awkwardness being removed.

Delete confirms first, and then calls `on_deleted` rather than `on_changed` — reloading
a view for a chronicle that no longer exists would immediately fail, so it navigates
back to the archive instead.

## The transcribe dialog

One button per source row, and it opens `views/transcript/transcribe_dialog.py`.

Previously there were two buttons: assign speaker, and transcribe. Both opened the same
dialog, whose confirm button said "Transcribe" either way — so choosing a speaker
started a transcription. Now the row's single button says transcribe, the dialog it opens
holds everything a run needs (speaker, language, model, silence threshold, normalize
first), and *Save speaker only* is a clearly-labelled secondary action for the case where
assignment is all you wanted.

Every value defaults from `Settings.transcription` and applies to that run only, so the
Settings page holds the defaults and the dialog holds the overrides. See
[transcription.md](transcription.md).

The dialog resolves its own future rather than using `await_dialog`, because a rejected
field has to leave the dialog open. `await_dialog`'s `on_choice` resolves unconditionally.

## The detail panel's width

`detail_panel_width()` is a share of the window with a floor and a ceiling, applied on
mount and on `page.on_resize`. At a fixed 260 px, long filenames and speaker names
ellipsised away on a large monitor, which is exactly where there was room to show them.
The floor keeps a narrow window readable; the ceiling stops the panel stranding the
transcript on an ultrawide. Rows also carry their full filename as a tooltip, since
ellipsis is still correct at the floor width.

## Tasks view

Chronicle titles are resolved once per load rather than per row — the archive is small
and a per-row fetch would be a query per task. A failure there is not worth failing the
whole view over; rows fall back to showing no chronicle name.

`RETRYABLE_STATUSES` excludes `WORKING` on purpose: it is already running, and
re-queueing it would let a second worker claim it while the first is still going.
