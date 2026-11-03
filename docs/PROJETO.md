# Receptor: plano do projeto

O Receptor apoia a comunicação de pessoas com dificuldades de fala. O primeiro
protótipo combina **fala para texto revisável** e **texto ou frases rápidas para voz**,
com foco em português do Brasil.

A interface principal é uma **PWA em React e TypeScript**. O **backend Python com
FastAPI** executa a transcrição; o treinamento e a avaliação continuam na CLI Python.
Não existe ainda um modelo Receptor treinado com participantes ou evidência de eficácia.
O protótipo precisa ser avaliado com as pessoas que irão utilizá-lo.

## Construir com os participantes

Dificuldades de fala abrangem experiências diferentes. Algumas pessoas se beneficiam
de reconhecimento; outras preferem comunicação aumentativa e alternativa (CAA),
como digitar ou selecionar frases. O produto deve permitir combinar as opções.

Antes de coletar gravações, definir com participantes, em formatos acessíveis:

- Situações em que a ferramenta pode ajudar e recursos já utilizados.
- Preferências de entrada, navegação, tamanho de controles e saída de voz.
- Como revisar, corrigir, cancelar e confirmar uma mensagem.
- Dados que aceitam registrar, finalidade, acesso e prazo de guarda.
- Critérios práticos para decidir se vale continuar.

A participação deve ser voluntária. Planejar tempo, apoio e eventual remuneração com
as pessoas envolvidas. Profissionais de acessibilidade e fonoaudiologia podem contribuir;
a pessoa que se comunica continua responsável por aprovar sua mensagem.

## Arquitetura inicial

```text
PWA — frontend/ — React, TypeScript e Vite
  ├─ texto ou frase rápida → revisão → speechSynthesis com voz local pt
  └─ WAV + autorização explícita → POST /api/transcriptions
                                      ↓
                               FastAPI + Whisper
                                      ↓
                           sugestão de texto revisável

Python — src/receptor/
  ├─ GET /api/health
  ├─ POST /api/transcriptions
  ├─ /docs: documentação da API
  └─ CLI: validar, separar, treinar, transcrever e avaliar
```

A PWA usa apenas vozes de português que o navegador identifica como locais por
`localService`. O suporte depende do navegador, sistema e vozes disponíveis. Sem uma
voz local compatível, a interface informa a indisponibilidade e mantém o texto e as
frases. O produto não deve escolher automaticamente um serviço remoto para ler mensagens.

A transcrição usa arquivos WAV de até 30 segundos, mono, PCM 16 bits e 16 kHz.
Ela exige autorização explícita para o processamento e um backend acessível.
Esta versão não grava pelo microfone. A confirmação do envio para transcrever não
autoriza automaticamente incluir o áudio em treinamento.

O backend processa o áudio com Whisper localmente. O primeiro uso de um modelo público
obtém seus pesos; não há envio do áudio para uma API externa de reconhecimento.
Um resultado deve ser tratado como sugestão: o modelo pode errar ou produzir palavras
sem correspondência com o áudio. Não completar intenções nem disparar ações automaticamente.

## Offline, instalação e execução

Em produção, o app shell pode ficar em cache após o primeiro acesso. Texto e frases
rápidas continuam disponíveis offline; síntese depende de uma voz local compatível.
A transcrição continua dependendo do backend. Áudios e mensagens não são persistidos
em `localStorage`; o cache da PWA guarda arquivos da interface.

No desenvolvimento, Vite atende na porta 5173 e encaminha `/api` ao Python na porta 8000.
Após `npm --prefix frontend run build`, o FastAPI serve `frontend/dist` na raiz quando
essa pasta existe. `/api` e `/docs` continuam disponíveis. O funcionamento offline e a
instalação devem ser verificados na versão de produção, em um navegador compatível.

Os comandos completos estão no [README](../README.md). A execução inicial é local,
em `127.0.0.1`. Disponibilizar o serviço para outros dispositivos exige configuração
própria de hospedagem, HTTPS e acesso; não faz parte da inicialização local.

A janela Tkinter permanece como ferramenta auxiliar via `receptor app`, com
`--model` e `--language` opcionais. Sua leitura usa uma voz de português do Windows
compatível com `System.Speech`. Ela não substitui a PWA como interface principal.

## Primeiro ciclo de dados e modelo

1. **Definir a tarefa com participantes.** Escolher situações e critérios de sucesso.
2. **Concluir o protocolo de dados.** Preparar consentimento, armazenamento, acesso e retirada antes da coleta. Ver [DADOS.md](DADOS.md).
3. **Medir o modelo original.** Usar a validação para obter uma referência durante o desenvolvimento.
4. **Adaptar em pequena escala.** Treinar somente com o conjunto de treino e comparar versões na validação.
5. **Congelar uma versão.** Comparar original e adaptado no mesmo teste reservado, sem ajustar decisões com base nele.
6. **Avaliar o uso.** Medir compreensão, correções, tempo de resposta e autonomia com participantes.

A separação automática mantém cada pessoa em apenas um conjunto e exige pelo menos
três participantes. Isso permite executar a divisão, mas não demonstra representatividade.
A implementação avalia ao final de cada treinamento; a equipe escolhe entre execuções,
sem seleção automática da melhor época.

Não existe uma quantidade universal de horas que garanta qualidade. Necessidade de dados,
memória, GPU e latência depende da tarefa e deve ser medida. Para personalizar um modelo
para uma pessoa, será necessário um protocolo por sessões; a divisão atual não o implementa.

## Entregas e critérios

| Entrega | Evidência para concluir |
| --- | --- |
| Protocolo de participação e dados | Finalidade, autorizações, acesso e retirada compreendidos pelos participantes |
| PWA acessível | Pessoa consegue navegar, editar, revisar e confirmar com sua forma de entrada |
| Funcionamento offline | Texto e frases disponíveis após cache, com indisponibilidade do backend comunicada |
| Primeiro conjunto autorizado | Áudios revisados, manifesto válido e origem documentada |
| Referência e adaptação | Comparação reproduzível, por participante, sem vazamento entre conjuntos |
| Decisão de continuidade | Utilidade observada, esforço aceitável e limitações registradas |

Testes automatizados de código e uma interface que abre no navegador não comprovam
acessibilidade. Planejar testes com teclado, tecnologias assistivas e os dispositivos
do público. Verificar separadamente vozes locais, instalação da PWA e retorno após perda
de conexão.

Registrar resultados reais em [AVALIACAO.md](AVALIACAO.md) e
[MODEL_CARD.md](MODEL_CARD.md). Manter gravações, transcrições e artefatos de treinamento
em armazenamento privado. Publicação e ampliação do piloto dependem das autorizações
aplicáveis e de evidência de utilidade.
