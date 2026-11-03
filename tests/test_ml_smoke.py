"""Teste opcional: um passo real de treinamento, sem baixar pesos ou usar fala real."""

import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave


ML_AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("torch", "numpy", "transformers", "accelerate"))


@unittest.skipUnless(ML_AVAILABLE, 'Instale o extra ".[ml]" para o smoke test de treinamento.')
class OfflineTrainingSmokeTests(unittest.TestCase):
    def test_real_training_save_reload_transcribe_and_evaluate_offline(self):
        with patch.dict(os.environ, {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}):
            self._run_smoke()

    def _run_smoke(self):
        import torch
        from transformers import WhisperConfig, WhisperFeatureExtractor, WhisperForConditionalGeneration, WhisperProcessor, WhisperTokenizer
        from transformers.models.whisper.tokenization_whisper import LANGUAGES, bytes_to_unicode
        from receptor.ml import WhisperCollator, evaluate, train, transcribe

        previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        self.addCleanup(torch.set_num_threads, previous_threads)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original"
            original.mkdir()
            vocab = {token: index for index, token in enumerate(bytes_to_unicode().values())}
            special = ["<|endoftext|>", "<|startoftranscript|>"]
            special += [f"<|{language}|>" for language in LANGUAGES]
            special += ["<|translate|>", "<|transcribe|>", "<|notimestamps|>"]
            for token in special:
                vocab[token] = len(vocab)
            (original / "vocab.json").write_text(json.dumps(vocab), encoding="utf-8")
            (original / "merges.txt").write_text("#version: 0.2\n", encoding="utf-8")
            tokenizer = WhisperTokenizer(
                str(original / "vocab.json"), str(original / "merges.txt"),
                language="portuguese", task="transcribe", additional_special_tokens=special,
                pad_token="<|endoftext|>",
            )
            extractor = WhisperFeatureExtractor(feature_size=80, sampling_rate=16000, chunk_length=1)
            processor = WhisperProcessor(extractor, tokenizer)
            config = WhisperConfig(
                vocab_size=len(tokenizer), num_mel_bins=80, d_model=16,
                encoder_layers=1, decoder_layers=1,
                encoder_attention_heads=2, decoder_attention_heads=2,
                encoder_ffn_dim=32, decoder_ffn_dim=32,
                max_source_positions=50, max_target_positions=32,
                decoder_start_token_id=vocab["<|startoftranscript|>"],
                pad_token_id=vocab["<|endoftext|>"],
                bos_token_id=vocab["<|endoftext|>"],
                eos_token_id=vocab["<|endoftext|>"],
                suppress_tokens=None, begin_suppress_tokens=None,
            )
            model = WhisperForConditionalGeneration(config)
            # This is a complete Whisper generation config, including language/task maps.
            # Keep those extra fields when Transformers saves and reloads it.
            model.generation_config._from_model_config = False
            model.generation_config.is_multilingual = True
            model.generation_config.suppress_tokens = None
            model.generation_config.begin_suppress_tokens = None
            model.generation_config.lang_to_id = {f"<|{language}|>": vocab[f"<|{language}|>"] for language in LANGUAGES}
            model.generation_config.task_to_id = {task: vocab[f"<|{task}|>"] for task in ("transcribe", "translate")}
            model.generation_config.no_timestamps_token_id = vocab["<|notimestamps|>"]
            model.generation_config.max_length = 12
            model.save_pretrained(original, safe_serialization=True)
            processor.save_pretrained(original)
            previous_weights = model.model.decoder.embed_tokens.weight.detach().clone()

            # Test real padding: only padding is masked; an EOS identical to PAD remains a target.
            feature = extractor([0.0] * 1600, sampling_rate=16000, return_attention_mask=True)
            collated = WhisperCollator(processor, config.decoder_start_token_id, torch)([
                {"input_features": feature.input_features[0], "attention_mask": feature.attention_mask[0], "labels": tokenizer("oi").input_ids},
                {"input_features": feature.input_features[0], "attention_mask": feature.attention_mask[0], "labels": tokenizer("o").input_ids},
            ])
            self.assertNotEqual(collated["labels"][0, 0].item(), config.decoder_start_token_id)
            self.assertEqual(collated["labels"][1, -1].item(), -100)
            self.assertEqual(collated["labels"][1, -2].item(), tokenizer.eos_token_id)
            self.assertEqual(tuple(collated["attention_mask"].shape), (2, 100))

            for split, frequency in (("train", 220), ("validation", 330)):
                audio = root / f"{split}.wav"
                with wave.open(str(audio), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(16000)
                    handle.writeframes(b"".join(struct.pack("<h", int(1000 * math.sin(2 * math.pi * frequency * index / 16000))) for index in range(1600)))
                entry = {"audio": audio.name, "text": "oi", "speaker_id": split, "consent": True}
                (root / f"{split}.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
            config_path = root / "train.toml"
            config_path.write_text(
                'train_manifest = "train.jsonl"\nvalidation_manifest = "validation.jsonl"\n'
                'output_dir = "result"\nmodel_name = "./original"\nbatch_size = 1\n'
                'gradient_accumulation_steps = 1\nmax_steps = 1\n', encoding="utf-8",
            )
            metrics = train(config_path)
            result = root / "result"
            self.assertTrue(math.isfinite(metrics["train"]["train_loss"]))
            self.assertEqual(metrics["validation"]["samples"], 1)
            self.assertTrue((result / "run.json").is_file())
            self.assertTrue((result / "metrics.json").is_file())
            trained = WhisperForConditionalGeneration.from_pretrained(result, local_files_only=True)
            self.assertFalse(torch.equal(previous_weights, trained.model.decoder.embed_tokens.weight))
            self.assertIsInstance(transcribe(root / "validation.wav", str(result)), str)
            self.assertIn("wer", evaluate(root / "validation.jsonl", str(result)))


if __name__ == "__main__":
    unittest.main()
