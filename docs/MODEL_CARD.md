# Cartão do modelo — Receptor

## Status

**Não treinado.** Este documento descreve o plano inicial e os campos a preencher após experimentos reais. O repositório contém uma base de desenvolvimento; não contém pesos próprios, dados reais de participantes ou resultados que demonstrem qualidade.

| Campo | Estado atual |
| --- | --- |
| Nome do modelo adaptado | Receptor, nome provisório |
| Tarefa | Reconhecimento de fala para sugestão de texto |
| Idioma inicial | Português do Brasil |
| Modelo base previsto | `openai/whisper-tiny` |
| Versão/revisão exata dos pesos base | Pendente de registro no experimento |
| Versão dos dados e protocolo | Pendente; coleta não iniciada por esta base |
| Checkpoint adaptado | Não produzido |
| Responsável e contato | A definir pela equipe |
| Licenças do modelo base e dos artefatos derivados | Verificar e registrar antes de distribuição |

## Uso pretendido

Apoiar experimentos de transcrição de fala de pessoas com dificuldades de fala, com revisão e confirmação humana. O sistema deve apresentar uma sugestão de texto e permitir correção, cancelamento e uma forma alternativa de comunicação.

A interface principal é uma PWA em React e TypeScript, com texto digitado, frases rápidas e reprodução em voz. A síntese usa `speechSynthesis` do navegador e somente vozes de português identificadas como locais por `localService`, com preferência por pt-BR. Não é um modelo de voz treinado pelo Receptor. Sem uma voz local compatível, o texto e as frases continuam disponíveis e a interface informa a limitação.

A transcrição recebe arquivos WAV por uma API FastAPI Python, com autorização explícita para esse processamento. O servidor local do usuário executa o reconhecimento; o áudio não é enviado a uma API externa de transcrição. A pessoa revisa a sugestão, escolhe **Usar na minha mensagem** e pode corrigir o texto antes de acionar **Falar mensagem**. Não há gravação de microfone nesta versão. A interface ainda precisa de validação de acessibilidade com participantes.

Após o cache do app shell de produção, texto e frases podem funcionar offline. A voz depende do suporte local do navegador; **a transcrição exige o backend acessível**. A PWA não persiste mensagens ou áudios em `localStorage`. O envio para transcrição não inclui o arquivo automaticamente em um conjunto de treinamento.

A janela Tkinter via `receptor app` permanece como ferramenta auxiliar. Sua leitura usa uma voz de português do Windows compatível com `System.Speech`; essa disponibilidade é independente das vozes oferecidas pelo navegador.

O reconhecimento não deve inferir diagnóstico, capacidade cognitiva, identidade ou intenção. O modelo não foi avaliado para decisões clínicas, uso em emergências ou execução automática de ações. Não apresentar suas saídas como certeza sobre o que alguém quis dizer.

## Dados e participação

Ainda não há um conjunto de treinamento do Receptor documentado. Antes de coletar, concluir o processo descrito em [DADOS.md](DADOS.md), com consentimento explícito para os usos previstos e armazenamento privado.

Os arquivos gerados por `receptor demo` contêm tons sintéticos, sem voz humana. Eles exercitam o formato dos dados e os comandos de validação e divisão; não são dados de treinamento ou evidência de qualidade da transcrição.

Após a coleta autorizada, registrar:

- Origem dos áudios, condições de gravação e tarefas escolhidas com participantes.
- Quantidade de participantes, áudios e duração por conjunto.
- Critérios de inclusão, exclusão, transcrição e revisão.
- Representatividade e variações relevantes ao uso, evitando coletar atributos pessoais desnecessários.
- Procedimento de separação, auditoria de duplicatas e limites de retirada dos artefatos treinados.

Pseudônimos não anonimizam a voz. Modelos adaptados podem memorizar informações dos dados; sua publicação exige revisão própria e não decorre automaticamente da autorização para treinamento local.

## Treinamento e reprodução

Arquitetura prevista: adaptação supervisionada de um modelo Whisper pré-treinado usando pares de áudio e texto. A escolha inicial prioriza um experimento pequeno; adequação ao público e ao hardware ainda precisa ser medida.

Após executar, registrar revisão do código, versões das dependências, revisão do modelo base, configuração, sementes aleatórias, estratégia de divisão, duração e hardware. Guardar configurações reproduzíveis sem incluir dados pessoais ou credenciais.

A configuração inicial é `configs/train.toml`, com caminhos relativos à sua própria pasta. O treinamento grava pesos, processador, `run.json`, `trainer_state.json` e `metrics.json` em `artifacts/whisper-receptor`. Há uma avaliação ao final de cada execução, sem escolha automática da melhor época. O `run.json` registra configuração, versões, hashes dos manifestos e revisão do modelo quando disponível; a equipe ainda deve registrar hardware e revisão do código.

| Item | Resultado |
| --- | --- |
| Hardware testado para treinamento | Pendente |
| Hardware testado para inferência | Pendente |
| Duração do treinamento e uso de memória | Pendente |
| Inferência local sem internet após obter os pesos | Pendente de teste; exige backend em execução |
| Checkpoint escolhido e critério | Pendente |

Não há estimativa de desempenho ou garantia de treinamento em uma máquina específica antes desses testes.

## Avaliação

Seguir [AVALIACAO.md](AVALIACAO.md). Comparar modelo original e adaptado no mesmo teste, reservado por participante, usando o mesmo procedimento de transcrição e normalização.

| Evidência | Modelo original | Modelo adaptado |
| --- | --- | --- |
| WER geral e por participante | Pendente | Pendente |
| CER geral e por participante | Pendente | Pendente |
| Latência no dispositivo de uso | Pendente | Pendente |
| Tempo e esforço de correção | Pendente | Pendente |
| Utilidade avaliada com participantes | Pendente | Pendente |

As métricas de uso e de interface precisam de um protocolo de teste com participantes; a CLI de avaliação não as mede automaticamente.

A verificação da PWA deve distinguir disponibilidade offline do app shell, suporte às vozes locais e disponibilidade do backend de transcrição. Testes automatizados da API ou da interface não demonstram qualidade do modelo, utilidade ou acessibilidade para o público.

## Limitações e riscos conhecidos

- O modelo base pode ter desempenho desigual em variedades de fala, sotaques, ritmos, volumes e ambientes. A adaptação pode melhorar algumas situações e piorar outras.
- Ruído, silêncio, gravações cortadas ou fala fora das condições avaliadas podem produzir texto incorreto ou sem correspondência com o áudio.
- Uma transcrição plausível pode mudar negações, nomes, números ou a mensagem pretendida. Confirmação e correção acessíveis são requisitos do produto.
- Resultados de poucos participantes não representam todas as pessoas com dificuldades de fala.
- A divisão por participante não demonstra desempenho de personalização individual; essa abordagem requer sessões separadas e avaliação própria.
- Instalação da PWA e vozes locais variam entre navegadores e sistemas. A transcrição fica indisponível quando o backend não pode ser acessado, mesmo com a interface em cache.
- Excluir gravações não desfaz automaticamente o aprendizado. Retenção, retirada e eventual novo treinamento precisam ser definidos previamente.

## Condição para disponibilização

Qualquer futura publicação deve registrar versão, avaliação, limitações, autorizações aplicáveis, licença e canal de retorno. Antes disso, o modelo adaptado permanece um artefato experimental privado. A disponibilização de uma interface também exige teste de acessibilidade e confirmação com as pessoas que irão utilizá-la.
