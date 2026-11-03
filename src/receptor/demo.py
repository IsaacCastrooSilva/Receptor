"""Gera apenas tons artificiais para testar o fluxo de arquivos."""

from array import array
import json
import math
from pathlib import Path
import sys
import wave


def create_demo(output_dir: Path) -> Path:
    """Cria 9 WAVs distintos; não representam fala nem desempenho do modelo."""
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("A pasta de demonstração precisa estar vazia.")
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir()
    records = []
    for i in range(9):
        name = f"tom_{i + 1:02d}.wav"
        samples = array("h", (
            int(3000 * math.sin(2 * math.pi * (220 + i * 37) * frame / 16000))
            for frame in range(16000)
        ))
        if sys.byteorder != "little":
            samples.byteswap()
        with wave.open(str(audio_dir / name), "wb") as handle:
            handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            handle.writeframes(samples.tobytes())
        records.append({
            "audio": f"audio/{name}",
            "text": "Tom artificial, sem fala humana.",
            "speaker_id": f"sintetico_{i // 3 + 1:02d}",
            "consent": True,
        })
    manifest = output_dir / "manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    return manifest
