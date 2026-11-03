import builtins
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from receptor.cli import main
from receptor.data import load_manifest, validate_disjoint
from receptor.demo import create_demo


@contextmanager
def without_model_imports():
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "receptor.ml" or name.split(".")[0] in {
            "torch", "transformers", "numpy", "accelerate",
        }:
            raise AssertionError("Um comando do núcleo tentou importar dependências de IA.")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded_import):
        yield


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def invoke(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_demo_validate_split_end_to_end_without_model_imports(self):
        with without_model_imports():
            manifest = create_demo(self.root / "demo")
            code, stdout, stderr = self.invoke("validate", str(manifest))
            self.assertEqual(code, 0, stderr)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout),
                {"samples": 9, "speakers": 3, "duration_seconds": 9.0},
            )

            code, stdout, stderr = self.invoke(
                "split", str(manifest), "--output-dir", str(self.root / "splits"),
                "--seed", "17",
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(stderr, "")
            paths = json.loads(stdout)
            self.assertEqual(set(paths), {"train", "validation", "test"})
            groups = [load_manifest(Path(path)) for path in paths.values()]
            self.assertEqual([len(group) for group in groups], [3, 3, 3])
            validate_disjoint(*groups)
            self.assertEqual(sum(map(len, groups)), len(load_manifest(manifest)))

    def test_demo_command_outputs_json_and_rejects_overwrite(self):
        output_dir = self.root / "demo"
        with without_model_imports():
            code, stdout, stderr = self.invoke("demo", "--output-dir", str(output_dir))
            self.assertEqual(code, 0, stderr)
            result = json.loads(stdout)
            self.assertIn("Tons artificiais", result["aviso"])
            manifest = Path(result["manifest"])
            original = {path: path.read_bytes() for path in output_dir.rglob("*") if path.is_file()}
            self.assertEqual(len(load_manifest(manifest)), 9)
            code, stdout, stderr = self.invoke("demo", "--output-dir", str(output_dir))
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("vazia", stderr)
            self.assertEqual(original, {path: path.read_bytes() for path in original})

    def test_invalid_manifest_returns_code_one_without_exposing_input(self):
        private_marker = "TRANSCRICAO_PRIVADA"
        with without_model_imports():
            code, stdout, stderr = self.invoke(
                "validate", str(self.root / f"{private_marker}.jsonl"),
            )
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Erro:", stderr)
        self.assertNotIn(private_marker, stderr)
        self.assertNotIn("Traceback", stderr)

    def test_invalid_record_does_not_print_transcription(self):
        manifest = self.root / "invalid.jsonl"
        manifest.write_text(json.dumps({
            "audio": "missing.wav",
            "text": "TRANSCRIÇÃO PRIVADA",
            "speaker_id": "PARTICIPANTE_PRIVADO",
            "consent": False,
        }), encoding="utf-8")
        with without_model_imports():
            code, stdout, stderr = self.invoke("validate", str(manifest))
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertNotIn("TRANSCRIÇÃO PRIVADA", stderr)
        self.assertNotIn("PARTICIPANTE_PRIVADO", stderr)

    def test_existing_evaluation_report_is_preserved_before_evaluation(self):
        report = self.root / "report.json"
        report.write_text('{"existing": true}\n', encoding="utf-8")
        original = report.read_bytes()
        with patch("receptor.ml.evaluate") as evaluate:
            code, stdout, stderr = self.invoke(
                "evaluate", str(self.root / "test.jsonl"), "--output", str(report),
            )
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("já existe", stderr)
        evaluate.assert_not_called()
        self.assertEqual(report.read_bytes(), original)

    def test_evaluation_writes_and_prints_the_same_json_report(self):
        manifest = self.root / "test.jsonl"
        report = self.root / "reports" / "report.json"
        result = {"wer": 0.25, "cer": 0.1, "samples": 3}
        with patch("receptor.ml.evaluate", return_value=result) as evaluate:
            code, stdout, stderr = self.invoke(
                "evaluate", str(manifest), "--model", "local-model",
                "--language", "portuguese", "--output", str(report),
            )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        evaluate.assert_called_once_with(manifest, "local-model", "portuguese")
        self.assertEqual(json.loads(stdout), result)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")), result)


if __name__ == "__main__":
    unittest.main()
