"""Síntese de voz local com uma voz de português instalada no Windows."""

import base64
import subprocess
import sys


MAX_TEXT_LENGTH = 5000
SPEECH_TIMEOUT_SECONDS = 300

# This script is constant. User text travels only through UTF-8 standard input,
# never as PowerShell code, a command-line argument, or SSML.
_POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$synth = $null
try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $voices = @($synth.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'pt'
    })
    if ($voices.Count -eq 0) {
        [Console]::Error.WriteLine('RECEPTOR_NO_PORTUGUESE_VOICE')
        exit 3
    }
    $selected = $voices | Sort-Object @{
        Expression = { if ($_.VoiceInfo.Culture.Name -eq 'pt-BR') { 0 } else { 1 } }
    }, @{ Expression = { $_.VoiceInfo.Name } } | Select-Object -First 1
    $synth.SelectVoice($selected.VoiceInfo.Name)
    $synth.SetOutputToDefaultAudioDevice()
    $message = [Console]::In.ReadToEnd()
    $synth.Speak($message)
}
catch {
    [Console]::Error.WriteLine('RECEPTOR_SPEECH_FAILED')
    exit 4
}
finally {
    if ($null -ne $synth) { $synth.Dispose() }
}
"""
_ENCODED_SCRIPT = base64.b64encode(_POWERSHELL_SCRIPT.encode("utf-16-le")).decode("ascii")


def speak_text(text: str) -> None:
    """Read plain text aloud; callers with a GUI must run this in a worker.

    No audio or text is saved. Only installed Portuguese voices are used, with
    Brazilian Portuguese preferred. Raises ValueError for invalid input and
    RuntimeError when local speech is unavailable or fails.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Digite um texto antes de pedir a leitura em voz alta.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError("Use um texto de até 5000 caracteres para a leitura em voz alta.")
    if sys.platform != "win32":
        raise RuntimeError("A leitura em voz alta desta versão está disponível apenas no Windows.")

    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        _ENCODED_SCRIPT,
    ]
    try:
        result = subprocess.run(
            command,
            input=text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            shell=False,
            check=False,
            timeout=SPEECH_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "A leitura ultrapassou 5 minutos e foi interrompida. "
            "Tente um texto menor e verifique a saída de áudio do Windows."
        ) from None
    except OSError:
        raise RuntimeError(
            "Não foi possível iniciar a voz local. Verifique o Windows PowerShell "
            "e instale uma voz de português compatível com System.Speech no Windows."
        ) from None

    if result.returncode == 3:
        raise RuntimeError(
            "Nenhuma voz de português compatível foi encontrada. "
            "Instale uma voz de português nas configurações de Fala do Windows "
            "que esteja disponível para System.Speech e abra o Receptor novamente."
        )
    if result.returncode != 0:
        # Do not include process output: it could contain sensitive input text.
        raise RuntimeError(
            "Não foi possível reproduzir a mensagem. Verifique a saída de áudio "
            "e instale ou habilite uma voz de português compatível com "
            "System.Speech nas configurações de Fala do Windows."
        )
