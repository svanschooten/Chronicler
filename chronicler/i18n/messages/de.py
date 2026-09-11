"""German message catalogue."""

MESSAGES = {
    "app": {
        "name": "Chronicler",
        "tagline": "Gespräche bewahren.",
    },
    "nav": {
        "archive": "Archiv",
        "tasks": "Aufgaben",
        "settings": "Einstellungen",
    },
    "common": {
        "cancel": "Abbrechen",
        "save": "Speichern",
        "delete": "Löschen",
        "close": "Schließen",
        "unknown": "Unbekannt",
    },
    "settings": {
        "title": "Einstellungen",
        "subtitle": "Einstellungen für diesen Rechner und Arbeitsbereich.",
        "appearance": {
            "title": "Darstellung",
            "dark_mode": "Dunkler Arbeitsbereich",
            "dark_mode_description": "Eine gedämpfte Oberfläche zum Lesen langer Transkripte.",
            "language": "Sprache der Oberfläche",
            "language_description": (
                "Die Sprache, in der Chronicler seine eigenen Beschriftungen anzeigt."
            ),
        },
        "workspace": {
            "title": "Arbeitsbereich",
            "local": "Lokaler Arbeitsbereich",
            "not_configured": "Nicht eingerichtet",
            "not_configured_thin": "Nicht eingerichtet (Thin Client)",
            "choose": "Ordner für den Arbeitsbereich wählen",
            "changed": "Arbeitsbereich auf {path} gesetzt. Starten Sie Chronicler neu.",
        },
        "connection": {
            "title": "Verbindung",
            "remote_server": "Entfernter Server",
            "service_layer": "Dienstschicht",
            "local_ready": "Lokale Dienste sind bereit.",
            "thin_client": "Thin Client",
            "server_side": (
                "Transkription, Normalisierung und Zusammenfassungen laufen auf dem Server, "
                "mit dessen Konfiguration."
            ),
            "full_stack": "Vollinstallation",
        },
        "transcription": {
            "title": "Standardwerte für Transkription",
            "subtitle": (
                "Die Startwerte einer Transkriptionsaufgabe. Jeder Wert ist pro Aufgabe änderbar."
            ),
            "language": "Sprache der Aufnahme",
            "language_description": "Leer lassen, um die Sprache je Aufnahme zu erkennen.",
            "model_size": "Whisper-Modell",
            "model_size_description": "Größere Modelle sind genauer und langsamer.",
            "no_speech_threshold": "Stilleschwelle",
            "no_speech_threshold_description": (
                "Wie sicher das Modell sein muss, dass ein Abschnitt Stille ist, bevor er "
                "verworfen wird. Erhöhen Sie den Wert bei erfundenen Sätzen."
            ),
            "normalize_first": "Audio vor der Transkription normalisieren",
            "normalize_first_description": (
                "Jede Aufnahme zuerst angleichen. Bereits normalisierte Aufnahmen werden "
                "übersprungen."
            ),
        },
        "extras": {
            "title": "Optionale Komponenten",
            "auto_install": "Ohne Rückfrage installieren",
            "auto_install_description": (
                "Eine optionale Komponente herunterladen und installieren, sobald "
                "eine Funktion sie braucht, statt vorher zu bestätigen."
            ),
        },
        "cleaning": {
            "title": "Bereinigung",
            "hallucination_phrases": "Halluzinierte Phrasen",
            "hallucination_phrases_description": (
                "Eine pro Zeile. Passende Zeilen werden als Modellartefakt entfernt."
            ),
            "hallucination_match": "Phrasenvergleich",
            "hallucination_match_description": (
                "Wie Phrasen verglichen werden: normalized ignoriert Groß- und Kleinschreibung "
                "sowie Satzzeichen."
            ),
            "repetition_window": "Wiederholungsfenster (Sekunden)",
            "repetition_window_description": (
                "Wiederholt eine Sprecherin dieselbe Zeile in diesem Fenster, gilt das als "
                "Schleife."
            ),
            "strip_patterns": "Entfernungsmuster",
            "strip_patterns_description": (
                "Reguläre Ausdrücke, die aus jeder Zeile entfernt werden. Einer pro Zeile."
            ),
        },
        "restore_defaults": "Standardwerte wiederherstellen",
        "llm": {
            "title": "Sprachmodell",
            "provider": "Anbieter",
            "provider_description": "Wo Zusammenfassungen erzeugt werden.",
            "provider_none": "Deaktiviert",
            "provider_openai_compatible": "OpenAI-kompatibler Server",
            "provider_llama_cpp": "Lokale Modelldatei",
            "base_url": "Server-URL",
            "base_url_description": "Zum Beispiel http://localhost:8080/v1",
            "api_key": "API-Schlüssel",
            "model": "Standardmodell",
            "model_description": "Im Zusammenfassungsdialog vorausgewaehlt. Optional.",
            "api_key_description": "Leer lassen, wenn das Gateway keinen braucht.",
            "model_path_description": "Die zu ladende .gguf-Datei.",
            "model_path": "Modelldatei (.gguf)",
            "test": "Verbindung testen",
            "test_ok": "Mit {model} verbunden.",
            "test_failed": "Modell nicht erreichbar: {error}",
            "testing": "Wird geprueft...",
            "test_empty": "Verbunden, aber es wurden keine Modelle aufgelistet.",
            "not_configured": "Nicht eingerichtet",
        },
        "saved": "Einstellungen gespeichert.",
        "save_failed": "Einstellungen konnten nicht gespeichert werden: {error}",
    },
    "forms": {
        "regex_hint": "z. B. ^([A-Z]+):\\s+(.*)$",
        "chronicle_title": "Titel der Chronicle",
        "create_title": "Neue Chronicle anlegen",
        "create": "Anlegen",
        "title": "Titel",
        "description": "Beschreibung",
        "kind": "Art",
        "kind_hint": "z. B. Podcast, D&D-Sitzung, Besprechung",
        "duration": "Dauer",
        "duration_hint": "z. B. 1h 24m",
        "edit_title": "Chronicle bearbeiten",
        "regex": "Zeilenmuster",
        "speaker_group": "Gruppenindex Sprecher",
        "text_group": "Gruppenindex Text",
        "timestamp_group": "Gruppenindex Zeitstempel (optional)",
        "timestamp_group_hint": "Leer lassen, wenn die Datei keine Zeitstempel hat",
        "select_and_import": "Datei waehlen und importieren",
    },
    "archive": {
        "subtitle": "Deine eigenstaendigen Gespraechsprojekte.",
        "import_into": "In diese Chronicle importieren",
        "no_description": "Keine Beschreibung",
        "link": "Externe Chronicle verknuepfen",
        "load_failed": "Fehler beim Laden der Chronicles: {error}",
        "title": "Archiv",
        "empty": "Noch keine Chronicles.",
        "search": "Chronicles durchsuchen",
        "new": "Neue Chronicle",
        "import": "Importieren",
        "speakers": "{count} Sprecher",
        "no_tags": "Keine Schlagwörter",
        "unknown_duration": "Unbekannte Dauer",
    },
    "tasks": {
        "heading": "Aufgaben verarbeiten",
        "subtitle": "Scribes arbeiten weiter, auch wenn du Chronicler schliesst.",
        "search": "Aufgaben suchen",
        "hide_completed": "Erledigte Aufgaben ausblenden",
        "retry_tooltip": "Diese Aufgabe erneut ausfuehren",
        "empty": "Noch keine Aufgaben.",
        "queued_normalize": "Normalisierung von '{name}' eingereiht",
        "queued_transcribe": "Transkription von '{name}' als {speaker} eingereiht",
    },
    "transcript": {
        "edit": "Transkript bearbeiten",
        "done": "Bearbeitung beenden",
        "delete_line": "Diese Zeile loeschen",
        "fullscreen": "Vollbild",
        "fullscreen_exit": "Vollbild verlassen",
        "delete_line_title": "Diese Zeile loeschen?",
        "delete_line_message": (
            'Damit wird "{excerpt}" aus dem Transkript entfernt. '
            "Das kann nicht rueckgaengig gemacht werden."
        ),
        "save_failed": "Aenderung konnte nicht gespeichert werden: {error}",
        "title": "Transkript",
        "loading": "Transkript wird geladen...",
        "empty": "Transkript ist leer oder wird noch verarbeitet.",
        "error": "Fehler beim Laden des Transkripts: {error}",
        "show_timestamps": "Zeitstempel anzeigen",
        "chronicle": "Chronicle",
        "speakers": "Sprecher",
        "speakers_identified": "{count} erkannt",
        "tags": "Schlagwörter",
    },
    "actions": {
        "import_audio": "Audio importieren",
        "import_transcript": "Transkript importieren",
        "clean": "Transkript bereinigen",
        "clean_queued": "Bereinigungsaufgabe eingereiht",
        "identify_speakers": "Sprecher erkennen",
        "speakers_found": "{count} Sprecher gefunden",
        "summarize": "Zusammenfassung erstellen",
        "summarize_unavailable": "KI-Modell einrichten, um Zusammenfassungen zu nutzen",
        "edit": "Chronicle bearbeiten",
        "updated": "Chronicle aktualisiert",
        "gone": "Diese Chronicle existiert nicht mehr.",
        "delete": "Chronicle loeschen",
        "delete_title": "Chronicle loeschen?",
        "delete_message": (
            "Damit werden '{title}', ihr Transkript und alle eingereihten Aufgaben "
            "endgueltig geloescht. Das kann nicht rueckgaengig gemacht werden."
        ),
        "deleted": "'{title}' geloescht",
        "delete_failed": "Chronik konnte nicht geloescht werden: {error}",
        "failed": "Fehler: {error}",
        "transcript_exists_title": "Es gibt schon ein Transkript",
        "transcript_exists_message": (
            "Diese Chronicle hat bereits ein importiertes Transkript. Mit der neuen Datei "
            "ueberschreiben oder deren Zeilen anhaengen?"
        ),
        "append": "Anhaengen",
        "overwrite": "Ueberschreiben",
    },
    "sources": {
        "title": "Quellen",
        "empty": "Noch keine Audioquellen.",
        "no_speaker": "Kein Sprecher",
        "missing": "Fehlt",
        "missing_cannot_transcribe": "'{name}' liegt nicht mehr auf der Festplatte.",
        "transcribed": "Transkribiert",
        "transcribing": "Wird transkribiert",
        "normalize": "Diese Spur normalisieren",
        "normalized": "Normalisiert",
        "failed": "Fehlgeschlagen",
        "record": "Neue Quelle aufnehmen",
        "speaker_saved": "Sprecher auf {speaker} gesetzt",
    },
    "transcribe": {
        "title": "{name} transkribieren",
        "message": (
            "Diese Werte gelten nur fuer diesen Lauf; die Standardwerte "
            "stehen in den Einstellungen."
        ),
        "speaker": "Sprecher",
        "speaker_required": "Sprechernamen waehlen oder eingeben",
        "language": "Sprache",
        "model": "Whisper-Modell",
        "threshold": "Stilleschwelle",
        "threshold_invalid": "Zahl zwischen 0 und 1 eingeben",
        "normalize_first": "Audio zuerst normalisieren",
        "already_normalized": "Eine normalisierte Kopie ist vorhanden und wird verwendet.",
        "save_speaker": "Nur Sprecher speichern",
        "start": "Transkription starten",
        "start_again": "Erneut transkribieren",
    },
    "recording": {
        "no_devices": "Keine Audioeingabegeräte gefunden. Unter WSL wird dafür WSLg benötigt.",
        "title": "Quelle aufnehmen",
        "device": "Eingabegerät",
        "name": "Dateiname",
        "default_name": "aufnahme.wav",
        "ready": "Bereit zur Aufnahme.",
        "recording": "Nimmt auf...",
        "recorded": "{seconds}s aufgenommen.",
        "start": "Starten",
        "stop": "Stoppen",
        "save": "In Chronicle speichern",
        "saved": "'{name}' zur Chronicle hinzugefügt",
        "failed": "Aufnahme konnte nicht gespeichert werden: {error}",
        "unavailable": "Aufnahme ist in dieser Sitzung nicht verfügbar.",
    },
    "summaries": {
        "title": "Zusammenfassungen",
        "empty": "Noch keine Zusammenfassungen.",
        "generate": "Zusammenfassung erzeugen",
        "generate_action": "Erzeugen",
        "generate_message": "Lassen Sie die Anweisung leer, um die Voreinstellung zu verwenden.",
        "queued": "Zusammenfassung eingereiht",
        "read": "Diese Zusammenfassung lesen",
        "untitled": "Ohne Titel",
        "model": "Modell",
        "name": "Name",
        "prompt": "Anweisung",
        "prompt_hint": "Wie soll diese Zusammenfassung geschrieben werden?",
        "delete_title": "Zusammenfassung löschen",
        "delete_message": (
            "Zusammenfassung {number} löschen? Das kann nicht rückgängig gemacht werden."
        ),
        "read_transcript": "Vollständiges Transkript lesen",
        "open_folder": "Chronicle ordner öffnen",
        "folder_failed": "Ordner konnte nicht geöffnet werden: {error}",
    },
    "export": {
        "menu": "Exportieren",
        "tooltip": "Transkript exportieren",
        "plaintext": "Klartext (.txt)",
        "plaintext_timestamps": "Klartext mit Zeitstempeln (.txt)",
        "srt": "Untertitel (.srt)",
        "html": "HTML (.html)",
        "pdf": "PDF (.pdf)",
        "zip": "Chronicle-.zip (in Kürze)",
        "saved": "Exportiert nach {path}",
        "failed": "Fehler beim Exportieren: {error}",
        "write_failed": "Fehler beim Schreiben der Datei: {error}",
        "no_picker": "Dateiauswahl nicht verfügbar.",
    },
    "extras": {
        "title": "Zusatzkomponente erforderlich",
        "message": (
            "{purpose} benötigt eine noch nicht installierte Komponente: {requirement} "
            "({size} Download). Jetzt installieren?"
        ),
        "remember": "Optionale Komponenten ohne Rückfrage installieren",
        "not_now": "Jetzt nicht",
        "install": "Installieren",
        "installing": "{name} wird installiert ({size})...",
        "installed": "{name} ist einsatzbereit",
        "failed": "{name} konnte nicht installiert werden: {error}",
    },
    "wizard": {
        "title": "Willkommen bei Chronicler",
        "subtitle": "Ein paar Fragen und dein Archiv ist bereit.",
        "back": "Zurück",
        "next": "Weiter",
        "finish": "Fertigstellen",
        "step": "Schritt {number} von {total}",
        "language": {
            "title": "Sprache wählen",
            "description": (
                "Wird für Chroniclers eigene Beschriftungen und als Standard für neue "
                "Transkriptionen verwendet."
            ),
            "label": "Sprache",
        },
        "mode": {
            "title": "Wie soll Chronicler laufen?",
            "description": "Das lässt sich später in den Einstellungen ändern.",
            "full_stack": "Vollständig lokal",
            "full_stack_description": "Alles auf diesem Rechner speichern und verarbeiten.",
            "thin_client": "Thin Client",
            "thin_client_description": (
                "Mit einem Chronicler-Server verbinden, der die Arbeit übernimmt."
            ),
            "server_note": (
                "Chronicler als Server oder Web-Client wird im Terminal eingerichtet: "
                "mit dem Argument 'server' oder 'web' starten."
            ),
        },
        "workspace": {
            "title": "Arbeitsordner wählen",
            "description": "Deine Chronicles, Aufnahmen und Datenbanken liegen hier.",
            "label": "Arbeitsordner",
            "browse": "Durchsuchen",
            "picker_title": "Arbeitsordner wählen",
            "required": "Wähle einen Ordner, um fortzufahren.",
        },
        "api_key": {
            "title": "API-Schlüssel",
            "description": (
                "Nur nötig, um diesen Rechner von einem anderen Chronicler-Client zu "
                "erreichen. Überspringe ihn, wenn du dieses Archiv allein nutzt."
            ),
            "label": "API-Schlüssel",
            "generate": "Neuen Schlüssel erzeugen",
            "skip": "Überspringen",
        },
        "server": {
            "title": "Mit deinem Server verbinden",
            "description": "Chronicler nutzt diesen Server für Speicherung und Verarbeitung.",
            "url_label": "Serveradresse",
            "url_hint": "http://localhost:8000",
            "url_required": "Eine Serveradresse ist erforderlich.",
            "key_label": "API-Schlüssel",
            "key_description": (
                "Frage den Serverbetreiber nach dem Schlüssel - er muss übereinstimmen und "
                "kann hier nicht erzeugt werden."
            ),
            "key_required": "Ein API-Schlüssel ist erforderlich.",
        },
        "saving": {
            "title": "Arbeitsordner wird eingerichtet",
            "saved": "Konfiguration gespeichert unter {path}",
        },
    },
    "startup": {
        "failed": "Chronicler konnte nicht starten",
        "hint": (
            "Prüfe die Verbindungseinstellungen in deiner Konfigurationsdatei und starte "
            "Chronicler erneut."
        ),
    },
}
