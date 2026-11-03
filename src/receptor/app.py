"""Interface desktop local: comunicação por texto/frases e transcrição revisável."""

from queue import Empty, Queue
from threading import Thread
from typing import Callable


def run(model_name: str = "openai/whisper-tiny", language: str = "portuguese") -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except ImportError as exc:
        raise RuntimeError("Instale uma distribuição Python com suporte a Tcl/Tk para abrir a janela.") from exc

    from receptor.speech import speak_text

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Não foi possível abrir a janela. Execute em uma sessão gráfica com Tcl/Tk.") from exc
    root.title("Receptor — comunicação")
    root.geometry("900x720")
    root.minsize(900, 720)
    root.configure(background="#f1f5f9")
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#f1f5f9")
    style.configure("TLabel", background="#f1f5f9", foreground="#102a43", font=("Segoe UI", 12))
    style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"))
    style.configure("TButton", font=("Segoe UI", 14), padding=12)
    style.configure("Speak.TButton", background="#164e63", foreground="white")
    style.map("Speak.TButton", background=[("active", "#0e3746"), ("disabled", "#526977")])
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(4, weight=1)

    ttk.Label(frame, text="Receptor", style="Title.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text="Escreva, escolha uma frase ou transcreva um áudio.").grid(
        row=1, column=0, sticky="w", pady=(0, 16)
    )
    quick = ttk.Frame(frame)
    quick.grid(row=2, column=0, sticky="ew", pady=(0, 16))
    editor: tk.Text

    def choose_phrase(phrase: str) -> None:
        editor.delete("1.0", "end")
        editor.insert("1.0", phrase)
        editor.focus_set()
        status.set("Frase pronta. Você pode editar antes de falar.")

    for index, phrase in enumerate(("Sim.", "Não.", "Preciso de água.", "Preciso de ajuda.")):
        quick.columnconfigure(index, weight=1)
        ttk.Button(quick, text=phrase, command=lambda text=phrase: choose_phrase(text)).grid(
            row=0, column=index, sticky="ew", padx=(0, 6)
        )
    ttk.Label(frame, text="Sua mensagem (revise a transcrição antes de falar):").grid(
        row=3, column=0, sticky="w", pady=(0, 6)
    )
    editor = tk.Text(
        frame, wrap="word", font=("Segoe UI", 20), height=6, padx=14, pady=14,
        foreground="#102a43", background="white", insertbackground="#102a43",
        relief="solid", borderwidth=1, undo=True,
    )
    editor.grid(row=4, column=0, sticky="nsew")
    # Tab moves focus rather than inserting tabs, keeping the whole flow keyboard usable.
    def next_focus(event: object) -> str:
        editor.tk_focusNext().focus_set()
        return "break"

    def previous_focus(event: object) -> str:
        editor.tk_focusPrev().focus_set()
        return "break"

    editor.bind("<Tab>", next_focus)
    editor.bind("<Shift-Tab>", previous_focus)
    controls = ttk.Frame(frame)
    controls.grid(row=5, column=0, sticky="ew", pady=12)
    status = tk.StringVar(value="Pronto. O texto só será lido ao acionar Falar texto.")
    messages: Queue[tuple[str, str]] = Queue()
    busy = False
    active_kind = ""
    snapshot = ""
    pending_transcription: str | None = None

    def start(kind: str, task: Callable[[], str | None]) -> None:
        nonlocal busy, active_kind
        if busy:
            return
        busy, active_kind = True, kind
        speak_button.state(["disabled"])
        audio_button.state(["disabled"])
        status.set(
            "Lendo sua mensagem…" if kind == "speech" else
            "Transcrevendo… No primeiro uso, o modelo será baixado. Aguarde."
        )

        def work() -> None:
            try:
                result = task()
                messages.put(("ok", result or ""))
            except Exception as exc:
                messages.put(("error", str(exc)))

        Thread(target=work, daemon=True).start()

    def speak() -> None:
        text = editor.get("1.0", "end-1c")
        if not text.strip():
            status.set("Escreva uma mensagem ou escolha uma frase primeiro.")
            editor.focus_set()
            return
        start("speech", lambda: speak_text(text))

    def open_audio() -> None:
        nonlocal snapshot, pending_transcription
        from pathlib import Path
        from receptor.ml import transcribe
        selected = filedialog.askopenfilename(
            title="Abrir WAV: mono, 16 kHz, PCM 16 bits, até 30 segundos",
            filetypes=[("Áudio WAV", "*.wav")],
        )
        if selected:
            snapshot = editor.get("1.0", "end-1c")
            pending_transcription = None
            use_result.state(["disabled"])
            start("transcription", lambda: transcribe(Path(selected), model_name, language))

    def apply_transcription() -> None:
        nonlocal pending_transcription
        if pending_transcription is None:
            return
        editor.delete("1.0", "end")
        editor.insert("1.0", pending_transcription)
        pending_transcription = None
        use_result.state(["disabled"])
        status.set("Transcrição inserida. Revise e corrija antes de falar.")
        editor.focus_set()

    speak_button = ttk.Button(controls, text="Falar texto", style="Speak.TButton", command=speak)
    speak_button.pack(side="left", padx=(0, 8))
    audio_button = ttk.Button(controls, text="Abrir áudio WAV", command=open_audio)
    audio_button.pack(side="left", padx=(0, 8))
    ttk.Button(controls, text="Limpar", command=lambda: choose_phrase("")).pack(side="left")
    use_result = ttk.Button(frame, text="Substituir mensagem pela transcrição", command=apply_transcription)
    use_result.grid(row=6, column=0, sticky="w", pady=(0, 8))
    use_result.state(["disabled"])
    ttk.Label(frame, textvariable=status, wraplength=810).grid(row=7, column=0, sticky="w", pady=8)
    ttk.Label(
        frame,
        text="Voz: português instalado no Windows. Áudio: WAV mono, 16 kHz, 16 bits, até 30 s.\n"
             "O reconhecimento pode errar. As mensagens não são salvas pelo aplicativo.",
        wraplength=810,
    ).grid(row=8, column=0, sticky="w", pady=(6, 0))

    def poll() -> None:
        nonlocal busy, pending_transcription
        try:
            outcome, value = messages.get_nowait()
        except Empty:
            pass
        else:
            busy = False
            speak_button.state(["!disabled"])
            audio_button.state(["!disabled"])
            if outcome == "error":
                status.set(value)
            elif active_kind == "speech":
                status.set("Leitura concluída.")
            elif not value.strip():
                status.set("Nenhuma transcrição foi gerada. Você pode digitar a mensagem.")
            elif editor.get("1.0", "end-1c") != snapshot or snapshot.strip():
                # Never overwrite a message typed while the background model was running.
                pending_transcription = value
                use_result.state(["!disabled"])
                status.set("Transcrição pronta. Use o botão acima para substituir sua mensagem atual.")
            else:
                pending_transcription = value
                apply_transcription()
        root.after(100, poll)

    editor.focus_set()
    root.after(100, poll)
    root.mainloop()
