# 014-M8_web_audio_upload_fails

## Audio uploads from the web client always fail

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: the upload fails with a confusing error. Change risk: none. |
| reach | Web client users |
| effort | none beyond the removal |
| evidence | reproduced |
| touches | `chronicler/webclient/src/app.js`, `chronicler/webclient/src/index.html` |

### description

The page invites an audio file (`index.html:166`), then always queues a text IMPORT
(`app.js:102`). The task fails with a UTF-8 decode error. The desktop fixed this same bug
on 2026-08-13, and `TODO.md:1297` marks the web version done.

### related tickets

- (CLOSED BY) [012-S14_remove_web_client](012-S14_remove_web_client.md): the page no longer exists
