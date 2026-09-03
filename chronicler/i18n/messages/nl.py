"""Dutch message catalogue."""

MESSAGES = {
    "app": {
        "tagline": "Bewaar gesprekken.",
    },
    "nav": {
        "archive": "Archief",
        "tasks": "Taken",
        "settings": "Instellingen",
    },
    "common": {
        "cancel": "Annuleren",
        "save": "Opslaan",
        "delete": "Verwijderen",
        "close": "Sluiten",
        "refresh": "Vernieuwen",
        "browse": "Bladeren",
        "unknown": "Onbekend",
        "none": "Geen",
    },
    "settings": {
        "title": "Instellingen",
        "subtitle": "Voorkeuren voor deze machine en werkruimte.",
        "appearance": {
            "title": "Weergave",
            "dark_mode": "Donkere werkruimte",
            "dark_mode_description": (
                "Een gedempte interface voor het lezen van lange transcripten."
            ),
            "language": "Taal van de interface",
            "language_description": "De taal waarin Chronicler zijn eigen labels toont.",
        },
        "workspace": {
            "title": "Werkruimte",
            "local": "Lokale werkruimte",
            "not_configured": "Niet ingesteld",
            "not_configured_thin": "Niet ingesteld (thin client)",
            "choose": "Kies een werkruimtemap",
            "changed": "Werkruimte ingesteld op {path}. Herstart Chronicler om hem te gebruiken.",
        },
        "connection": {
            "title": "Verbinding",
            "remote_server": "Externe server",
            "service_layer": "Servicelaag",
            "local_ready": "Lokale services zijn klaar voor gebruik.",
            "thin_client": "Thin client",
            "full_stack": "Volledige installatie",
        },
        "transcription": {
            "title": "Standaardwaarden transcriptie",
            "subtitle": (
                "De startwaarden voor een transcriptietaak. Elke waarde is per taak aan te passen."
            ),
            "language": "Taal van de opname",
            "language_description": "Laat leeg om de taal per opname te laten detecteren.",
            "model_size": "Whisper-model",
            "model_size_description": "Grotere modellen zijn nauwkeuriger en langzamer.",
            "no_speech_threshold": "Stiltedrempel",
            "no_speech_threshold_description": (
                "Hoe zeker het model moet zijn dat een fragment stilte is voordat het "
                "wordt weggelaten. Verhoog dit als er verzonnen zinnen verschijnen."
            ),
            "normalize_first": "Audio normaliseren voor transcriptie",
            "normalize_first_description": (
                "Egaliseer elke opname eerst. Al genormaliseerde opnames worden overgeslagen."
            ),
        },
        "extras": {
            "title": "Optionele onderdelen",
            "auto_install": "Installeren zonder te vragen",
            "auto_install_description": (
                "Download en installeer een optioneel onderdeel zodra een functie "
                "het nodig heeft, in plaats van eerst te bevestigen."
            ),
        },
        "cleaning": {
            "title": "Opschonen",
            "hallucination_phrases": "Gehallucineerde zinnen",
            "hallucination_phrases_description": (
                "Eén per regel. Regels die hieraan voldoen worden als modelartefact verwijderd."
            ),
            "hallucination_match": "Zinvergelijking",
            "hallucination_match_description": (
                "Hoe zinnen worden vergeleken: normalized negeert hoofdletters en leestekens."
            ),
            "repetition_window": "Herhaalvenster (seconden)",
            "repetition_window_description": (
                "Een spreker die binnen dit venster dezelfde regel herhaalt geldt als lus."
            ),
            "strip_patterns": "Verwijderpatronen",
            "strip_patterns_description": (
                "Reguliere expressies die uit elke regel worden verwijderd. Eén per regel."
            ),
        },
        "restore_defaults": "Standaardwaarden herstellen",
        "llm": {
            "title": "Taalmodel",
            "provider": "Aanbieder",
            "provider_description": "Waar samenvattingen worden gemaakt.",
            "provider_none": "Uitgeschakeld",
            "provider_openai_compatible": "OpenAI-compatibele server",
            "provider_llama_cpp": "Lokaal modelbestand",
            "base_url": "Server-URL",
            "base_url_description": "Bijvoorbeeld http://localhost:8080/v1",
            "api_key": "API-sleutel",
            "model": "Modelnaam",
            "model_path": "Modelbestand (.gguf)",
            "test": "Verbinding testen",
            "test_ok": "Verbonden met {model}.",
            "test_failed": "Kan het model niet bereiken: {error}",
            "not_configured": "Niet ingesteld",
        },
        "saved": "Instellingen opgeslagen.",
        "save_failed": "Kan instellingen niet opslaan: {error}",
    },
    "archive": {
        "title": "Archief",
        "empty": "Nog geen kronieken.",
        "search": "Zoek in kronieken",
        "new": "Nieuwe kroniek",
        "import": "Importeren",
        "speakers": "{count} sprekers",
        "no_tags": "Geen labels",
        "unknown_duration": "Onbekende duur",
    },
    "tasks": {
        "title": "Taken",
        "empty": "Nog geen taken.",
        "retry": "Opnieuw",
        "status": "Status: {status}",
        "queued_import": "Transcript-import in de wachtrij",
        "queued_append": "Transcript-toevoeging in de wachtrij",
        "queued_clean": "Opschoontaak in de wachtrij",
        "queued_normalize": "Normalisatie van '{name}' in de wachtrij",
        "queued_transcribe": "Transcriptie van '{name}' als {speaker} in de wachtrij",
    },
    "transcript": {
        "title": "Transcript",
        "loading": "Transcript laden...",
        "empty": "Transcript is leeg of wordt nog verwerkt.",
        "error": "Fout bij laden van transcript: {error}",
        "show_timestamps": "Tijdcodes tonen",
        "chronicle": "Kroniek",
        "speakers": "Sprekers",
        "speakers_identified": "{count} herkend",
        "tags": "Labels",
    },
    "actions": {
        "import_audio": "Audio importeren",
        "import_transcript": "Transcript importeren",
        "clean": "Transcript opschonen",
        "clean_queued": "Opschoontaak in de wachtrij",
        "identify_speakers": "Sprekers herkennen",
        "speakers_found": "{count} spreker(s) gevonden",
        "summarize": "Samenvatting maken",
        "summarize_unavailable": "Stel een AI-model in om samenvattingen te gebruiken",
        "edit": "Kroniek bewerken",
        "updated": "Kroniek bijgewerkt",
        "gone": "Deze kroniek bestaat niet meer.",
        "delete": "Kroniek verwijderen",
        "delete_title": "Kroniek verwijderen?",
        "delete_message": (
            "Dit verwijdert '{title}', het transcript en alle taken in de wachtrij "
            "definitief. Dit kan niet worden teruggedraaid."
        ),
        "deleted": "'{title}' verwijderd",
        "failed": "Fout: {error}",
        "transcript_exists_title": "Er is al een transcript",
        "transcript_exists_message": (
            "Deze kroniek heeft al een geimporteerd transcript. Overschrijven met het "
            "nieuwe bestand, of de regels eraan toevoegen?"
        ),
        "append": "Toevoegen",
        "overwrite": "Overschrijven",
    },
    "sources": {
        "title": "Bronnen",
        "empty": "Nog geen audiobronnen.",
        "no_speaker": "Geen spreker",
        "missing": "Ontbreekt",
        "missing_cannot_transcribe": "'{name}' staat niet meer op schijf.",
        "transcribed": "Getranscribeerd",
        "transcribing": "Transcriberen",
        "normalize": "Dit spoor normaliseren",
        "normalized": "Genormaliseerd",
        "failed": "Mislukt",
        "record": "Nieuwe bron opnemen",
        "speaker_saved": "Spreker ingesteld op {speaker}",
    },
    "transcribe": {
        "title": "{name} transcriberen",
        "message": (
            "Deze waarden gelden alleen voor deze run; de standaarden staan in Instellingen."
        ),
        "speaker": "Spreker",
        "speaker_required": "Kies of typ een sprekernaam",
        "language": "Taal",
        "model": "Whisper-model",
        "threshold": "Stiltedrempel",
        "threshold_invalid": "Voer een getal tussen 0 en 1 in",
        "normalize_first": "Eerst audio normaliseren",
        "already_normalized": "Er is al een genormaliseerde kopie; die wordt gebruikt.",
        "save_speaker": "Alleen spreker opslaan",
        "start": "Transcriptie starten",
        "start_again": "Opnieuw transcriberen",
    },
    "recording": {
        "no_devices": "Geen audio-invoerapparaten gevonden. Op WSL is WSLg nodig voor invoer.",
        "title": "Bron opnemen",
        "device": "Invoerapparaat",
        "name": "Bestandsnaam",
        "default_name": "opname.wav",
        "ready": "Klaar om op te nemen.",
        "recording": "Bezig met opnemen...",
        "recorded": "{seconds}s opgenomen.",
        "start": "Starten",
        "stop": "Stoppen",
        "save": "Opslaan in kroniek",
        "saved": "'{name}' toegevoegd aan deze kroniek",
        "failed": "Kan de opname niet opslaan: {error}",
        "unavailable": "Opnemen is niet beschikbaar in deze sessie.",
    },
    "summaries": {
        "title": "Samenvattingen",
        "empty": "Nog geen samenvattingen.",
        "generate": "Genereer een samenvatting",
        "generate_action": "Genereren",
        "generate_message": "Laat de instructie leeg voor de ingestelde standaard.",
        "queued": "Samenvattingstaak in de wachtrij",
        "read": "Lees deze samenvatting",
        "untitled": "Naamloos",
        "model": "Model",
        "name": "Naam",
        "prompt": "Instructie",
        "prompt_hint": "Hoe moet deze samenvatting geschreven worden?",
        "delete_title": "Samenvatting verwijderen",
        "delete_message": (
            "Samenvatting {number} verwijderen? Dit kan niet ongedaan worden gemaakt."
        ),
        "read_transcript": "Lees het volledige transcript",
        "open_folder": "Open de kroniekmap",
        "folder_failed": "Kan de map niet openen: {error}",
        "record": "Neem een bron op",
    },
    "export": {
        "menu": "Exporteren",
        "tooltip": "Transcript exporteren",
        "plaintext": "Platte tekst (.txt)",
        "plaintext_timestamps": "Platte tekst met tijdcodes (.txt)",
        "srt": "Ondertitels (.srt)",
        "html": "HTML (binnenkort)",
        "pdf": "PDF (binnenkort)",
        "zip": "Kroniek .zip (binnenkort)",
        "saved": "Geëxporteerd naar {path}",
        "failed": "Fout bij exporteren: {error}",
        "write_failed": "Fout bij schrijven van bestand: {error}",
        "no_picker": "Bestandskiezer niet beschikbaar.",
    },
    "extras": {
        "title": "Extra onderdeel nodig",
        "message": (
            "{purpose} heeft een onderdeel nodig dat nog niet is geïnstalleerd: "
            "{requirement} ({size} download). Nu installeren?"
        ),
        "remember": "Optionele onderdelen zonder vragen installeren",
        "not_now": "Niet nu",
        "install": "Installeren",
        "installing": "{name} wordt geïnstalleerd ({size})...",
        "installed": "{name} is klaar voor gebruik",
        "failed": "Kan {name} niet installeren: {error}",
    },
}
