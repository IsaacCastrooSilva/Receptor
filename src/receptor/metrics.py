"""WER/CER agregados com normalização explícita e sem bibliotecas externas."""

from __future__ import annotations

from collections.abc import Sequence
import unicodedata


def normalize_text(text: str) -> str:
    """Normaliza Unicode NFC, minúsculas, pontuação e espaços; preserva acentos.

    Pontuação Unicode vira espaço. Espaços repetidos são reduzidos a um, sem
    espaços nas extremidades. Números e símbolos não são removidos.
    """
    if not isinstance(text, str):
        raise ValueError("Referências e hipóteses devem conter somente strings.")
    normalized = unicodedata.normalize("NFC", text).lower()
    return " ".join(
        "".join(" " if unicodedata.category(char).startswith("P") else char for char in normalized).split()
    )


def _edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    # Keep only one DP row; memory is bounded by the shorter sequence.
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, reference_item in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (reference_item != hypothesis_item),
                )
            )
        previous = current
    return previous[-1]


def error_rates(references: list[str], hypotheses: list[str]) -> dict[str, float]:
    """Calcula WER e CER como frações agregadas, que podem ultrapassar 1.

    Cada taxa é soma das distâncias / soma dos tamanhos das referências;
    CER inclui os espaços normalizados. Se o denominador agregado for zero,
    usa 1: silêncio correto produz 0 e inserções continuam penalizadas.
    Listas vazias ou de tamanhos diferentes são inválidas. A normalização
    utilizada é a descrita em normalize_text.
    """
    if isinstance(references, str) or isinstance(hypotheses, str):
        raise ValueError("Forneça listas de referências e hipóteses.")
    if len(references) != len(hypotheses):
        raise ValueError("Referências e hipóteses devem ter o mesmo tamanho.")
    if not references:
        raise ValueError("É necessário ao menos um par de referência e hipótese.")
    word_errors = character_errors = reference_words = reference_characters = 0
    for reference, hypothesis in zip(references, hypotheses, strict=True):
        reference = normalize_text(reference)
        hypothesis = normalize_text(hypothesis)
        words = reference.split()
        word_errors += _edit_distance(words, hypothesis.split())
        character_errors += _edit_distance(reference, hypothesis)
        reference_words += len(words)
        reference_characters += len(reference)
    return {
        "wer": word_errors / max(reference_words, 1),
        "cer": character_errors / max(reference_characters, 1),
    }
