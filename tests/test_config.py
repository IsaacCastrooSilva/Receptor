import tempfile
from pathlib import Path
import unittest

from receptor.config import load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "train.toml"
        self.base = 'train_manifest = "train.jsonl"\nvalidation_manifest = "val.jsonl"\noutput_dir = "output"\n'

    def write(self, extra=""):
        self.path.write_text(self.base + extra, encoding="utf-8")
        return load_config(self.path)

    def test_paths_relative_to_config_and_defaults(self):
        config = self.write()
        self.assertEqual(config.train_manifest, self.folder / "train.jsonl")
        self.assertEqual(config.validation_manifest, self.folder / "val.jsonl")
        self.assertEqual(config.output_dir, self.folder / "output")
        self.assertEqual(config.model_name, "openai/whisper-tiny")
        self.assertEqual(config.language, "portuguese")
        self.assertIsNone(config.max_steps)

    def test_local_model_relative_to_config(self):
        self.assertEqual(self.write('model_name = "./model"\n').model_name, str(self.folder / "model"))

    def test_invalid_config_values(self):
        for extra in (
            "epochs = 0", "epochs = inf", "learning_rate = nan", "learning_rate = -1",
            "batch_size = true", "gradient_accumulation_steps = 1.5", "seed = -1",
            "seed = 4294967296", "max_steps = 0", "max_steps = false", "unknown = 1",
            'language = ""', 'model_name = " "', "model_name = 1",
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.write(extra + "\n")

    def test_required_paths(self):
        self.path.write_text('output_dir = "output"', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "train_manifest"):
            load_config(self.path)

    def test_bad_toml_explains_error(self):
        self.path.write_text("broken [", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "TOML"):
            load_config(self.path)


if __name__ == "__main__":
    unittest.main()
