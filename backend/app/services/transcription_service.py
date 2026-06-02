from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings
from app.schemas.interview import TranscriptSegment


@dataclass
class TranscriptionResult:
    full_text: str
    segments: list[TranscriptSegment]
    language: str = "en"
    duration: float = 0.0


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> TranscriptionResult:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename

    response = await client.audio.transcriptions.create(
        model=settings.whisper_model,
        file=audio_file,
        response_format="verbose_json",
        timestamp_granularities=["segment"],
    )

    segments: list[TranscriptSegment] = []
    raw_segments = getattr(response, "segments", []) or []
    for seg in raw_segments:
        segments.append(
            TranscriptSegment(
                speaker="unknown",
                text=seg.get("text", "").strip(),
                start_time=seg.get("start", 0.0),
                end_time=seg.get("end", 0.0),
            )
        )

    duration = raw_segments[-1].get("end", 0.0) if raw_segments else 0.0

    return TranscriptionResult(
        full_text=response.text,
        segments=segments,
        language=getattr(response, "language", "en"),
        duration=duration,
    )


async def transcribe_file(file_path: Path) -> TranscriptionResult:
    audio_bytes = file_path.read_bytes()
    return await transcribe_audio(audio_bytes, file_path.name)


def apply_speaker_labels(
    segments: list[TranscriptSegment],
    speaker_map: dict[str, str] | None = None,
) -> list[TranscriptSegment]:
    """
    Heuristic speaker assignment: alternates speakers based on silence gaps.
    A real implementation would use Pyannote.audio diarization.
    """
    if not segments:
        return segments

    labeled = []
    current_speaker = "interviewer"
    prev_end = 0.0

    for seg in segments:
        gap = seg.start_time - prev_end
        if gap > 1.5 and labeled:  # speaker change on long pause
            current_speaker = "candidate" if current_speaker == "interviewer" else "interviewer"
        prev_end = seg.end_time
        labeled.append(
            TranscriptSegment(
                speaker=current_speaker,
                text=seg.text,
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
        )

    if speaker_map:
        return [
            TranscriptSegment(
                speaker=speaker_map.get(s.speaker, s.speaker),
                text=s.text,
                start_time=s.start_time,
                end_time=s.end_time,
            )
            for s in labeled
        ]
    return labeled
