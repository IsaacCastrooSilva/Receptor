"""Configuração TOML validada sem carregar bibliotecas de IA."""

from __future__ import annotations

from dataclasses import dataclass, fields
import math
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class TrainConfig:
    train_manifest: Path
    validation_manifest: Path
    output_dir: Path
    model_name: str = "openai/whisper-tiny"
    language: str = "portuguese"
    epochs: float = 3.0
    learning_rate: float = 0.00001
    batch_size: int = 2
    gradient_accumulation_steps: int = 4
    seed: int = 42
    max_steps: int | None = None


def load_config(path: Path) -> TrainConfig:
    """Carrega campos no nível principal; caminhos são relativos ao TOML."""
    path = Path(path).resolve()
    try:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("Não foi possível ler uma configuração TOML válida.") from exc

    allowed = {field.name for field in fields(TrainConfig)}
    if set(values) - allowed:
        raise ValueError("Configuração contém campos desconhecidos: " + ", ".join(sorted(set(values) - allowed)))
    for name in ("train_manifest", "validation_manifest", "output_dir"):
        value = values.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"O campo {name} deve ser um caminho não vazio.")
        candidate = Path(value).expanduser()
        values[name] = (path.parent / candidate).resolve()

    for name in ("model_name", "language"):
        if name in values and (not isinstance(values[name], str) or not values[name].strip()):
            raise ValueError(f"O campo {name} deve ser uma string não vazia.")
        if name in values:
            values[name] = values[name].strip()
    # Nomes do Hub permanecem identificadores. Pastas locais explícitas são relativas ao TOML.
    model_name = values.get("model_name", "openai/whisper-tiny")
    if model_name.startswith(("./", "../", ".\\", "..\\")) or Path(model_name).is_absolute():
        values["model_name"] = str((path.parent / Path(model_name)).resolve())

    for name in ("epochs", "learning_rate"):
        if name in values:
            value = values[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"O campo {name} deve ser um número positivo e finito.")
    for name in ("batch_size", "gradient_accumulation_steps", "max_steps"):
        if name in values and (type(values[name]) is not int or values[name] < 1):
            raise ValueError(f"O campo {name} deve ser um inteiro positivo.")
    if "seed" in values and (type(values["seed"]) is not int or not 0 <= values["seed"] < 2**32):
        raise ValueError("O campo seed deve ser um inteiro entre 0 e 4294967295.")
    return TrainConfig(**values)
