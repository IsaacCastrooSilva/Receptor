import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from receptor.config import TrainConfig
from receptor.data import Sample
from receptor import ml


class MLPreflightTests(unittest.TestCase):
    def test_missing_dependencies_have_install_instruction(self):
        with patch.object(ml.importlib, "import_module", side_effect=ImportError("missing")):
            with self.assertRaisesRegex(RuntimeError, r'pip install -e ".\[ml\]"'):
                ml._load_runtime()

    def test_invalid_audio_rejected_before_loading_runtime(self):
        with patch.object(ml, "_load_runtime") as runtime:
            with self.assertRaises(ValueError):
                ml.transcribe(Path("does-not-exist.wav"))
        runtime.assert_not_called()

    def test_invalid_manifest_rejected_before_loading_runtime(self):
        with patch.object(ml, "_load_runtime") as runtime:
            with self.assertRaises(ValueError):
                ml.evaluate(Path("does-not-exist.jsonl"), "openai/whisper-tiny")
        runtime.assert_not_called()

    def test_leakage_rejected_before_loading_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = TrainConfig(folder / "train.jsonl", folder / "val.jsonl", folder / "output")
            with patch.object(ml, "load_config", return_value=config), \
                 patch.object(ml, "load_manifest", return_value=[]), \
                 patch.object(ml, "validate_disjoint", side_effect=ValueError("vazamento")), \
                 patch.object(ml, "_load_runtime") as runtime:
                with self.assertRaisesRegex(ValueError, "vazamento"):
                    ml.train(folder / "config.toml")
            runtime.assert_not_called()

    def test_existing_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            output = folder / "output"
            output.mkdir()
            existing = output / "previous-model.txt"
            existing.write_text("preservar", encoding="utf-8")
            config = TrainConfig(folder / "train.jsonl", folder / "val.jsonl", output)
            with patch.object(ml, "load_config", return_value=config), \
                 patch.object(ml, "load_manifest", return_value=[]), \
                 patch.object(ml, "validate_disjoint"), \
                 patch.object(ml, "_load_runtime") as runtime:
                with self.assertRaisesRegex(ValueError, "nova ou vazia"):
                    ml.train(folder / "config.toml")
            runtime.assert_not_called()
            self.assertEqual(existing.read_text(encoding="utf-8"), "preservar")

    def test_evaluation_aggregates_errors_and_reports_per_speaker_without_texts(self):
        samples = [
            Sample(Path("a.wav"), "quero tomar água", "p001"),
            Sample(Path("b.wav"), "muito obrigado", "p002"),
        ]
        with patch.object(ml, "_predict", side_effect=["quero água", "muito obrigado"]):
            metrics = ml._evaluate_samples(samples, SimpleNamespace(), Mock(), Mock())
        self.assertAlmostEqual(metrics["wer"], 1 / 5)
        self.assertAlmostEqual(metrics["by_speaker"]["p001"]["wer"], 1 / 3)
        self.assertEqual(metrics["by_speaker"]["p002"]["wer"], 0)
        self.assertEqual(metrics["samples"], 2)
        self.assertEqual(metrics["speakers"], 2)
        self.assertNotIn("quero", json.dumps(metrics))
        self.assertNotIn("obrigado", json.dumps(metrics))

    def test_generation_uses_language_task_and_clears_legacy_prompt(self):
        processor = Mock()
        model = SimpleNamespace(generation_config=SimpleNamespace(), config=SimpleNamespace())
        runtime = SimpleNamespace(processor_class=Mock(), model_class=Mock())
        runtime.processor_class.from_pretrained.return_value = processor
        runtime.model_class.from_pretrained.return_value = model
        actual_processor, actual_model = ml._load_components(runtime, "local-model", "portuguese")
        self.assertIs(actual_processor, processor)
        self.assertIs(actual_model, model)
        self.assertEqual(model.generation_config.language, "portuguese")
        self.assertEqual(model.generation_config.task, "transcribe")
        self.assertIsNone(model.generation_config.forced_decoder_ids)
        self.assertIsNone(model.config.forced_decoder_ids)


if __name__ == "__main__":
    unittest.main()
