import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import {
  ArrowRight, ArrowUp, AudioLines, Check, CheckCheck, ChevronDown, CircleHelp, Copy,
  Download, Droplets, Heart, Hexagon, House, Info, LoaderCircle, MessageCircle, Mic, Moon,
  Plus, ShieldCheck, Smile, Square, Upload, Utensils, X,
} from 'lucide-react'
import { transcribeAudio } from './api'
import { localPortugueseVoices, MAX_MESSAGE_LENGTH } from './speech'

const phrases = [
  { text: 'Sim.', label: 'Sim', category: 'Respostas', icon: Check, color: 'mint' },
  { text: 'Não.', label: 'Não', category: 'Respostas', icon: X, color: 'rose' },
  { text: 'Preciso de água.', label: 'Quero água', category: 'Necessidades', icon: Droplets, color: 'blue' },
  { text: 'Estou com fome.', label: 'Estou com fome', category: 'Necessidades', icon: Utensils, color: 'peach' },
  { text: 'Preciso de ajuda.', label: 'Preciso de ajuda', category: 'Necessidades', icon: Heart, color: 'rose' },
  { text: 'Estou bem.', label: 'Estou bem', category: 'Sentimentos', icon: Smile, color: 'mint' },
  { text: 'Preciso descansar.', label: 'Quero descansar', category: 'Necessidades', icon: Moon, color: 'lavender' },
  { text: 'Obrigado.', label: 'Obrigado', category: 'Respostas', icon: CheckCheck, color: 'peach' },
]
const categories = ['Todas', 'Necessidades', 'Respostas', 'Sentimentos']

interface InstallPrompt extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

function App() {
  const [text, setText] = useState('')
  const [category, setCategory] = useState('Todas')
  const [notice, setNotice] = useState('')
  const [helpOpen, setHelpOpen] = useState(false)
  const [panel, setPanel] = useState<'phrases' | 'audio' | null>(null)
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [speaking, setSpeaking] = useState(false)
  const [service, setService] = useState<'checking' | 'ready' | 'unavailable'>('checking')
  const [connected, setConnected] = useState(navigator.onLine)
  const [file, setFile] = useState<File | null>(null)
  const [consent, setConsent] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [transcription, setTranscription] = useState('')
  const [hasTranscription, setHasTranscription] = useState(false)
  const [audioNotice, setAudioNotice] = useState('')
  const [installPrompt, setInstallPrompt] = useState<InstallPrompt | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const request = useRef<AbortController | null>(null)
  const speech = useRef<SpeechSynthesisUtterance | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const { offlineReady: [offlineReady], needRefresh: [needRefresh], updateServiceWorker } = useRegisterSW({
    onRegisterError() { setNotice('Não foi possível preparar o modo sem conexão. Tente recarregar depois.') },
  })

  useLayoutEffect(() => {
    const resizeMessage = () => {
      const textarea = editor.current
      if (!textarea) return
      textarea.style.height = 'auto'
      textarea.style.height = `${textarea.scrollHeight}px`
    }
    resizeMessage()
    window.addEventListener('resize', resizeMessage)
    return () => window.removeEventListener('resize', resizeMessage)
  }, [text])

  useEffect(() => {
    if (!('speechSynthesis' in window)) return
    const synth = window.speechSynthesis
    const refresh = () => setVoices(localPortugueseVoices(synth.getVoices()))
    refresh()
    synth.addEventListener('voiceschanged', refresh)
    return () => { synth.removeEventListener('voiceschanged', refresh); synth.cancel() }
  }, [])

  useEffect(() => {
    let controller: AbortController | null = null
    let disposed = false
    const check = async () => {
      controller?.abort()
      controller = new AbortController()
      const current = controller
      const timeout = setTimeout(() => current.abort(), 4000)
      try {
        const response = await fetch('/api/health', { cache: 'no-store', signal: current.signal })
        const body = await response.json()
        if (!disposed && controller === current) setService(response.ok && body.status === 'ok' ? 'ready' : 'unavailable')
      } catch {
        if (!disposed && controller === current) setService('unavailable')
      } finally { clearTimeout(timeout) }
    }
    const online = () => { setConnected(true); void check() }
    const offline = () => { setConnected(false); setService('unavailable') }
    void check()
    const interval = setInterval(() => { void check() }, 30000)
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      disposed = true; controller?.abort(); clearInterval(interval)
      window.removeEventListener('online', online); window.removeEventListener('offline', offline)
    }
  }, [])

  useEffect(() => {
    const capture = (event: Event) => { event.preventDefault(); setInstallPrompt(event as InstallPrompt) }
    const installed = () => { setInstallPrompt(null); setNotice('Receptor instalado neste dispositivo.') }
    window.addEventListener('beforeinstallprompt', capture)
    window.addEventListener('appinstalled', installed)
    return () => {
      window.removeEventListener('beforeinstallprompt', capture)
      window.removeEventListener('appinstalled', installed)
      request.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (helpOpen) dialog.current?.showModal()
    else dialog.current?.close()
  }, [helpOpen])

  function speak() {
    const selected = voices[0]
    if (!text.trim() || !selected || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.voice = selected; utterance.lang = selected.lang; utterance.rate = 0.9
    utterance.onstart = () => { if (speech.current === utterance) setSpeaking(true) }
    utterance.onend = () => {
      if (speech.current !== utterance) return
      speech.current = null; setSpeaking(false); setNotice('Leitura concluída.')
    }
    utterance.onerror = event => {
      if (speech.current !== utterance) return
      speech.current = null
      setSpeaking(false)
      if (event.error !== 'canceled' && event.error !== 'interrupted') {
        setNotice('Não foi possível ler. Confira a voz instalada e o áudio do dispositivo.')
      }
    }
    speech.current = utterance
    setSpeaking(true); setNotice('Lendo sua mensagem…')
    window.speechSynthesis.speak(utterance)
  }

  function stop() {
    speech.current = null
    window.speechSynthesis?.cancel(); setSpeaking(false); setNotice('Leitura interrompida.')
  }

  async function copy() {
    try { await navigator.clipboard.writeText(text); setNotice('Mensagem copiada.') }
    catch { setNotice('Selecione o texto e use a opção Copiar do seu dispositivo.'); editor.current?.focus() }
  }

  async function install() {
    if (installPrompt) {
      await installPrompt.prompt(); await installPrompt.userChoice; setInstallPrompt(null)
    } else {
      setHelpOpen(true)
    }
  }

  async function transcribe() {
    if (!file || !consent || transcribing) return
    const controller = new AbortController()
    request.current = controller
    setTranscribing(true); setAudioNotice('Preparando a transcrição. A primeira vez pode demorar para carregar o modelo.')
    try {
      const result = await transcribeAudio(file, consent, controller.signal)
      setTranscription(result)
      setHasTranscription(Boolean(result.trim()))
      setAudioNotice(result.trim() ? 'Transcrição pronta. Revise antes de usar.' : 'Nenhuma fala foi reconhecida. Você pode escrever sua mensagem.')
    } catch (error) {
      if (controller.signal.aborted) setAudioNotice('Solicitação cancelada. O servidor pode terminar o processamento já iniciado.')
      else setAudioNotice(error instanceof TypeError ? 'Não foi possível conectar ao serviço de transcrição.' : error instanceof Error ? error.message : 'Não foi possível transcrever.')
    } finally { setTranscribing(false); request.current = null }
  }

  function useTranscription() {
    if (transcription.length > MAX_MESSAGE_LENGTH) {
      setAudioNotice('Reduza a transcrição para até 5.000 caracteres antes de usar.')
      return
    }
    setText(transcription)
    setNotice('Transcrição inserida na sua mensagem. Você pode editar antes de falar.')
    editor.current?.focus()
  }

  return (
    <div className="app">
      <a className="skip-link" href="#mensagem">Ir para minha mensagem</a>
      <header className="header">
        <a href="/" className="brand" aria-label="Receptor, início" onClick={event => { event.preventDefault(); setPanel(null); editor.current?.focus() }}>
          <span className="brand-mark"><img src="/logo.png" alt="" /></span>
          <span>Receptor.</span>
        </a>
        <nav className="mode-switch" aria-label="Forma de comunicação">
          <button className={panel !== 'audio' ? 'active' : ''} aria-pressed={panel !== 'audio'} onClick={() => { setPanel(null); editor.current?.focus() }}>Texto</button>
          <button className={panel === 'audio' ? 'active' : ''} aria-pressed={panel === 'audio'} onClick={() => setPanel('audio')}>Áudio</button>
        </nav>
      </header>

      <main className="main">
        <h1>O que você quer comunicar?</h1>
        {needRefresh && <div className="update-banner" role="status">Há uma nova versão. Salve sua mensagem antes de atualizar.
          <button onClick={() => { void updateServiceWorker(true) }}>Atualizar agora</button></div>}
        <nav className="action-bar" aria-label="Ferramentas da mensagem">
          <button aria-expanded={panel === 'phrases'} aria-controls="phrases-panel" onClick={() => setPanel(panel === 'phrases' ? null : 'phrases')}><MessageCircle size={18} /><span>Frases rápidas</span></button>
          <button disabled={!text} onClick={() => { void copy() }}><Copy size={17} /><span>Copiar</span></button>
          <button disabled={!text} onClick={() => { setText(''); setNotice('Mensagem limpa.'); editor.current?.focus() }}><X size={18} /><span>Limpar</span></button>
          <button onClick={() => setHelpOpen(true)}><CircleHelp size={18} /><span>Como usar</span></button>
          <button className="install-button" onClick={() => { void install() }}><Download size={17} /><span>Instalar aplicativo</span></button>
        </nav>
        <section className="compose" aria-label="Minha mensagem">
          <label htmlFor="mensagem" className="sr-only">Sua mensagem</label>
          <textarea id="mensagem" ref={editor} value={text} maxLength={MAX_MESSAGE_LENGTH}
            onChange={event => setText(event.target.value)} placeholder="Escreva sua mensagem para o Receptor" />
          <div className="composer-actions">
            <button className="icon-button add-audio" aria-label="Adicionar áudio" title="Adicionar áudio WAV" aria-expanded={panel === 'audio'} aria-controls="audio-panel" onClick={() => setPanel(panel === 'audio' ? null : 'audio')}><Plus size={17} /></button>
            <button className="auto-button" title="Seleção automática de voz em português" onClick={() => setNotice(voices.length ? 'A voz local em português é selecionada automaticamente.' : 'Nenhuma voz local de português está disponível neste navegador.')}><Hexagon size={15} /><span>Auto</span></button>
            <span className="character-count">{text ? `${text.length.toLocaleString('pt-BR')} / 5.000` : ''}</span>
            <div className="composer-right">
              <details className="create-control" onKeyDown={event => {
                if (event.key === 'Escape') {
                  event.currentTarget.removeAttribute('open')
                  event.currentTarget.querySelector('summary')?.focus()
                }
              }}>
                <summary>Criar <ChevronDown size={13} /></summary>
                <div className="create-options">
                  <button onClick={event => { editor.current?.focus(); event.currentTarget.closest('details')?.removeAttribute('open') }}><MessageCircle size={16} /> Escrever mensagem</button>
                  <button onClick={event => { setPanel('phrases'); event.currentTarget.closest('details')?.removeAttribute('open') }}><Plus size={16} /> Usar frase pronta</button>
                  <button onClick={event => { setPanel('audio'); event.currentTarget.closest('details')?.removeAttribute('open') }}><AudioLines size={16} /> Transcrever um áudio</button>
                </div>
              </details>
              <button className="icon-button microphone-button" aria-label="Abrir transcrição de áudio" title="Transcrever um arquivo de áudio" aria-expanded={panel === 'audio'} aria-controls="audio-panel" onClick={() => setPanel(panel === 'audio' ? null : 'audio')}><Mic size={17} /></button>
              {speaking && <button className="icon-button stop-button" onClick={stop} aria-label="Parar" title="Parar leitura"><Square size={15} /></button>}
              <button className="speak-button" disabled={!text.trim() || !voices.length || speaking} onClick={speak} aria-label="Falar mensagem" title="Falar mensagem"><ArrowUp size={17} /></button>
            </div>
          </div>
        </section>
        <div className="message-status" role="status" aria-live="polite">{notice || <><ShieldCheck size={16} /> Sua mensagem, no seu tempo. Você decide quando falar.</>}</div>
        {!voices.length && <p className="inline-note"><Info size={15} /> Para ouvir, habilite uma voz local de português no dispositivo. Você pode escrever e mostrar o texto.</p>}
        <div id="phrases-panel" className="expandable-panel" hidden={panel !== 'phrases'}>
            <section className="quick-section" aria-labelledby="quick-heading">
              <div className="quick-heading"><h2 id="quick-heading">Palavras que aproximam</h2><span>Um toque para começar</span></div>
              <div className="categories" aria-label="Filtrar frases">{categories.map(item =>
                <button key={item} aria-pressed={category === item} className={category === item ? 'selected' : ''} onClick={() => setCategory(item)}>{item}</button>,
              )}</div>
              <div className="phrases-grid">{phrases.filter(phrase => category === 'Todas' || phrase.category === category).map(phrase =>
                <button className="phrase" key={phrase.label} onClick={() => { setText(phrase.text); setNotice('Frase escolhida. Você pode editar antes de falar.'); editor.current?.focus() }}>
                  <span className={`phrase-icon ${phrase.color}`}><phrase.icon size={22} strokeWidth={1.8} /></span>
                  <span>{phrase.label}</span><Plus className="phrase-plus" size={14} />
                </button>,
              )}</div>
            </section>
        </div>
        <div id="audio-panel" className="expandable-panel" hidden={panel !== 'audio'}>
          <p className="connection" role="status">{!connected ? 'Sem conexão' : service === 'ready' ? 'Transcrição conectada' : service === 'checking' ? 'Conectando transcrição' : 'Transcrição desconectada'}</p>
            <section className="card audio-card" aria-labelledby="audio-heading">
              <div className="section-heading"><div className="title-with-icon"><span className="heading-icon"><AudioLines size={20} /></span><h2 id="audio-heading">Da fala ao texto</h2></div></div>
              <p className="section-description">Envie um áudio e revise a transcrição.<br />A sua mensagem continua sendo sua.</p>
              <label className={`upload-area ${file ? 'has-file' : ''} ${transcribing ? 'disabled' : ''}`}>
                <input type="file" accept=".wav,audio/wav,audio/x-wav" aria-label="Escolher áudio WAV" disabled={transcribing} onChange={event => {
                  const selected = event.target.files?.[0] ?? null
                  setTranscription(''); setHasTranscription(false); setConsent(false); setAudioNotice('')
                  if (selected && selected.size > 1024 * 1024) { setFile(null); setAudioNotice('Escolha um WAV de até 1 MB.'); event.target.value = '' }
                  else setFile(selected)
                }} />
                <span className="upload-icon">{file ? <Check size={25} /> : <Upload size={25} />}</span>
                <strong>{file ? file.name : 'Escolher um áudio'}</strong><span>{file ? 'Clique para trocar o arquivo' : 'Selecione um arquivo do dispositivo'}</span>
                <span className="format-tag">WAV · ATÉ 30 SEGUNDOS · 1 MB</span>
              </label>
              <p className="audio-format">Mono, 16 kHz e 16 bits. A gravação por microfone será adicionada em uma próxima versão.</p>
              <label className="consent"><input type="checkbox" checked={consent} disabled={transcribing} onChange={event => setConsent(event.target.checked)} />
                <span>Autorizo processar este áudio para transcrição. Ele não será usado para treinamento.</span></label>
              <button className="transcribe-button" disabled={!file || !consent || transcribing || service !== 'ready'} onClick={() => { void transcribe() }}>
                {transcribing ? <LoaderCircle className="spin" size={18} /> : <AudioLines size={18} />}{transcribing ? 'Transcrevendo…' : 'Transcrever áudio'}{!transcribing && <ArrowRight size={16} />}
              </button>
              {transcribing && <button className="small-button cancel-upload" onClick={() => request.current?.abort()}>Cancelar solicitação</button>}
              <p className="audio-status" role="status">{audioNotice || (service === 'unavailable' ? 'Transcrição indisponível agora. As mensagens e frases continuam disponíveis.' : 'O áudio é processado pelo servidor e descartado após a transcrição.')}</p>
              {hasTranscription && <div className="review"><label htmlFor="transcription">Revise a transcrição</label>
                <textarea id="transcription" value={transcription} maxLength={MAX_MESSAGE_LENGTH} onChange={event => setTranscription(event.target.value)} />
                {transcription.length > MAX_MESSAGE_LENGTH && <p>Reduza a transcrição para até 5.000 caracteres antes de usar.</p>}
                <button className="primary-button" disabled={!transcription.trim() || transcription.length > MAX_MESSAGE_LENGTH} onClick={useTranscription}><Check size={17} /> Usar na minha mensagem</button>
                <p>Substitui o texto atual. A leitura não começa automaticamente.</p></div>}
            </section>
        </div>
      </main>
      <footer className="footer">{offlineReady ? 'Interface disponível sem conexão' : 'Receptor — apoio ? comunicação'}<span>Sem histórico de mensagens</span></footer>

      <dialog ref={dialog} className="help-dialog" onCancel={() => setHelpOpen(false)} onClose={() => setHelpOpen(false)} aria-labelledby="help-title">
        <button className="close-dialog" aria-label="Fechar ajuda" onClick={() => setHelpOpen(false)}><X size={22} /></button>
        <span className="heading-icon"><House size={25} /></span><h2 id="help-title">Um espaço para sua comunicação.</h2>
        <p><strong>1. Escreva ou escolha uma frase.</strong> Edite sua mensagem e toque em Falar mensagem. A voz depende de uma voz local de português disponível no navegador.</p>
        <p><strong>2. Transforme áudio em texto.</strong> Escolha um WAV mono, 16 kHz, 16 bits, até 30 segundos e 1 MB. Autorize o processamento e revise o resultado antes de usar. A transcrição precisa do servidor conectado.</p>
        <p><strong>3. Leve o Receptor com você.</strong> Use Instalar app quando o navegador oferecer a instalação. No iPhone/iPad, use Compartilhar → Adicionar à Tela de Início. O suporte depende do navegador.</p>
        <p>Após a primeira abertura da versão de produção, a interface pode funcionar sem conexão. A voz usa apenas vozes locais; a transcrição continua dependendo do servidor.</p>
        <div className="help-privacy"><ShieldCheck size={20} /><p>Mensagens e áudios não ficam no histórico do app. Recarregar fecha a mensagem atual. Enviar um áudio para transcrever não autoriza seu uso em treinamento.</p></div>
        <button className="primary-button" onClick={() => setHelpOpen(false)}>Entendi, vamos começar <ArrowRight size={17} /></button>
      </dialog>
    </div>
  )
}

export default App
