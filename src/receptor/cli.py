"""Comandos do projeto; dependências de IA só são importadas quando necessárias."""

import argparse
import json
from pathlib import Path
import sys

from receptor import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Receptor — apoio local à comunicação")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    app = commands.add_parser("app", help="Abrir janela de texto, frases e transcrição")
    app.add_argument("--model", default="openai/whisper-tiny")
    app.add_argument("--language", default="portuguese")
    speak = commands.add_parser("speak", help="Ler um texto com uma voz instalada no Windows")
    speak.add_argument("text")
    demo = commands.add_parser("demo", help="Gerar tons artificiais para testar o fluxo de dados")
    demo.add_argument("--output-dir", type=Path, default=Path("data/demo"))
    validate = commands.add_parser("validate", help="Validar manifesto e gravações")
    validate.add_argument("manifest", type=Path)
    split = commands.add_parser("split", help="Separar dados por participante")
    split.add_argument("manifest", type=Path)
    split.add_argument("--output-dir", type=Path, default=Path("data/splits"))
    split.add_argument("--seed", type=int, default=42)
    train = commands.add_parser("train", help="Adaptar Whisper usando gravações autorizadas")
    train.add_argument("--config", type=Path, default=Path("configs/train.toml"))
    transcribe = commands.add_parser("transcribe", help="Transcrever um WAV de até 30 segundos")
    transcribe.add_argument("audio", type=Path)
    transcribe.add_argument("--model", default="openai/whisper-tiny")
    transcribe.add_argument("--language", default="portuguese")
    evaluate = commands.add_parser("evaluate", help="Medir erros no conjunto reservado")
    evaluate.add_argument("manifest", type=Path)
    evaluate.add_argument("--model", default="openai/whisper-tiny")
    evaluate.add_argument("--language", default="portuguese")
    evaluate.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "app":
            from receptor.app import run
            run(model_name=args.model, language=args.language)
            return 0
        if args.command == "speak":
            from receptor.speech import speak_text
            speak_text(args.text)
            return 0
        if args.command == "demo":
            from receptor.demo import create_demo
            result = {
                "manifest": str(create_demo(args.output_dir)),
                "aviso": "Tons artificiais: não usar para medir qualidade de reconhecimento de fala.",
            }
        elif args.command == "validate":
            from receptor.data import load_manifest, summary
            result = summary(load_manifest(args.manifest))
        elif args.command == "split":
            from receptor.data import split_manifest
            result = {
                key: str(value)
                for key, value in split_manifest(args.manifest, args.output_dir, seed=args.seed).items()
            }
        elif args.command == "train":
            from receptor.ml import train
            result = train(args.config)
        elif args.command == "transcribe":
            from receptor.ml import transcribe
            print(transcribe(args.audio, args.model, args.language))
            return 0
        else:
            from receptor.ml import evaluate
            if args.output is not None and args.output.exists():
                raise ValueError("O relatório já existe; escolha outro caminho de saída.")
            result = evaluate(args.manifest, args.model, args.language)
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operação interrompida.", file=sys.stderr)
        return 130
