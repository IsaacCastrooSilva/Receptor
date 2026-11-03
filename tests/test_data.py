import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from receptor.data import Sample, load_manifest, split_manifest, summary, validate_audio, validate_disjoint


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def audio(self, name="audio.wav", *, value=1, channels=1, width=2, rate=16000, frames=160):
        path = self.root / name
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(channels)
            audio.setsampwidth(width)
            audio.setframerate(rate)
            frame = struct.pack("<h", value) if width == 2 else bytes([value]) * width
            audio.writeframes(frame * frames * channels)
        return path

    def manifest(self, rows, name="data.jsonl"):
        path = self.root / name
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        return path

    def row(self, audio="audio.wav", speaker="participant-01", text="Preciso de água.", consent=True):
        return {"audio": audio, "text": text, "speaker_id": speaker, "consent": consent}

    def test_loads_relative_audio_and_preserves_accents(self):
        audio = self.audio()
        samples = load_manifest(self.manifest([self.row()]))
        self.assertEqual(samples, [Sample(audio.resolve(), "Preciso de água.", "participant-01")])
        self.assertEqual(summary(samples), {"samples": 1, "speakers": 1, "duration_seconds": 0.01})

    def test_requires_literal_boolean_consent(self):
        self.audio()
        for consent in (False, None, "true", 1, 0, [], {}):
            with self.subTest(consent=consent), self.assertRaises(ValueError):
                load_manifest(self.manifest([self.row(consent=consent)]))
        row = self.row()
        del row["consent"]
        with self.assertRaises(ValueError):
            load_manifest(self.manifest([row]))

    def test_rejects_blank_or_invalid_fields_without_exposing_transcription(self):
        self.audio()
        for field in ("audio", "text", "speaker_id"):
            for value in ("", " \t", None, 123):
                row = self.row(text="TRANSCRIÇÃO PRIVADA")
                row[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError) as caught:
                    load_manifest(self.manifest([row]))
                self.assertNotIn("TRANSCRIÇÃO PRIVADA", str(caught.exception))

    def test_rejects_missing_audio_and_empty_manifest(self):
        with self.assertRaises(ValueError):
            load_manifest(self.manifest([self.row()]))
        with self.assertRaises(ValueError):
            load_manifest(self.manifest([]))

    def test_rejects_malformed_json_and_duplicate_fields(self):
        path = self.root / "data.jsonl"
        for content in ('{"text": "TRANSCRIÇÃO PRIVADA",', '{"consent": false, "consent": true}', "[]"):
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(ValueError) as caught:
                load_manifest(path)
            self.assertNotIn("TRANSCRIÇÃO PRIVADA", str(caught.exception))

    def test_rejects_duplicate_pcm_even_under_another_path(self):
        first = self.audio()
        other = self.root / "copy.wav"
        altered_container = bytearray(first.read_bytes())
        altered_container.extend(b"JUNK" + struct.pack("<I", 4) + b"meta")
        struct.pack_into("<I", altered_container, 4, len(altered_container) - 8)
        other.write_bytes(altered_container)
        with self.assertRaisesRegex(ValueError, "duplicada"):
            load_manifest(self.manifest([self.row(), self.row("copy.wav", speaker="participant-02")]))

    def test_audio_format_and_duration_validation(self):
        cases = (
            {"channels": 2}, {"width": 1}, {"rate": 8000},
            {"frames": 0}, {"frames": 480001},
        )
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_audio(self.audio(**settings))
        metadata = validate_audio(self.audio(frames=480000))
        self.assertEqual(metadata["duration_seconds"], 30.0)
        self.assertEqual(metadata["sample_rate"], 16000)
        self.assertEqual(metadata["frames"], 480000)
        self.assertEqual(len(metadata["sha256"]), 64)

    def test_rejects_truncated_or_nonwav_audio(self):
        path = self.audio()
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaises(ValueError):
            validate_audio(path)
        path.write_bytes(b"not a wav file")
        with self.assertRaises(ValueError):
            validate_audio(path)

    def test_rejects_partial_pcm_frame_in_data_chunk(self):
        path = self.audio()
        content = bytearray(path.read_bytes())
        content.append(0)
        struct.pack_into("<I", content, 4, len(content) - 8)
        struct.pack_into("<I", content, 40, len(content) - 44)
        path.write_bytes(content)
        with self.assertRaises(ValueError):
            validate_audio(path)

    def test_disjoint_checks_participants_and_copied_audio(self):
        first = Sample(self.audio("a.wav", value=1), "a", "a")
        same_speaker = Sample(self.audio("b.wav", value=2), "b", "a")
        with self.assertRaisesRegex(ValueError, "participantes"):
            validate_disjoint([first], [same_speaker])
        copied_audio = Sample(self.audio("c.wav", value=1), "c", "b")
        with self.assertRaisesRegex(ValueError, "gravações"):
            validate_disjoint([first], [copied_audio])
        independent = Sample(self.audio("d.wav", value=3), "d", "b")
        validate_disjoint([first, same_speaker], [independent])

    def dataset(self, speakers=6):
        rows = []
        for speaker in range(speakers):
            for recording in range(2):
                index = speaker * 2 + recording
                name = f"recording-{index}.wav"
                self.audio(name, value=index + 1)
                rows.append(self.row(name, speaker=f"participant-{speaker}"))
        return self.manifest(rows)

    def test_split_is_reproducible_disjoint_and_uses_relative_paths(self):
        manifest = self.dataset()
        first = split_manifest(manifest, self.root / "first", seed=17)
        second = split_manifest(manifest, self.root / "second", seed=17)
        self.assertEqual(set(first), {"train", "validation", "test"})
        groups = [load_manifest(path) for path in first.values()]
        self.assertEqual(sum(map(len, groups)), 12)
        self.assertTrue(all(groups))
        validate_disjoint(*groups)
        for name in first:
            self.assertEqual(first[name].read_text(encoding="utf-8"), second[name].read_text(encoding="utf-8"))
            for line in first[name].read_text(encoding="utf-8").splitlines():
                self.assertFalse(Path(json.loads(line)["audio"]).is_absolute())

    def test_split_requires_three_speakers_and_never_overwrites(self):
        manifest = self.dataset(speakers=2)
        with self.assertRaises(ValueError):
            split_manifest(manifest, self.root / "split")
        manifest = self.dataset(speakers=3)
        paths = split_manifest(manifest, self.root / "split")
        before = {name: path.read_bytes() for name, path in paths.items()}
        with self.assertRaises(FileExistsError):
            split_manifest(manifest, self.root / "split")
        self.assertEqual(before, {name: path.read_bytes() for name, path in paths.items()})

    def test_split_fraction_validation_and_small_datasets(self):
        manifest = self.dataset(speakers=3)
        for validation, test in ((0, .2), (-1, .2), (.6, .4), (float("nan"), .2), (True, .2)):
            with self.subTest(validation=validation, test=test), self.assertRaises(ValueError):
                split_manifest(manifest, self.root / "invalid", validation_fraction=validation, test_fraction=test)
        paths = split_manifest(manifest, self.root / "valid", validation_fraction=.001, test_fraction=.99)
        self.assertTrue(all(load_manifest(path) for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
