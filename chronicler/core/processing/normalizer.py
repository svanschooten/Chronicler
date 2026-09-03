"""Loudness normalisation of one audio source, via PyAV's libavfilter bindings."""

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chronicler.core.config_sections import NormalizationSettings

logger = logging.getLogger(__name__)

NORMALIZED_SUFFIX = ".normalized.wav"
TARGET_SAMPLE_RATE = 16000
SILENCE_DBFS = -120.0


class NormalizationError(RuntimeError):
    """The source could not be normalised."""


def _av():
    """PyAV, or a NormalizationError naming the extra that provides it."""
    try:
        import av
    except ImportError as error:
        raise NormalizationError(
            "Audio normalization requires the 'normalization' extra "
            "(pip install 'chronicler[normalization]')"
        ) from error
    return av


@dataclass(frozen=True)
class NormalizationResult:
    output_path: Path
    loudness_before: float | None
    loudness_after: float | None


def normalized_path_for(source: Path) -> Path:
    """`<stem>.normalized.wav` beside the source, never replacing the original."""
    stem = source.name[: -len(source.suffix)] if source.suffix else source.name
    return source.parent / f"{stem}{NORMALIZED_SUFFIX}"


def build_filter_description(settings: NormalizationSettings, measure_only: bool = False) -> str:
    """The libavfilter chain, ordered so cleanup happens before loudness is measured."""
    stages = []
    if settings.highpass_hz:
        stages.append(f"highpass=f={settings.highpass_hz}")
    if settings.denoise:
        stages.append("afftdn=nf=-25")

    loudnorm = (
        f"loudnorm=I={settings.target_lufs}:TP={settings.true_peak}:LRA={settings.loudness_range}"
    )
    if measure_only:
        loudnorm += ":print_format=json"
    stages.append(loudnorm)

    stages.append(f"aresample={TARGET_SAMPLE_RATE}")
    stages.append(f"aformat=sample_fmts=s16:channel_layouts=mono:sample_rates={TARGET_SAMPLE_RATE}")
    return ",".join(stages)


def _open_source(source: Path) -> tuple[Any, Any]:
    av = _av()

    if not source.exists():
        raise NormalizationError(f"{source} does not exist")

    try:
        container = av.open(str(source))
    except Exception as error:
        raise NormalizationError(f"Could not open {source.name}: {error}") from error

    if not container.streams.audio:
        container.close()
        raise NormalizationError(f"{source.name} contains no audio stream")
    return container, container.streams.audio[0]


def _build_graph(stream: Any, description: str) -> Any:
    _av()
    from av.filter import Graph

    graph = Graph()
    nodes = [graph.add_abuffer(template=stream)]
    for stage in description.split(","):
        name, _, args = stage.partition("=")
        nodes.append(graph.add(name, args or None))
    nodes.append(graph.add("abuffersink"))
    for first, second in zip(nodes, nodes[1:], strict=False):
        first.link_to(second)
    graph.configure()
    return graph


def measure_dbfs(source: Path) -> float | None:
    """
    Root-mean-square level of `source` in dBFS.

    Not LUFS: PyAV exposes no way to read filter metadata, so the figure ffmpeg's own
    loudnorm computes internally cannot be read back out. This is a real, comparable
    measurement of the same thing in a simpler unit - see docs/audio-normalization.md.
    """
    import numpy as np

    try:
        container, stream = _open_source(source)
    except NormalizationError:
        raise

    total = 0.0
    count = 0
    try:
        for frame in container.decode(stream):
            samples = frame.to_ndarray().astype(np.float64)
            if samples.size == 0:
                continue
            if np.issubdtype(frame.to_ndarray().dtype, np.integer):
                samples = samples / 32768.0
            total += float(np.sum(samples**2))
            count += samples.size
    except Exception:
        logger.debug("Could not measure %s", source.name, exc_info=True)
        return None
    finally:
        container.close()

    if not count:
        return None
    mean_square = total / count
    if mean_square <= 0:
        return SILENCE_DBFS
    return round(20 * math.log10(math.sqrt(mean_square)), 2)


def normalize_audio(
    source: Path,
    settings: NormalizationSettings | None = None,
    output_path: Path | None = None,
) -> NormalizationResult:
    """Writes a levelled copy of `source`, leaving the original untouched."""
    av = _av()

    settings = settings or NormalizationSettings()
    destination = output_path or normalized_path_for(source)
    before = measure_dbfs(source)

    container, stream = _open_source(source)
    try:
        output = av.open(str(destination), mode="w")
    except Exception as error:
        container.close()
        raise NormalizationError(f"Could not write {destination.name}: {error}") from error

    try:
        out_stream = output.add_stream("pcm_s16le", rate=TARGET_SAMPLE_RATE, layout="mono")
        graph = _build_graph(stream, build_filter_description(settings))

        def drain() -> None:
            while True:
                try:
                    frame = graph.pull()
                except (av.error.BlockingIOError, av.error.EOFError):
                    return
                frame.pts = None
                for packet in out_stream.encode(frame):
                    output.mux(packet)

        for frame in container.decode(stream):
            graph.push(frame)
            drain()

        graph.push(None)
        drain()

        for packet in out_stream.encode(None):
            output.mux(packet)
    except Exception as error:
        raise NormalizationError(f"Could not normalize {source.name}: {error}") from error
    finally:
        output.close()
        container.close()

    after = measure_dbfs(destination)
    logger.info(
        f"Normalized {source.name}: {_format_dbfs(before)} -> {_format_dbfs(after)} "
        f"(target {settings.target_lufs} LUFS)"
    )
    return NormalizationResult(
        output_path=destination, loudness_before=before, loudness_after=after
    )


def _format_dbfs(value: float | None) -> str:
    return f"{value:.1f} dBFS" if value is not None else "unknown"
