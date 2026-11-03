import unittest

from receptor.metrics import error_rates, normalize_text


class MetricsTests(unittest.TestCase):
    def test_normalization_preserves_accents(self):
        self.assertEqual(normalize_text("  OLÁ,\n Água!  "), "olá água")
        self.assertEqual(normalize_text("cafe\u0301"), "café")
        self.assertEqual(error_rates(["Olá, água!"], ["olá água"]), {"wer": 0.0, "cer": 0.0})
        self.assertEqual(error_rates(["café"], ["cafe"]), {"wer": 1.0, "cer": .25})

    def test_substitutions_insertions_and_deletions(self):
        self.assertEqual(error_rates(["a b c"], ["a x c"]), {"wer": 1 / 3, "cer": 1 / 5})
        self.assertEqual(error_rates(["a b"], ["a"]), {"wer": .5, "cer": 2 / 3})
        self.assertEqual(error_rates(["a"], ["a b c"]), {"wer": 2.0, "cer": 4.0})

    def test_aggregates_counts_instead_of_averaging_per_utterance(self):
        rates = error_rates(["a", "a b c"], ["x", "a b c"])
        self.assertEqual(rates, {"wer": .25, "cer": 1 / 6})

    def test_empty_transcriptions_have_explicit_behavior(self):
        self.assertEqual(error_rates([""], [""]), {"wer": 0.0, "cer": 0.0})
        self.assertEqual(error_rates([""], ["oi"]), {"wer": 1.0, "cer": 2.0})
        self.assertEqual(error_rates(["oi"], [""]), {"wer": 1.0, "cer": 1.0})

    def test_invalid_inputs(self):
        for references, hypotheses in (([], []), (["a"], []), ([], ["a"]), ([None], ["a"]), ("a", "b")):
            with self.subTest(references=references), self.assertRaises(ValueError):
                error_rates(references, hypotheses)


if __name__ == "__main__":
    unittest.main()
