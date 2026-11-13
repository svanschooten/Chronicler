"""English message catalogue, and the reference every other locale is checked against."""

MESSAGES = {
    "app": {
        "name": "Chronicler",
        "tagline": "Preserve conversations.",
    },
    "nav": {
        "archive": "Archive",
        "tasks": "Tasks",
        "settings": "Settings",
    },
    "common": {
        "cancel": "Cancel",
        "save": "Save",
        "delete": "Delete",
        "close": "Close",
        "unknown": "Unknown",
        "ok": "OK",
        "thousands_separator": ",",
    },
    "settings": {
        "title": "Settings",
        "subtitle": "Preferences for this machine and workspace.",
        "appearance": {
            "title": "Appearance",
            "dark_mode": "Dark workspace",
            "dark_mode_description": "Use a low-light interface while reviewing long transcripts.",
            "language": "Interface language",
            "language_description": "The language Chronicler's own labels are shown in.",
        },
        "workspace": {
            "title": "Workspace",
            "local": "Local workspace",
            "not_configured": "Not configured",
            "not_configured_thin": "Not configured (thin client mode)",
            "choose": "Choose a workspace folder",
            "changed": "Workspace set to {path}. Restart Chronicler to use it.",
        },
        "connection": {
            "title": "Connection",
            "remote_server": "Remote server",
            "service_layer": "Service layer",
            "local_ready": "Local desktop services are ready to connect.",
            "thin_client": "Thin Client",
            "server_side": (
                "Transcription, normalisation and summaries run on the server, "
                "using its own configuration."
            ),
            "full_stack": "Full Stack",
        },
        "transcription": {
            "title": "Transcription defaults",
            "subtitle": (
                "The starting values for a transcribe task. Every one can be overridden per task."
            ),
            "language": "Transcription language",
            "language_description": "Leave blank to detect the language of each track.",
            "model_size": "Whisper model",
            "model_size_description": "Larger models are more accurate and slower to run.",
            "no_speech_threshold": "Silence threshold",
            "no_speech_threshold_description": (
                "How confident the model must be that a segment is silence before it is "
                "discarded. Raise it if you see invented phrases in quiet passages."
            ),
            "normalize_first": "Normalize audio before transcribing",
            "normalize_first_description": (
                "Level each track first. Already-normalized tracks are skipped."
            ),
        },
        "extras": {
            "title": "Optional components",
            "auto_install": "Install without asking",
            "auto_install_description": (
                "Download and install an optional component the moment a feature "
                "needs it, instead of confirming first."
            ),
        },
        "cleaning": {
            "title": "Cleaning",
            "hallucination_phrases": "Hallucinated phrases",
            "hallucination_phrases_description": (
                "One per line. Lines matching any of these are dropped as model artifacts."
            ),
            "hallucination_match": "Phrase matching",
            "hallucination_match_description": (
                "How phrases are compared: normalized ignores case and punctuation."
            ),
            "repetition_window": "Repeat window (seconds)",
            "repetition_window_description": (
                "A speaker repeating the same line inside this window is treated as a loop."
            ),
            "strip_patterns": "Strip patterns",
            "strip_patterns_description": (
                "Regular expressions removed from every line. One per line."
            ),
        },
        "restore_defaults": "Restore defaults",
        "llm": {
            "title": "Language model",
            "provider": "Provider",
            "provider_description": "Where summaries are generated.",
            "provider_none": "Disabled",
            "provider_openai_compatible": "OpenAI-compatible server",
            "provider_llama_cpp": "Local model file",
            "base_url": "Server URL",
            "base_url_description": "For example http://localhost:8080/v1",
            "api_key": "API key",
            "model": "Default model",
            "model_description": "Preselected in the summary dialog. Optional.",
            "api_key_description": "Leave empty for a gateway that needs none.",
            "model_path_description": "The .gguf file to load.",
            "model_path": "Model file (.gguf)",
            "test": "Test connection",
            "test_ok": "Connected to {model}.",
            "test_failed": "Could not reach the model: {error}",
            "testing": "Checking...",
            "test_empty": "Connected, but no models were listed.",
            "not_configured": "Not configured",
        },
        "saved": "Settings saved.",
        "save_failed": "Could not save settings: {error}",
    },
    "forms": {
        "regex_hint": "e.g. ^([A-Z]+):\\s+(.*)$",
        "chronicle_title": "Chronicle title",
        "create_title": "Create a new chronicle",
        "create": "Create",
        "title": "Title",
        "description": "Description",
        "kind": "Kind",
        "kind_hint": "e.g. Podcast, D&D session, Meeting",
        "duration": "Duration",
        "duration_hint": "e.g. 1h 24m",
        "edit_title": "Edit chronicle",
        "regex": "Line pattern",
        "speaker_group": "Speaker group index",
        "text_group": "Text group index",
        "timestamp_group": "Timestamp group index (optional)",
        "timestamp_group_hint": "Leave blank when the file has no timestamps",
        "select_and_import": "Select file and import",
    },
    "archive": {
        "subtitle": "Your self-contained conversation projects.",
        "import_into": "Import to this chronicle",
        "no_description": "No description",
        "link": "Link External Chronicle",
        "load_failed": "Error loading chronicles: {error}",
        "title": "Archive",
        "empty": "No chronicles yet.",
        "search": "Search chronicles and what was said in them",
        "new": "New Chronicle",
        "import": "Import",
        "speakers": "{count} speakers",
        "no_tags": "No tags",
        "unknown_duration": "Unknown duration",
        "in_transcripts": "Said in",
        "more_matches": "More lines match - search inside the chronicle to see them all.",
        "transcript_search_failed": "Could not search the transcripts: {error}",
    },
    "tasks": {
        "heading": "Processing tasks",
        "subtitle": "Scribes keep work moving, even when you close Chronicler.",
        "search": "Search tasks",
        "hide_completed": "Hide completed tasks",
        "clear_finished": "Clear finished tasks",
        "clear_title": "Clear finished tasks?",
        "clear_message": (
            "Completed tasks are removed from the list. "
            "Failed tasks keep their error unless you clear them too."
        ),
        "clear_cancel": "Cancel",
        "clear_done_only": "Completed only",
        "clear_with_failed": "Completed and failed",
        "cleared": "Cleared {count} tasks",
        "retry_tooltip": "Run this task again",
        "cancel_tooltip": "Cancel this task",
        "cancelled": "Task cancelled",
        "not_cancelled": "The task had already finished or cannot be stopped",
        "requeued": "Task re-queued",
        "load_failed": "Error loading tasks: {error}",
        "status": "Status: {status}",
        "created": "Created {time}",
        "next_attempt": "Next attempt {time}",
        "started": "Started {time}",
        "completed": "Completed {time}",
        "empty": "No tasks yet.",
        "queued_normalize": "Queued normalization of '{name}'",
        "queued_transcribe": "Queued transcription of '{name}' as {speaker}",
    },
    "transcript": {
        "edit": "Edit the transcript",
        "done": "Finish editing",
        "delete_line": "Delete this line",
        "line_window": "Lines {first}-{last} of {total}",
        "first_lines": "First lines",
        "previous_lines": "Previous lines",
        "next_lines": "Next lines",
        "last_lines": "Last lines",
        "fullscreen": "Full screen",
        "fullscreen_exit": "Leave full screen",
        "delete_line_title": "Delete this line?",
        "delete_line_message": (
            'This removes "{excerpt}" from the transcript. This cannot be undone.'
        ),
        "save_failed": "Could not save the change: {error}",
        "title": "Transcript",
        "loading": "Loading transcript...",
        "empty": "Transcript is empty or still processing.",
        "error": "Error loading transcript: {error}",
        "find": "Find in transcript",
        "no_matches": "No line contains '{query}'.",
        "match_count": "{count} matching lines",
        "match_count_capped": (
            "Showing the first {count} matching lines. Type more to narrow it down."
        ),
        "newer_version": (
            "This chronicle was made by a newer version of Chronicler. Update Chronicler to "
            "open it. The file was not changed."
        ),
        "show_timestamps": "Show timestamps",
        "chronicle": "Chronicle",
        "speakers": "Speakers",
        "speakers_identified": "{count} identified",
        "tags": "Tags",
    },
    "actions": {
        "import_audio": "Import audio",
        "import_transcript": "Import transcript",
        "clean": "Clean transcript",
        "clean_queued": "Clean task queued",
        "restore": "Restore previous version",
        "restore_title": "Restore a previous version?",
        "restore_message": (
            "Replaces the current transcript of '{title}' with a copy saved before a clean, "
            "an import or a re-transcription. The current version is saved first, so this "
            "can be undone."
        ),
        "restore_option": "{kind} - {time}",
        "snapshot_kind": {
            "clean": "Before cleaning",
            "import": "Before an import",
            "transcribe": "Before re-transcribing",
            "restore": "Before a restore",
        },
        "no_snapshots": "There is no earlier version to restore yet.",
        "restored": "Previous version restored",
        "audio_added": "Added audio source '{name}'",
        "audio_created": "Created '{title}' and added audio source",
        "import_created": "Created '{title}' and queued transcript import",
        "append_queued": "Transcript append task queued",
        "import_queued": "Transcript import task queued",
        "linked": "Linked '{title}' - {count} speaker(s)",
        "clean_title": "Clean transcript?",
        "clean_message": (
            "Cleaning '{title}' drops filler and repeated lines and merges consecutive turns. "
            "A copy of the transcript is saved first, in the chronicle's snapshots folder."
        ),
        "identify_speakers": "Identify speakers",
        "speakers_found": "Found {count} speaker(s)",
        "summarize": "Generate summary",
        "summarize_unavailable": "Configure an AI model to enable summaries",
        "edit": "Edit chronicle",
        "updated": "Chronicle updated",
        "gone": "This chronicle no longer exists.",
        "delete": "Delete chronicle",
        "delete_title": "Delete chronicle?",
        "delete_message": (
            "This permanently deletes '{title}', its transcript, and any queued tasks "
            "for it. This cannot be undone."
        ),
        "deleted": "Deleted '{title}'",
        "delete_failed": "Could not delete the chronicle: {error}",
        "failed": "Error: {error}",
        "link_not_found": "Cannot link {path}: the file was not found",
        "link_not_chronicler": "Cannot link {path}: it is not a Chronicler database",
        "link_newer_version": "Cannot link {path}: it was made by a newer version of Chronicler",
        "link_unreadable": "Cannot link {path}: it could not be read ({detail})",
        "link_not_allowed": (
            "Cannot link {path}: it is outside the folders the server allows chronicles in"
        ),
        "transcript_exists_title": "Transcript already exists",
        "transcript_exists_message": (
            "This chronicle already has an imported transcript. Overwrite it with the "
            "new file, or append the new file's lines to the end?"
        ),
        "append": "Append",
        "overwrite": "Overwrite",
    },
    "sources": {
        "title": "Sources",
        "empty": "No audio sources yet.",
        "no_speaker": "No speaker",
        "missing": "Missing",
        "missing_cannot_transcribe": "'{name}' is no longer on disk.",
        "transcribed": "Transcribed",
        "transcribing": "Transcribing",
        "normalize": "Normalize this track",
        "normalize_unavailable": "Loudness normalisation is not available here",
        "transcribe_unavailable": "Transcription is not available here",
        "record_unavailable": "Recording is not available in this build",
        "normalized": "Normalized",
        "failed": "Failed",
        "record": "Record a new source",
        "speaker_saved": "Speaker set to {speaker}",
    },
    "transcribe": {
        "title": "Transcribe {name}",
        "message": "These values apply to this run only; the defaults live in Settings.",
        "speaker": "Speaker",
        "speaker_required": "Pick or type a speaker name",
        "language": "Language",
        "model": "Whisper model",
        "threshold": "Silence threshold",
        "threshold_invalid": "Enter a number between 0 and 1",
        "normalize_first": "Normalize audio first",
        "already_normalized": "A normalized copy already exists and will be used.",
        "save_speaker": "Save speaker only",
        "start": "Start transcription",
        "start_again": "Transcribe again",
        "start_offset": "Start offset (seconds)",
        "start_offset_invalid": "Enter a number of seconds, 0 or more",
        "replaces_edits": (
            "This track is already transcribed. "
            "Transcribing it again replaces its lines, including any edits made to them."
        ),
    },
    "recording": {
        "no_devices": "No audio input devices were found. On WSL, audio input needs WSLg.",
        "title": "Record a source",
        "device": "Input device",
        "name": "File name",
        "default_name": "recording.wav",
        "ready": "Ready to record.",
        "recording": "Recording...",
        "recorded": "Recorded {seconds}s.",
        "start": "Start",
        "stop": "Stop",
        "save": "Save to chronicle",
        "saved": "Added '{name}' to this chronicle",
        "failed": "Could not save the recording: {error}",
        "unavailable": "Recording is not available in this session.",
    },
    "summaries": {
        "title": "Summaries",
        "empty": "No summaries yet.",
        "generate": "Generate a summary",
        "generate_action": "Generate",
        "generate_message": "Leave the prompt blank to use the configured default.",
        "queued": "Summary task queued",
        "read": "Read this summary",
        "untitled": "Untitled",
        "model": "Model",
        "name": "Name",
        "prompt": "Instruction",
        "prompt_hint": "How should this summary be written?",
        "delete_title": "Delete summary",
        "delete_message": "Delete summary {number}? This cannot be undone.",
        "read_transcript": "Read the full transcript",
        "open_folder": "Open the chronicle folder",
        "folder_failed": "Could not open the folder: {error}",
    },
    "export": {
        "menu": "Export",
        "tooltip": "Export transcript",
        "plaintext": "Plain text (.txt)",
        "plaintext_timestamps": "Plain text with timestamps (.txt)",
        "srt": "Subtitles (.srt)",
        "html": "HTML (.html)",
        "pdf": "PDF (.pdf)",
        "zip": "Chronicle archive (.zip)",
        "zip_title": "Export Chronicle archive",
        "zip_message": (
            "The archive holds this chronicle's own database - its transcript, speakers and "
            "summaries - so it can be opened as a linked chronicle elsewhere. Audio is much "
            "larger than the rest and is left out unless you ask for it."
        ),
        "zip_include_sources": "Include the audio sources",
        "zip_confirm": "Export",
        "saved": "Exported to {path}",
        "failed": "Error exporting transcript: {error}",
        "write_failed": "Error writing export file: {error}",
        "no_picker": "File picker not available.",
        "plaintext_title": "Export transcript as plain text",
    },
    "extras": {
        "title": "Extra component needed",
        "message": (
            "{purpose} needs a component that is not installed yet: {requirement} "
            "({size} download). Install it now?"
        ),
        "remember": "Install optional components without asking",
        "not_now": "Not now",
        "install": "Install",
        "installing": "Installing {name} ({size})...",
        "installed": "{name} is ready to use",
        "failed": "Could not install {name}: {error}",
        "purposes": {
            "transcription": "Transcribing audio with Whisper",
            "normalization": "Normalizing the loudness of an audio source",
            "llm": "Running a local GGUF language model for summaries",
            "recording": "Recording audio from a microphone",
            "server": "Running Chronicler as a server",
        },
        "notes": {
            "transcription": "The Whisper model is downloaded separately the first time it runs.",
            "llm": "Only needed for local models; a remote gateway needs nothing.",
            "recording": "sounddevice is a binding, not a bundle: it needs PortAudio.",
        },
    },
    "wizard": {
        "title": "Welcome to Chronicler",
        "subtitle": "A few questions and your archive is ready.",
        "back": "Back",
        "next": "Continue",
        "finish": "Finish",
        "step": "Step {number} of {total}",
        "language": {
            "title": "Choose your language",
            "description": (
                "Used for Chronicler's own labels and as the default for new transcriptions."
            ),
            "label": "Language",
        },
        "mode": {
            "title": "How should Chronicler run?",
            "description": "You can change this later under Settings.",
            "full_stack": "Full Stack",
            "full_stack_description": "Store and process everything on this machine.",
            "thin_client": "Thin Client",
            "thin_client_description": "Connect to a Chronicler Server that does the work.",
            "server_note": (
                "Running Chronicler as a server is set up from a terminal: "
                "start it with the 'server' argument."
            ),
        },
        "workspace": {
            "title": "Pick a workspace folder",
            "description": "Your chronicles, recordings and databases are kept here.",
            "label": "Workspace folder",
            "browse": "Browse",
            "picker_title": "Choose a workspace folder",
            "required": "Choose a folder to continue.",
            "not_writable": "Chronicler cannot write to this folder. Choose a different one.",
        },
        "api_key": {
            "title": "API key",
            "description": (
                "Needed only to reach this machine from another Chronicler client. "
                "Skip it if you are the only one using this archive."
            ),
            "label": "API key",
            "generate": "Generate a new key",
            "skip": "Skip",
        },
        "server": {
            "title": "Connect to your server",
            "description": "Chronicler will use this server for storage and processing.",
            "url_label": "Server address",
            "url_hint": "http://localhost:8000",
            "url_required": "A server address is required.",
            "key_label": "API key",
            "key_description": (
                "Ask the server operator for its key - it has to match, so it cannot be "
                "generated here."
            ),
            "key_required": "An API key is required.",
        },
        "saving": {
            "title": "Setting up your workspace",
            "saved": "Configuration saved to {path}",
        },
    },
    "startup": {
        "failed": "Chronicler could not start",
        "hint": (
            "Check the connection settings in your configuration file, then start Chronicler again."
        ),
        "workspace_locked": (
            "The workspace at {path} is already open in another Chronicler window or server."
        ),
        "workspace_locked_hint": "Close the other one, then start Chronicler again.",
        "workspace_lock_unavailable": (
            "Chronicler could not lock the workspace at {path}: {reason}."
        ),
        "workspace_lock_unavailable_hint": (
            "The filesystem it is on may not support file locks, as some network and FUSE "
            "mounts do not. Choose a workspace on a local disk, then start Chronicler again."
        ),
        "workspace_not_writable": ("Chronicler cannot write to the workspace at {path}: {reason}."),
        "workspace_not_writable_hint": (
            "Check the folder's permissions, or choose a different workspace, then start "
            "Chronicler again."
        ),
        "workspace_newer_version": (
            "The workspace at {path} was made by a newer version of Chronicler."
        ),
        "workspace_newer_version_hint": (
            "Update Chronicler to open it. Nothing in the workspace was changed."
        ),
    },
}
