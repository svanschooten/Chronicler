# Testing the thin client

`scripts/thin_client_check.py`, `chronicler/core/handshake.py`,
`chronicler/core/services/system_service.py`

Three layers, from fastest to most realistic.

## 1. In-process integration tests

`tests/chronicler/server/test_rpc_routing.py` boots the real server ASGI app and drives a
real `RemoteContainer` against it — the same proxy the desktop thin client uses, not raw
HTTP. It covers the handshake succeeding, a version mismatch being refused, an
unreachable server, and a wrong API key.

These run in CI, so thin-client breakage fails a build rather than being found by hand.

## 2. Two processes on one machine

```bash
python scripts/thin_client_check.py
```

Starts a real `chronicler server` subprocess, waits for it to listen, then runs a real
handshake and round-trips a chronicle over RPC. Both sides get their own isolated config
through `CHRONICLER_CONFIG_FILE`, so your own `~/.chronicler_config.yaml` is never
touched and no workspace of yours is written to.

Expected output, where `<version>` is whatever release you are running:

```text
Chronicler <version> thin-client check
  server:  127.0.0.1:46095

Starting server...
  ok    server is listening

Connecting thin client...
  ok    server version <version> matches client <version>
  ok    capabilities: clean, export, import, transcribe
  ok    pulled chronicle list (0 chronicles)
  ok    round-tripped a chronicle over RPC (Thin client check)
  ok    cleaned up

PASS - the thin client can talk to the server.
```

## 3. Across your network

```bash
python scripts/thin_client_check.py --host 0.0.0.0 --port 8000 --keep-running
```

`--keep-running` leaves the server up after the check so another device can connect. It
prints the API key to use.

`chronicler server` also takes `--host` and `--port` directly:

```bash
python -m chronicler server --host 0.0.0.0 --port 8000
```

### WSL2 needs a port proxy

This is the step that otherwise costs an evening. **WSL2 runs behind its own NAT**, so
binding `0.0.0.0` inside WSL makes the server reachable from Windows, but *not* from
other devices on your network.

Find the WSL address:

```bash
hostname -I | awk '{print $1}'
```

Then, in **PowerShell as Administrator on Windows**:

```powershell
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<WSL_IP>
```

```powershell
New-NetFirewallRule -DisplayName "Chronicler" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

Other devices then connect to `http://<windows-machine-ip>:8000`.

To inspect or remove the rule later:

```powershell
netsh interface portproxy show v4tov4
```

```powershell
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
```

WSL's IP **changes on restart**, so the `portproxy` rule needs re-adding after a reboot.

## Configuring a real thin client

```yaml
server_url: http://192.168.1.20:8000
api_key: <the server's key>
mode: desktop:thin_client
```

Then `python -m chronicler desktop`. Use `--config` to keep it separate from a full-stack
install on the same machine.

## The handshake

A thin client verifies its server before showing any UI:

1. `SystemService.get_server_info()` — reachable, and what it can do
2. **Versions must match exactly.** `HandshakeError` on mismatch, and the desktop entry
   point exits with a clear message rather than failing later in a confusing way
3. `ChronicleService.list_chronicles()` — opening state, pulled once

Exact version matching is deliberate. The HTTP API is *generated* from the service
classes, so a signature change on either side silently changes the wire contract; there
is no independently versioned API surface to negotiate against. Matching versions is the
only honest compatibility statement available today.

A failure to list chronicles is logged but does not fail the handshake — the connection
is established, and an empty archive is a normal state.

The success line is deliberately greppable for log monitoring:

```text
Connected to Chronicler server (version <version>, chronicles: 3, capabilities: clean, export, import, transcribe)
```

## Capabilities

`ServerInfo.capabilities` reports which optional extras the **server** actually has
installed, so a client can tell that a server without the `transcription` extra cannot
transcribe — before queueing a task that would fail on the far side.
