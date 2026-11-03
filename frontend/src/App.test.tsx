import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { localPortugueseVoices } from './speech'
import { transcribeAudio } from './api'

vi.mock('virtual:pwa-register/react', () => ({
  useRegisterSW: () => ({ offlineReady: [false], needRefresh: [false], updateServiceWorker: vi.fn() }),
}))

const voice = { name: 'Português local', lang: 'pt-BR', localService: true } as SpeechSynthesisVoice
const synth = { getVoices: vi.fn(() => [voice]), addEventListener: vi.fn(), removeEventListener: vi.fn(), cancel: vi.fn(), speak: vi.fn() }
const fetchMock = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  synth.getVoices.mockReturnValue([voice])
  vi.stubGlobal('speechSynthesis', synth)
  vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; constructor(text: string) { this.text = text } })
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (url: string) => ({ ok: true, json: async () => url === '/api/health' ? { status: 'ok' } : { text: 'Transcrição de teste.', review_required: true } }))
})
afterEach(() => vi.unstubAllGlobals())

describe('comunicação com controle da pessoa', () => {
  it('escolher uma frase preenche o editor sem falar automaticamente', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    await userEvent.click(screen.getByRole('button', { name: 'Frases rápidas' }))
    await userEvent.click(screen.getByRole('button', { name: 'Quero água' }))
    expect(screen.getByLabelText('Sua mensagem')).toHaveValue('Preciso de água.')
    expect(synth.speak).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Falar mensagem' }))
    expect(synth.speak).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: 'Parar' }))
    expect(synth.cancel).toHaveBeenCalled()
  })

  it('exige autorização para envio e revisão explícita antes de substituir uma mensagem', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    await screen.findByText('Transcrição conectada')
    const editor = screen.getByLabelText('Sua mensagem')
    await userEvent.type(editor, 'Minha mensagem atual')
    const file = new File(['fake WAV; backend is mocked'], 'amostra.wav', { type: 'audio/wav' })
    await userEvent.upload(screen.getByLabelText('Escolher áudio WAV'), file)
    const send = screen.getByRole('button', { name: 'Transcrever áudio' })
    expect(send).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox'))
    expect(send).toBeEnabled()
    await userEvent.click(send)
    const review = await screen.findByLabelText('Revise a transcrição')
    expect(review).toHaveValue('Transcrição de teste.')
    expect(editor).toHaveValue('Minha mensagem atual')
    expect(synth.speak).not.toHaveBeenCalled()
    await userEvent.clear(review)
    await userEvent.type(review, 'Texto corrigido.')
    await userEvent.click(screen.getByRole('button', { name: 'Usar na minha mensagem' }))
    expect(editor).toHaveValue('Texto corrigido.')
    const uploadCall = fetchMock.mock.calls.find(call => call[0] === '/api/transcriptions')!
    expect((uploadCall[1].body as FormData).get('consent')).toBe('true')
  })

  it('mantém frases disponíveis com API fora do ar e sem voz compatível', async () => {
    synth.getVoices.mockReturnValue([])
    fetchMock.mockRejectedValue(new TypeError('offline'))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    await screen.findByText('Transcrição desconectada')
    await userEvent.click(screen.getByRole('button', { name: 'Frases rápidas' }))
    await userEvent.click(screen.getByRole('button', { name: 'Estou bem' }))
    expect(screen.getByLabelText('Sua mensagem')).toHaveValue('Estou bem.')
    expect(screen.getByRole('button', { name: 'Falar mensagem' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    expect(screen.getByRole('button', { name: 'Transcrever áudio' })).toBeDisabled()
  })

  it('trocar o arquivo revoga a autorização anterior', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    await screen.findByText('Transcrição conectada')
    const input = screen.getByLabelText('Escolher áudio WAV')
    await userEvent.upload(input, new File(['one'], 'um.wav', { type: 'audio/wav' }))
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.upload(input, new File(['two'], 'dois.wav', { type: 'audio/wav' }))
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    expect(screen.getByRole('button', { name: 'Transcrever áudio' })).toBeDisabled()
  })

  it('não envia arquivos acima do limite', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    fireEvent.change(screen.getByLabelText('Escolher áudio WAV'), { target: { files: [new File([new Uint8Array(1024 * 1024 + 1)], 'grande.wav')] } })
    await screen.findByText('Escolha um WAV de até 1 MB.')
    expect(fetchMock.mock.calls.some(call => call[0] === '/api/transcriptions')).toBe(false)
  })

  it('mostra falhas da API sem substituir o texto digitado', async () => {
    fetchMock.mockImplementation(async (url: string) => url === '/api/health'
      ? { ok: true, json: async () => ({ status: 'ok' }) }
      : { ok: false, status: 503 })
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Áudio' }))
    await screen.findByText('Transcrição conectada')
    await userEvent.type(screen.getByLabelText('Sua mensagem'), 'Texto preservado')
    await userEvent.upload(screen.getByLabelText('Escolher áudio WAV'), new File(['x'], 'x.wav', { type: 'audio/wav' }))
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Transcrever áudio' }))
    await waitFor(() => expect(screen.getByText(/A transcrição está indisponível/)).toBeInTheDocument())
    expect(screen.getByLabelText('Sua mensagem')).toHaveValue('Texto preservado')
  })
})

it('filtra vozes remotas e prioriza português brasileiro', () => {
  const portuguese = { name: 'PT', lang: 'pt-PT', localService: true } as SpeechSynthesisVoice
  expect(localPortugueseVoices([portuguese, { ...voice, localService: false }, { ...voice, lang: 'en-US' }, voice])).toEqual([voice, portuguese])
})

it('a camada HTTP também recusa falta de autorização antes de qualquer envio', async () => {
  await expect(transcribeAudio(new File(['x'], 'x.wav'), false)).rejects.toThrow('Autorize')
  expect(fetchMock).not.toHaveBeenCalled()
})
