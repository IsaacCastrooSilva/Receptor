"""Validação de dados e divisão por participante, sem dependências externas."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
from typing import Any
import wave


SAMPLE_RATE = 16_000
MAX_DURATION_SECONDS = 30


@dataclass(frozen=True)
class Sample:
    audio: Path
    text: str
    speaker_id: str


def _audio_info(path: Path) -> tuple[float, str]:
    """Retorna duração e hash PCM; metadados do contêiner não afetam o hash."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getcomptype() != "NONE"
                or audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != SAMPLE_RATE
            ):
                raise ValueError("O áudio deve ser WAV PCM de 16 bits, mono, a 16000 Hz.")
            frames = audio.getnframes()
            if not 0 < frames <= SAMPLE_RATE * MAX_DURATION_SECONDS:
                raise ValueError("A duração do áudio deve ser maior que zero e até 30 segundos.")
            # One additional requested frame also catches odd-sized data chunks.
            pcm = audio.readframes(frames + 1)
            if len(pcm) != frames * 2:
                raise ValueError("O áudio contém frames incompletos ou dados truncados.")
    except (OSError, EOFError, wave.Error):
        raise ValueError("Não foi possível ler um arquivo WAV válido.") from None
    return frames / SAMPLE_RATE, hashlib.sha256(pcm).hexdigest()


def validate_audio(path: Path) -> dict[str, int | float | str]:
    """Valida WAV PCM16 mono 16 kHz, 0 < duração <= 30 s; retorna metadados.

    O hash sha256 representa os frames PCM, sem os cabeçalhos WAV.
    """
    duration, digest = _audio_info(Path(path))
    return {
        "sample_rate": SAMPLE_RATE,
        "frames": round(duration * SAMPLE_RATE),
        "duration_seconds": duration,
        "sha256": digest,
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("O objeto JSON contém um campo repetido.")
        result[key] = value
    return result


def load_manifest(path: Path) -> list[Sample]:
    """Lê JSONL consentido, valida os áudios e rejeita gravações repetidas.

    Campos obrigatórios: audio, text, speaker_id e consent (booleano true).
    Caminhos relativos são resolvidos em relação ao manifesto. Campos extras
    são permitidos. Linhas em branco são ignoradas; um manifesto vazio falha.
    Mensagens de erro não incluem caminhos, identificadores nem transcrições.
    """
    manifest = Path(path)
    samples: list[Sample] = []
    seen_audio: set[str] = set()
    try:
        with manifest.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line, object_pairs_hook=_unique_object)
                    if not isinstance(row, dict):
                        raise ValueError("Cada linha deve conter um objeto JSON.")
                    if row.get("consent") is not True:
                        raise ValueError("É necessário consentimento explícito: consent deve ser true.")
                    for field in ("audio", "text", "speaker_id"):
                        if not isinstance(row.get(field), str) or not row[field].strip():
                            raise ValueError(f"O campo {field} deve ser uma string não vazia.")
                    audio_path = Path(row["audio"])
                    if not audio_path.is_absolute():
                        audio_path = manifest.parent / audio_path
                    try:
                        audio_path = audio_path.resolve(strict=True)
                    except (OSError, RuntimeError, ValueError):
                        raise ValueError("O arquivo de áudio não está acessível.") from None
                    _, digest = _audio_info(audio_path)
                    if digest in seen_audio:
                        raise ValueError("O manifesto contém uma gravação duplicada.")
                    seen_audio.add(digest)
                    samples.append(
                        Sample(audio_path, row["text"].strip(), row["speaker_id"].strip())
                    )
                except (ValueError, TypeError) as error:
                    # JSONDecodeError includes fragments of input in some contexts;
                    # expose only our bounded field/format messages.
                    detail = "JSON inválido." if isinstance(error, json.JSONDecodeError) else str(error)
                    raise ValueError(f"Linha {line_number}: {detail}") from None
    except (OSError, UnicodeError):
        raise ValueError("Não foi possível ler o manifesto em UTF-8.") from None
    if not samples:
        raise ValueError("O manifesto deve conter ao menos uma amostra.")
    return samples


def validate_disjoint(*groups: list[Sample]) -> None:
    """Rejeita participantes ou gravações compartilhados entre conjuntos."""
    previous_speakers: set[str] = set()
    previous_audio: set[str] = set()
    for group in groups:
        speakers = {sample.speaker_id for sample in group}
        if previous_speakers & speakers:
            raise ValueError("Há participantes compartilhados entre os conjuntos.")
        audio_hashes = {_audio_info(sample.audio)[1] for sample in group}
        if previous_audio & audio_hashes:
            raise ValueError("Há gravações compartilhadas entre os conjuntos.")
        previous_speakers.update(speakers)
        previous_audio.update(audio_hashes)


def split_manifest(
    manifest: Path,
    output_dir: Path,
    seed: int = 42,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> dict[str, Path]:
    """Separa participantes em treino, validação e teste de forma reproduzível.

    Frações referem-se a participantes, não a gravações. Usa arredondamento
    para baixo, garantindo ao menos um participante em cada conjunto. Exige
    três participantes e nunca sobrescreve os manifestos de saída existentes.
    """
    for fraction in (validation_fraction, test_fraction):
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float))
            or not math.isfinite(fraction)
            or not 0 < fraction < 1
        ):
            raise ValueError("As frações de validação e teste devem estar entre zero e um.")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("A soma das frações deve ser menor que um para preservar treino.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("A semente deve ser um número inteiro.")

    samples = load_manifest(Path(manifest))
    speakers = sorted({sample.speaker_id for sample in samples})
    if len(speakers) < 3:
        raise ValueError("São necessários ao menos três participantes para a divisão.")
    random.Random(seed).shuffle(speakers)
    count = len(speakers)
    validation_count = min(max(1, int(count * validation_fraction)), count - 2)
    test_count = min(max(1, int(count * test_fraction)), count - validation_count - 1)
    validation_speakers = set(speakers[:validation_count])
    test_speakers = set(speakers[validation_count : validation_count + test_count])
    train_speakers = set(speakers[validation_count + test_count :])
    assignments = {
        "train": train_speakers,
        "validation": validation_speakers,
        "test": test_speakers,
    }
    groups = {
        name: [sample for sample in samples if sample.speaker_id in participants]
        for name, participants in assignments.items()
    }
    validate_disjoint(*groups.values())

    output_dir = Path(output_dir).resolve()
    paths = {name: output_dir / f"{name}.jsonl" for name in groups}
    if any(path.exists() or path.is_symlink() for path in paths.values()):
        raise FileExistsError("Um manifesto de saída já existe; use outro diretório.")
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, path in paths.items():
            with path.open("x", encoding="utf-8", newline="\n") as target:
                created.append(path)
                for sample in groups[name]:
                    try:
                        audio_reference = os.path.relpath(sample.audio, start=output_dir)
                    except ValueError:
                        # Windows cannot express a relative path between drives.
                        audio_reference = str(sample.audio)
                    row = {
                        "audio": audio_reference,
                        "text": sample.text,
                        "speaker_id": sample.speaker_id,
                        "consent": True,
                    }
                    target.write(json.dumps(row, ensure_ascii=False) + "\n")
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return paths


def summary(samples: list[Sample]) -> dict[str, int | float]:
    """Resumo agregado sem transcrições, caminhos ou identificadores pessoais."""
    return {
        "samples": len(samples),
        "speakers": len({sample.speaker_id for sample in samples}),
        "duration_seconds": sum(_audio_info(sample.audio)[0] for sample in samples),
    }
