# 013-H2_web_client_open_proxy

## The web client exposes the full API with no login

### info

| | |
| --- | --- |
| importance | high |
| danger level | High: anyone who can reach port 8080 can delete data or write files on the server. Change risk: none. |
| reach | Anyone running `chronicler web` on a network |
| effort | none beyond the removal |
| evidence | read in code |
| touches | `chronicler/webclient/main.py`, `chronicler/__main__.py`, `chronicler/webclient/src/index.html` |

### description

`/api/{service}/{method}` (`webclient/main.py:62-87`) forwards any method using the
server's API key, with no login, and the default bind is `0.0.0.0` (`__main__.py:136`).
The page uses 3 methods and the proxy exposes all 36.

Anyone who can reach the port can delete chronicles, or call `link_external_chronicle`,
which creates and migrates an SQLite file at any path on the server. `docs/security.md`
reports that the browser never sees the key, which is true but does not help here.

Vue also loads from `unpkg.com/vue@3` (`index.html:7`), an unpinned range with no
integrity check.

### related tickets

- (CLOSED BY) [012-S14_remove_web_client](012-S14_remove_web_client.md): the proxy no longer exists
