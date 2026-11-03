export async function transcribeAudio(file: File, consent: boolean, signal?: AbortSignal): Promise<string> {
  if (!consent) throw new Error('Autorize o processamento deste áudio antes de continuar.')
  if (file.size > 1024 * 1024) throw new Error('O arquivo deve ter no máximo 1 MB.')
  const body = new FormData()
  body.append('file', file)
  body.append('consent', 'true')
  const response = await fetch('/api/transcriptions', { method: 'POST', body, signal, cache: 'no-store' })
  if (!response.ok) {
    const errors: Record<number, string> = {
      413: 'O arquivo deve ter no máximo 1 MB.',
      422: 'Confira o áudio: WAV mono, 16 kHz, 16 bits e até 30 segundos.',
      429: 'Já existe uma transcrição em andamento. Tente novamente em instantes.',
      503: 'A transcrição está indisponível. Você pode continuar escrevendo ou usando as frases.',
    }
    throw new Error(errors[response.status] ?? 'Não foi possível transcrever. Tente novamente.')
  }
  const result: unknown = await response.json()
  if (!result || typeof result !== 'object' || !('text' in result) || typeof result.text !== 'string') {
    throw new Error('O serviço retornou uma resposta inválida.')
  }
  return result.text
}
