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
        "refresh": "Aktualisieren",
        "browse": "Durchsuchen",
        "unknown": "Unbekannt",
        "none": "Keine",
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
            "full_stack": "Vollinstallation",
        },
        "transcription": {
            "title": "Transkription",
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
            "model": "Modellname",
            "model_path": "Modelldatei (.gguf)",
            "test": "Verbindung testen",
            "test_ok": "Mit {model} verbunden.",
            "test_failed": "Modell nicht erreichbar: {error}",
            "not_configured": "Nicht eingerichtet",
        },
        "saved": "Einstellungen gespeichert.",
        "save_failed": "Einstellungen konnten nicht gespeichert werden: {error}",
    },
    "archive": {
        "title": "Archiv",
        "empty": "Noch keine Chroniken.",
        "search": "Chroniken durchsuchen",
        "new": "Neue Chronik",
        "import": "Importieren",
        "speakers": "{count} Sprecher",
        "no_tags": "Keine Schlagwörter",
        "unknown_duration": "Unbekannte Dauer",
    },
    "tasks": {
        "title": "Aufgaben",
        "empty": "Noch keine Aufgaben.",
        "retry": "Erneut versuchen",
        "status": "Status: {status}",
        "queued_import": "Transkript-Import eingereiht",
        "queued_append": "Transkript-Anfügen eingereiht",
        "queued_clean": "Bereinigung eingereiht",
        "queued_normalize": "Normalisierung von '{name}' eingereiht",
        "queued_transcribe": "Transkription von '{name}' als {speaker} eingereiht",
    },
    "transcript": {
        "title": "Transkript",
        "loading": "Transkript wird geladen...",
        "empty": "Transkript ist leer oder wird noch verarbeitet.",
        "error": "Fehler beim Laden des Transkripts: {error}",
        "show_timestamps": "Zeitstempel anzeigen",
        "chronicle": "Chronik",
        "speakers": "Sprecher",
        "speakers_identified": "{count} erkannt",
        "tags": "Schlagwörter",
    },
    "sources": {
        "title": "Quellen",
        "empty": "Noch keine Audioquellen.",
        "transcribe": "Diese Aufnahme transkribieren",
        "transcribe_action": "Transkribieren",
        "no_speaker": "Kein Sprecher",
        "missing": "Fehlt",
        "missing_cannot_transcribe": "'{name}' liegt nicht mehr auf der Festplatte.",
        "transcribed": "Transkribiert",
        "transcribing": "Wird transkribiert",
        "normalize": "Diese Aufnahme normalisieren",
        "normalized": "Normalisiert",
        "failed": "Fehlgeschlagen",
        "record": "Neue Quelle aufnehmen",
        "assign_speaker": "Sprecher zuweisen",
        "speaker": "Sprecher",
        "new_speaker": "Neuer Sprecher",
        "ask_speaker_title": "'{name}' transkribieren",
        "ask_speaker_message": (
            "Welcher Sprecher ist diese Aufnahme? Eine Audioquelle enthält genau einen Sprecher - "
            "beim Transkribieren werden nur dessen Zeilen ersetzt."
        ),
    },
    "recording": {
        "title": "Quelle aufnehmen",
        "device": "Eingabegerät",
        "name": "Dateiname",
        "default_name": "aufnahme.wav",
        "ready": "Bereit zur Aufnahme.",
        "recording": "Nimmt auf...",
        "recorded": "{seconds}s aufgenommen.",
        "start": "Starten",
        "stop": "Stoppen",
        "save": "In Chronik speichern",
        "saved": "'{name}' zur Chronik hinzugefügt",
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
        "open_folder": "Chronikordner öffnen",
        "folder_failed": "Ordner konnte nicht geöffnet werden: {error}",
        "record": "Quelle aufnehmen",
    },
    "export": {
        "menu": "Exportieren",
        "tooltip": "Transkript exportieren",
        "plaintext": "Klartext (.txt)",
        "plaintext_timestamps": "Klartext mit Zeitstempeln (.txt)",
        "srt": "Untertitel (.srt)",
        "html": "HTML (in Kürze)",
        "pdf": "PDF (in Kürze)",
        "zip": "Chronik-.zip (in Kürze)",
        "saved": "Exportiert nach {path}",
        "failed": "Fehler beim Exportieren: {error}",
        "write_failed": "Fehler beim Schreiben der Datei: {error}",
        "no_picker": "Dateiauswahl nicht verfügbar.",
    },
}
