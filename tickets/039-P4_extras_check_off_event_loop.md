# 039-P4_extras_check_off_event_loop

## Checking extras can stall startup

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a startup hitch. Change risk: very low. |
| reach | Startup, and each `get_server_info` until the imports are cached |
| effort | XS |
| evidence | measured |
| touches | `chronicler/core/services/system_service.py` |

### description

`capabilities_for` runs synchronously inside the async `get_server_info`, and
`extras.is_available` really imports each module. `import faster_whisper` took 3.1 s on
first run and 0.6 s warm.

### proposed fix

Run it with `await asyncio.to_thread(capabilities_for, self.settings)`.

The audit report suggested `find_spec` instead. Do not do that:
`docs/optional-extras.md:25-35` and `docs/testing.md:92-97` explain why availability has
to mean the import really worked, including for installed but unimportable packages.

Done when the event loop keeps running during the first check.

### related tickets

- none
