# 058-T6_ui_rendering_checks

## Nothing verifies the real rendered UI

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium: UI bugs reach users, as four rounds of Sprint 4 fixes showed. Change risk: none. |
| reach | All contributors |
| effort | M |
| evidence | read in code; already noted in `TODO.md:1435` |
| touches | `tests/`, CI |

### description

Views are only tested as control trees. Nothing renders, and the audit did not open the UI
either. So bugs like the view rebuild in the linked ticket can only be found by hand. It
is not yet known what Flet 0.86 offers for testing a rendered app.

### outcome

Flet 0.86's `flet.testing` can drive the real rendered app. In host mode, pytest runs
`DesktopApp` in-process and a Flutter client connects back to it, drawn on Xvfb. Tests
find text and tooltips, tap, and type. `tests/ui/` covers every view, the create form,
a dismissed confirmation (073), and editing a transcript line. Each test fails if
"Unknown control" is on screen: putting the old FilePicker back into `page.overlay`
fails them, which no control-tree test could see. About 25 s a test.

They found a bug on the first run: clicking "Finish editing" right after typing showed
the old text, because the blur's save had not landed when the view reloaded. Fixed in
the follow-up PR, which also removes that test's `xfail`.

What it took:

- **The client is Flet's own `client/`**, fetched at the installed Flet's tag and trimmed
  by `scripts/ui_host.py`. `flet test` builds a device-mode shell instead, which runs the
  app on its own embedded Python, not in pytest. Every Flet extension is removed, and
  Flet's `jni: 1.0.0` override is lifted to `^1.1.1`, without which `flutter pub get`
  fails (Flet pins it for dart-lang/native#3498, an ARM64 build bug).
- **`GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1`** on Xvfb, or the client draws nothing.
- **`PUB_CACHE` pinned to the real cache**, since every test points `HOME` at a temporary
  folder and Flutter would download its packages into it.
- **Screens of failures via ffmpeg**: Flet takes app screenshots only on Android and iOS.
- **A port picked with a socket that is closed**: Flet's own `get_free_tcp_port` leaks
  one, which the suite's ResourceWarning filter (080) turns into an error.

They run locally only, through `scripts/ui_tests.sh`. A CI job was built and dropped:
on GitHub's runners the client segfaults about 2 s after it starts, under `flutter test`
only. The same build started on its own runs fine there, and every test passes locally
(Ubuntu 24.04 under WSL, Mesa 25.2.8, no AVX-512). What the CI runs showed:

- The core dump's backtrace runs GTK draw → `libflutter_linux_gtk.so` → Mesa's
  `libgallium` → a `memcpy` in libc that reads unmapped memory.
- It is not Chronicler or the Python side: `flutter test` on the client alone, with no
  app to connect to, crashes the same way.
- Not the Mesa version: `ubuntu-latest` had Mesa 26.0.8, and `ubuntu-24.04` with Mesa
  25.2.8, the version that works locally, crashes too.
- Not glibc's AVX-512 routines (the runners have AVX-512): with them turned off through
  `GLIBC_TUNABLES` the same copy faults in the AVX2 routine.
- With software GL on or off, and with `GALLIUM_DRIVER=softpipe` instead of llvmpipe,
  the tests still fail. The softpipe run was not backtraced.

Left open, if CI is wanted later: a backtrace with Flutter engine symbols, to see which
buffer the engine hands Mesa; `GDK_GL=disable` or another way to keep the client off GL;
an older runner image or another Flutter version. The job lives in this ticket's PR
history.

### related tickets

- (RELATED) [027-M7_refresh_view_in_place](027-M7_refresh_view_in_place.md): the kind of bug this would catch
- (RELATED) [073-M14_dismissed_dialogs_hang](073-M14_dismissed_dialogs_hang.md): another, found only by reading Flet's source
