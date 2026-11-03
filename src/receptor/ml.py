"""Fine-tuning e reconhecimento local com Whisper; dependências ML opcionais."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
from types import SimpleNamespace
from typing import Any
import wave

from receptor.config import load_config
from receptor.data import Sample, load_manifest, validate_audio, validate_disjoint
from receptor.metrics import error_rates


def _load_runtime(*, training: bool = False) -> SimpleNamespace:
    # Set before importing HF: no analytics, remote experiment logging or model upload.
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    try:
        torch = importlib.import_module("torch")
        np = importlib.import_module("numpy")
        transformers = importlib.import_module("transformers")
        runtime = SimpleNamespace(
            torch=torch, np=np,
            processor_class=transformers.WhisperProcessor,
            model_class=transformers.WhisperForConditionalGeneration,
        )
        if training:
            importlib.import_module("accelerate")
            runtime.trainer_class = transformers.Seq2SeqTrainer
            runtime.arguments_class = transformers.Seq2SeqTrainingArguments
            runtime.set_seed = transformers.set_seed
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            'As dependências de IA estão ausentes ou incompatíveis. '
            'No ambiente virtual do projeto, execute: python -m pip install -e ".[ml]"'
        ) from exc
    return runtime


def _load_components(runtime: SimpleNamespace, model_name: str, language: str) -> tuple[Any, Any]:
    processor = runtime.processor_class.from_pretrained(model_name, language=language, task="transcribe")
    model = runtime.model_class.from_pretrained(model_name, use_safetensors=True)
    # language/task are the current Whisper generation API. Remove obsolete prompts.
    model.generation_config.language = language
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None
    model.config.forced_decoder_ids = None
    return processor, model


def _read_audio(path: Path, np: Any) -> Any:
    validate_audio(path)
    with wave.open(str(path), "rb") as handle:
        pcm = handle.readframes(handle.getnframes())
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def _validate_model_options(model_name: str, language: str) -> None:
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("Informe um nome de modelo ou diretório local.")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("Informe o idioma da fala.")


def _make_dataset(runtime: SimpleNamespace, samples: list[Sample], processor: Any, max_labels: int) -> Any:
    class SpeechDataset(runtime.torch.utils.data.Dataset):
        def __init__(self) -> None:
            # Do not truncate references silently. Check every text before optimizer steps.
            self.labels = [processor.tokenizer(sample.text).input_ids for sample in samples]
            if any(len(labels) - 1 > max_labels for labels in self.labels):
                raise ValueError("Uma transcrição excede o limite de tokens do modelo; divida o segmento.")

        def __len__(self) -> int:
            return len(samples)

        def __getitem__(self, index: int) -> dict[str, Any]:
            audio = _read_audio(samples[index].audio, runtime.np)
            features = processor.feature_extractor(audio, sampling_rate=16000, return_attention_mask=True)
            return {
                "input_features": features.input_features[0],
                "attention_mask": features.attention_mask[0],
                "labels": self.labels[index],
            }

    return SpeechDataset()


@dataclass
class WhisperCollator:
    processor: Any
    decoder_start_token_id: int
    torch: Any

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        batch = self.processor.feature_extractor.pad(
            [{"input_features": row["input_features"]} for row in features], return_tensors="pt"
        )
        batch["attention_mask"] = self.torch.stack([
            self.torch.as_tensor(row["attention_mask"]) for row in features
        ])
        label_batch = self.processor.tokenizer.pad(
            [{"input_ids": row["labels"]} for row in features], return_tensors="pt"
        )
        labels = label_batch["input_ids"].masked_fill(label_batch["attention_mask"].ne(1), -100)
        if labels.shape[1] > 0 and (labels[:, 0] == self.decoder_start_token_id).all().item():
            labels = labels[:, 1:]
        batch["labels"] = labels
        return batch


def _predict(path: Path, runtime: SimpleNamespace, processor: Any, model: Any) -> str:
    audio = _read_audio(path, runtime.np)
    inputs = processor.feature_extractor(
        audio, sampling_rate=16000, return_tensors="pt", return_attention_mask=True
    )
    inputs = {name: value.to(model.device) for name, value in inputs.items()}
    with runtime.torch.inference_mode():
        generated = model.generate(**inputs)
    return processor.batch_decode(generated, skip_special_tokens=True)[0].strip()


def _evaluate_samples(samples: list[Sample], runtime: SimpleNamespace, processor: Any, model: Any) -> dict[str, Any]:
    model.eval()
    references: list[str] = []
    hypotheses: list[str] = []
    speakers: dict[str, tuple[list[str], list[str]]] = defaultdict(lambda: ([], []))
    for sample in samples:
        hypothesis = _predict(sample.audio, runtime, processor, model)
        references.append(sample.text)
        hypotheses.append(hypothesis)
        speakers[sample.speaker_id][0].append(sample.text)
        speakers[sample.speaker_id][1].append(hypothesis)
    return {
        "samples": len(samples),
        "speakers": len(speakers),
        **error_rates(references, hypotheses),
        "by_speaker": {
            speaker: {"samples": len(refs), **error_rates(refs, hyps)}
            for speaker, (refs, hyps) in sorted(speakers.items())
        },
    }


def transcribe(audio_path: Path, model_name: str = "openai/whisper-tiny", language: str = "portuguese") -> str:
    """Transcreve um WAV de até 30 s. A saída precisa de confirmação humana."""
    audio_path = Path(audio_path)
    validate_audio(audio_path)
    _validate_model_options(model_name, language)
    runtime = _load_runtime()
    processor, model = _load_components(runtime, model_name, language)
    model.to("cuda" if runtime.torch.cuda.is_available() else "cpu")
    model.eval()
    return _predict(audio_path, runtime, processor, model)


def evaluate(manifest_path: Path, model_name: str, language: str = "portuguese") -> dict[str, Any]:
    """WER/CER do conjunto inteiro e por participante; não persiste transcrições."""
    samples = load_manifest(Path(manifest_path))
    _validate_model_options(model_name, language)
    runtime = _load_runtime()
    processor, model = _load_components(runtime, model_name, language)
    model.to("cuda" if runtime.torch.cuda.is_available() else "cpu")
    return {
        "model_name": model_name,
        "language": language,
        "metrics_policy": "WER/CER em frações, ponderados pelos totais de palavras/caracteres da referência; normalização em receptor.metrics",
        **_evaluate_samples(samples, runtime, processor, model),
    }


def _write_json(path: Path, values: dict[str, Any]) -> None:
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")


def _versions() -> dict[str, str]:
    result = {"python": platform.python_version()}
    for name in ("torch", "transformers", "accelerate", "numpy", "safetensors"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "não instalado"
    return result


def train(config_path: Path) -> dict[str, Any]:
    """Ajusta Whisper e grava modelo, processador, métricas e proveniência localmente."""
    config = load_config(Path(config_path))
    train_samples = load_manifest(config.train_manifest)
    validation_samples = load_manifest(config.validation_manifest)
    validate_disjoint(train_samples, validation_samples)
    if config.output_dir.exists() and (not config.output_dir.is_dir() or any(config.output_dir.iterdir())):
        raise ValueError("output_dir deve ser uma pasta nova ou vazia; escolha outro nome para preservar os resultados.")

    runtime = _load_runtime(training=True)
    runtime.set_seed(config.seed)
    processor, model = _load_components(runtime, config.model_name, config.language)
    train_dataset = _make_dataset(runtime, train_samples, processor, model.config.max_target_positions)
    # Validate references in the validation set before spending time training.
    _make_dataset(runtime, validation_samples, processor, model.config.max_target_positions)
    arguments = runtime.arguments_class(
        output_dir=str(config.output_dir),
        per_device_train_batch_size=config.batch_size,
        per_device_eval_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        num_train_epochs=config.epochs,
        max_steps=config.max_steps if config.max_steps is not None else -1,
        seed=config.seed,
        data_seed=config.seed,
        eval_strategy="no",  # One complete evaluation after training, including speaker metrics.
        save_strategy="no",
        logging_strategy="no",
        report_to=[],
        push_to_hub=False,
        dataloader_num_workers=0,
        dataloader_pin_memory=runtime.torch.cuda.is_available(),
        remove_unused_columns=False,
        optim="adamw_torch",
        fp16=False,
        bf16=False,
        save_safetensors=True,
    )
    trainer = runtime.trainer_class(
        model=model, args=arguments, train_dataset=train_dataset,
        data_collator=WhisperCollator(processor, model.config.decoder_start_token_id, runtime.torch),
        processing_class=processor,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(config.output_dir / "run.json", {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "versions": _versions(),
        "model_revision": getattr(model.config, "_commit_hash", None),
        "manifest_sha256": {
            "train": hashlib.sha256(config.train_manifest.read_bytes()).hexdigest(),
            "validation": hashlib.sha256(config.validation_manifest.read_bytes()).hexdigest(),
        },
        "metrics_policy": "WER/CER em frações; normalização definida em receptor.metrics",
        "reproducibility": "Seed fixa; hardware e operações GPU podem causar variações numéricas.",
    })
    result = trainer.train()
    trainer.save_model(str(config.output_dir))
    processor.save_pretrained(str(config.output_dir))
    trainer.save_state()
    metrics = {
        "output_dir": str(config.output_dir),
        "train": result.metrics,
        "validation": _evaluate_samples(validation_samples, runtime, processor, trainer.model),
    }
    _write_json(config.output_dir / "metrics.json", metrics)
    return metrics
