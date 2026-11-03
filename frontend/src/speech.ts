export function localPortugueseVoices(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  return voices.filter(voice => voice.localService && /^pt(?:-|_|$)/i.test(voice.lang))
    .sort((a, b) => Number(/^pt[-_]BR$/i.test(b.lang)) - Number(/^pt[-_]BR$/i.test(a.lang)))
}

export const MAX_MESSAGE_LENGTH = 5000
