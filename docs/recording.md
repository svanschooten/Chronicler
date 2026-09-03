# Recording

`chronicler/core/recording/`, `chronicler/desktop/views/transcript/recording.py`

A "Record a source" action inside a Chronicle: pick an input device, record, stop, and the
WAV lands in that chronicle's `sources/` with a source record already created.

16 kHz mono `int16` — the format Whisper wants, so no resampling is needed later. Taken
from the prototype's one genuinely good live-audio detail.

## How it works over RPC in thin-client mode

**It needs no new RPC at all**, and that is the design rather than a shortcut.

The microphone is on the machine running the interface. There is no sensible meaning to
"the server records" when the server is in another room, so the recorder always runs
client-side regardless of deployment mode.

```text
Recorder  →  temp .wav  →  FileStager.stage()  →  ChronicleService.add_audio_source()
                              │
                              ├─ LocalFileStager   copies into the workspace
                              └─ RemoteFileStager  uploads via POST /upload
```

That is exactly the path a file picked from disk already takes. Recording is a new way to
*produce* a file, not a new way to move one — so it inherits the upload, the path
confinement and the source registration for free, and behaves identically in both modes.

Live streaming of audio to the server for real-time transcription is a genuinely different
feature: it needs a persistent connection, a streaming protocol and incremental
transcription, none of which exist. It is deliberately out of scope here.

## Threading

`sounddevice` delivers audio on its own callback thread. Blocks go onto a queue, and a
writer thread drains it into the WAV file — the callback never touches the filesystem,
because blocking in an audio callback drops samples.

`stop()` stops the stream first, then joins the writer, so anything still queued is
written before the file is closed.

## Optional extra

`sounddevice` is the optional `recording` extra, imported lazily. A missing extra — or a
machine with no working audio backend, which raises `OSError` rather than `ImportError` —
produces one clear message naming the `pip install`, not a crash.

Device enumeration filters on `max_input_channels > 0` and keeps the backend's own index,
since that index is what selects the device when the stream opens.
