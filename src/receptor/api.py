"""API local de transcrição: sem retenção de áudio e sem carregar IA no startup.

Execute com um único processo, vinculado a 127.0.0.1. O frontend usa o proxy
de mesma origem; não há autorização de origens externas por CORS.
"""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import tempfile
from threading import Lock
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, UploadFile as StarletteUploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from receptor.data import validate_audio


MAX_AUDIO_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
DEFAULT_MODEL = "openai/whisper-tiny"
Transcriber = Callable[[Path, str, str], str]

_INVALID_UPLOAD = (
    "Envie um único arquivo WAV e consent=true para autorizar esta transcrição."
)
_INVALID_AUDIO = "Use WAV PCM de 16 bits, mono, a 16000 Hz, com duração de até 30 segundos."
_UNAVAILABLE = (
    "A transcrição está indisponível. Verifique as dependências de IA e a "
    "disponibilidade do modelo no servidor. Você pode continuar digitando."
)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    model: str


class TranscriptionResponse(BaseModel):
    text: str
    review_required: Literal[True] = True


async def _check_multipart_in_memory(scope: Scope, body: bytes) -> None:
    """Verifica consentimento e tamanho antes do parser padrão criar um spool.

    O corpo já está limitado a 2 MiB. Este parser mantém todo o arquivo em
    memória; o segundo parsing do FastAPI recebe apenas arquivos <= 1 MiB,
    dentro do limite de memória padrão do UploadFile.
    """
    headers = Headers(scope=scope)
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise HTTPException(status_code=422, detail=_INVALID_UPLOAD)

    async def stream():
        yield body

    parser = MultiPartParser(headers, stream(), max_files=1, max_fields=1, max_part_size=64)
    parser.spool_max_size = MAX_REQUEST_BYTES
    try:
        form = await parser.parse()
    except (MultiPartException, ValueError):
        raise HTTPException(status_code=422, detail=_INVALID_UPLOAD) from None
    try:
        files = form.getlist("file")
        if form.getlist("consent") != ["true"] or len(files) != 1:
            raise HTTPException(status_code=422, detail=_INVALID_UPLOAD)
        upload = files[0]
        if not isinstance(upload, StarletteUploadFile):
            raise HTTPException(status_code=422, detail=_INVALID_UPLOAD)
        if upload.size is None or upload.size > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="O arquivo WAV deve ter até 1 MiB.")
    finally:
        await form.close()


class _RequestPolicyMiddleware:
    """Limita o corpo bruto antes do parser multipart, mesmo sem Content-Length.

    No máximo 2 MiB ficam em memória aqui. O limite separado de 1 MiB do áudio
    é verificado na rota. Cabeçalhos no-store também acompanham respostas de erro.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        cache_policy = None
        if path == "/api" or path.startswith("/api/"):
            cache_policy = b"no-store"
        elif path in ("/", "/index.html", "/sw.js"):
            cache_policy = b"no-cache"

        async def policy_send(message: Message) -> None:
            if message["type"] == "http.response.start" and cache_policy is not None:
                headers = [
                    pair for pair in message.get("headers", [])
                    if pair[0].lower() != b"cache-control"
                ]
                message = {**message, "headers": headers + [(b"cache-control", cache_policy)]}
            await send(message)

        async def reject(status: int, detail: str) -> None:
            await JSONResponse({"detail": detail}, status_code=status)(
                scope, receive, policy_send,
            )

        if scope["method"] == "POST" and scope["path"] == "/api/transcriptions":
            lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
            if lengths:
                try:
                    if len(lengths) != 1 or int(lengths[0]) < 0:
                        raise ValueError
                    declared_length = int(lengths[0])
                except ValueError:
                    await reject(400, "O tamanho informado na requisição é inválido.")
                    return
                if declared_length > MAX_REQUEST_BYTES:
                    await reject(413, "O envio excede o limite de tamanho permitido.")
                    return

            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                    await reject(413, "O envio excede o limite de tamanho permitido.")
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break

            payload = bytes(body)
            del body
            try:
                await _check_multipart_in_memory(scope, payload)
            except HTTPException as error:
                await reject(error.status_code, error.detail)
                return
            delivered = False

            async def bounded_receive() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": payload, "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, policy_send)
            return
        await self.app(scope, receive, policy_send)


def _default_transcriber(audio_path: Path, model_name: str, language: str) -> str:
    from receptor.ml import transcribe

    return transcribe(audio_path, model_name, language)


def _process_audio(payload: bytes, model_name: str, transcriber: Transcriber) -> str:
    """O diretório temporário pertence ao worker e é removido em todos os caminhos."""
    try:
        with tempfile.TemporaryDirectory(prefix="receptor-") as temporary:
            audio_path = Path(temporary) / "audio.wav"
            audio_path.write_bytes(payload)
            try:
                validate_audio(audio_path)
            except ValueError:
                raise HTTPException(status_code=422, detail=_INVALID_AUDIO) from None
            try:
                text = transcriber(audio_path, model_name, "portuguese")
                if not isinstance(text, str):
                    raise TypeError
                return text.strip()
            except Exception:
                # Never return model errors: they can contain paths or input content.
                raise HTTPException(status_code=503, detail=_UNAVAILABLE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from None


def create_app(
    transcriber: Transcriber | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
    """Cria a API e, quando disponível, serve a build local da PWA.

    A pasta explícita tem prioridade sobre RECEPTOR_FRONTEND_DIR; sem ambos,
    usa frontend/dist do repositório. Sem index.html, apenas a API é iniciada.
    Nenhum modelo é importado ou baixado ao criar a aplicação.
    """
    app = FastAPI(title="Receptor API", version="0.1.0")
    app.add_middleware(_RequestPolicyMiddleware)
    model_name = os.environ.get("RECEPTOR_MODEL", "").strip() or DEFAULT_MODEL
    recognize = transcriber if transcriber is not None else _default_transcriber
    inference_lock = Lock()

    def busy_error() -> HTTPException:
        return HTTPException(
            status_code=429,
            detail="Já existe uma transcrição em andamento. Tente novamente em instantes.",
            headers={"Retry-After": "2"},
        )

    def process_exclusively(payload: bytes) -> str:
        # The worker owns the lock: cancellation of an HTTP task cannot release
        # it while the underlying model is still running in another thread.
        if not inference_lock.acquire(blocking=False):
            raise busy_error()
        try:
            return _process_audio(payload, model_name, recognize)
        finally:
            inference_lock.release()

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic errors can include submitted values; expose only a stable message.
        return JSONResponse({"detail": _INVALID_UPLOAD}, status_code=422)

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # This is liveness only: no weights or network calls are needed for health.
        return HealthResponse(model=model_name)

    @app.post("/api/transcriptions", response_model=TranscriptionResponse)
    async def transcriptions(
        request: Request,
        file: Annotated[UploadFile, File()],
        consent: Annotated[bool, Form()],
    ) -> TranscriptionResponse:
        try:
            form = await request.form()
            if (
                consent is not True
                or form.getlist("consent") != ["true"]
                or len(form.getlist("file")) != 1
            ):
                raise HTTPException(status_code=422, detail=_INVALID_UPLOAD)
            payload = await file.read(MAX_AUDIO_BYTES + 1)
            if len(payload) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="O arquivo WAV deve ter até 1 MiB.")
            if not payload:
                raise HTTPException(status_code=422, detail=_INVALID_AUDIO)
        finally:
            await file.close()

        # This fast check avoids scheduling a worker when inference is already busy.
        # The worker also acquires atomically without waiting, covering races.
        if inference_lock.locked():
            raise busy_error()
        text = await run_in_threadpool(process_exclusively, payload)
        return TranscriptionResponse(text=text)

    # Reserve the API namespace before mounting static files, including when a
    # frontend build provides its own 404.html or files inside an api/ folder.
    methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

    @app.api_route("/api", methods=methods, include_in_schema=False)
    @app.api_route("/api/{path:path}", methods=methods, include_in_schema=False)
    async def unknown_api() -> None:
        raise HTTPException(status_code=404, detail="Rota da API não encontrada.")

    if frontend_dir is None:
        configured_frontend = os.environ.get("RECEPTOR_FRONTEND_DIR", "").strip()
        frontend_dir = (
            Path(configured_frontend) if configured_frontend
            else Path(__file__).resolve().parents[2] / "frontend" / "dist"
        )
    frontend_dir = Path(frontend_dir).expanduser().resolve()
    if frontend_dir.is_dir() and (frontend_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()
