import base64
import subprocess
import unittest
from unittest.mock import patch

from receptor.speech import speak_text


class SpeechTests(unittest.TestCase):
    def test_text_is_sent_only_through_stdin_without_a_shell(self):
        message = "Água, por favor. '; Write-Output PRIVATE; $(Get-Process)\n<speak>oi</speak>"
        with patch("receptor.speech.sys.platform", "win32"), patch(
            "receptor.speech.subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ) as run:
            self.assertIsNone(speak_text(message))
        args, kwargs = run.call_args
        command = args[0]
        self.assertEqual(command[0], "powershell.exe")
        self.assertIn("-NoProfile", command)
        self.assertIn("-NonInteractive", command)
        self.assertEqual(kwargs["input"], message)
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertTrue(kwargs["text"])
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], 300)
        self.assertEqual(kwargs["creationflags"], 0x08000000)
        script = base64.b64decode(command[-1]).decode("utf-16-le")
        self.assertNotIn(message, script)
        self.assertNotIn("PRIVATE", script)
        self.assertNotIn(message, " ".join(command))
        self.assertIn("[Console]::In.ReadToEnd()", script)
        self.assertIn("$synth.Speak($message)", script)
        self.assertNotIn("SpeakSsml", script)
        self.assertTrue(script.isascii())

    def test_invalid_text_never_launches_a_process(self):
        with patch("receptor.speech.subprocess.run") as run:
            for message in (None, 42, "", " \n\t", "x" * 5001):
                with self.subTest(message_type=type(message)), self.assertRaises(ValueError):
                    speak_text(message)
            run.assert_not_called()

    def test_maximum_length_is_accepted(self):
        with patch("receptor.speech.sys.platform", "win32"), patch(
            "receptor.speech.subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ) as run:
            speak_text("a" * 5000)
            self.assertEqual(len(run.call_args.kwargs["input"]), 5000)

    def test_other_platforms_do_not_launch_a_process(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform), patch(
                "receptor.speech.sys.platform", platform
            ), patch("receptor.speech.subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "apenas no Windows"):
                    speak_text("Olá")
                run.assert_not_called()

    def test_missing_portuguese_voice_gives_installation_guidance(self):
        with patch("receptor.speech.sys.platform", "win32"), patch(
            "receptor.speech.subprocess.run", return_value=subprocess.CompletedProcess([], 3)
        ):
            with self.assertRaisesRegex(RuntimeError, "Instale uma voz de português"):
                speak_text("Olá")

    def test_synthesis_failure_does_not_expose_process_output(self):
        result = subprocess.CompletedProcess([], 4, stdout="SECRET", stderr="PRIVATE MESSAGE")
        with patch("receptor.speech.sys.platform", "win32"), patch(
            "receptor.speech.subprocess.run", return_value=result
        ):
            with self.assertRaisesRegex(RuntimeError, "voz de português") as caught:
                speak_text("PRIVATE MESSAGE")
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))

    def test_missing_powershell_gives_actionable_error(self):
        with patch("receptor.speech.sys.platform", "win32"), patch(
            "receptor.speech.subprocess.run", side_effect=FileNotFoundError("not installed")
        ):
            with self.assertRaisesRegex(RuntimeError, "Windows PowerShell"):
                speak_text("Olá")

    def test_timeout_is_reported_without_private_output(self):
        error = subprocess.TimeoutExpired("powershell.exe", 300, output="PRIVATE")
        with patch("receptor.speech.sys.platform", "win32"), patch(
            "receptor.speech.subprocess.run", side_effect=error
        ):
            with self.assertRaisesRegex(RuntimeError, "5 minutos") as caught:
                speak_text("PRIVATE")
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
