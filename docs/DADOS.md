# Dados de fala

Comece pelo protocolo de participação, não pelas gravações. Voz e transcrições podem identificar pessoas ou revelar informações pessoais. Um identificador como `p001` é um pseudônimo: ele não torna a gravação anônima.

## Antes de coletar

Preparar um registro de consentimento acessível que explique finalidade, dados coletados, usos de treinamento e avaliação, pessoas com acesso, prazo de guarda e contato para dúvidas ou retirada. Definir separadamente se haverá compartilhamento de dados ou publicação de modelos. Uma autorização para um uso não deve ser presumida como autorização para todos os outros.

O projeto ainda não fornece um formulário de consentimento pronto para uso. Esse documento e o processo de participação precisam ser construídos e revisados antes da coleta real. Considerar necessidades de apoio à comunicação e regras específicas caso a participação envolva crianças ou outras situações que exijam procedimentos adicionais.

No manifesto, `consent: true` significa que **uma autorização válida para esse uso já foi registrada fora do repositório**. Esse campo não solicita consentimento, não comprova sozinho sua validade e não substitui o registro. Não marcar como verdadeiro para contornar a validação.

## Armazenamento

- Manter gravações, transcrições, divisões de dados e resultados individuais em armazenamento local privado, fora do Git e de pastas compartilhadas automaticamente.
- Proteger o dispositivo e limitar o acesso às pessoas responsáveis pelo trabalho. A base Python não oferece por si só controle de acesso ou criptografia dos arquivos.
- Guardar o vínculo entre identidade, pseudônimo e consentimento separado dos áudios e manifestos.
- Registrar origem, finalidade autorizada, responsáveis, prazo de retenção e versões dos conjuntos em controle privado.
- Tratar modelos adaptados, checkpoints e relatórios individuais como artefatos potencialmente sensíveis. Ignorar um arquivo no Git não remove cópias já publicadas ou incluídas no histórico.

Planejar retirada de consentimento e exclusão também para cópias e backups. Apagar uma gravação não remove automaticamente sua influência de um modelo já treinado. A equipe deve explicar esse limite antes da coleta e definir se precisará descartar checkpoints ou treinar novamente. Não prometer remoção completa de um modelo sem um procedimento demonstrável.

## Manifesto JSONL

Cada linha é um objeto JSON, salvo em UTF-8. O exemplo a seguir é apenas ilustrativo; o áudio citado não vem com o projeto.

```json
{"audio":"../audio/p001_001.wav","text":"Preciso de água.","speaker_id":"p001","consent":true}
```

| Campo | Conteúdo |
| --- | --- |
| `audio` | Caminho de um áudio WAV. Caminhos relativos são resolvidos a partir da pasta do manifesto. |
| `text` | Transcrição de referência, não vazia, revisada por uma pessoa. |
| `speaker_id` | Pseudônimo consistente para a mesma pessoa, sem nome, e-mail ou documento. |
| `consent` | Booleano `true`, somente quando a autorização correspondente já está registrada. |

Formato de áudio aceito nesta base: **WAV PCM de 16 bits, mono, 16.000 Hz, duração maior que zero e de até 30 segundos**. Converter o arquivo para esse formato não corrige uma gravação de baixa qualidade.

Uma organização possível, com arquivos reais mantidos privados:

```text
data/
  audio/
    p001_001.wav
  manifests/
    corpus.jsonl
  splits/
    train.jsonl
    validation.jsonl
    test.jsonl
```

Execute a validação antes de separar os dados:

```powershell
receptor validate data/manifests/corpus.jsonl
receptor split data/manifests/corpus.jsonl --output-dir data/splits
```

## Exercício sem dados pessoais

O comando abaixo cria arquivos de demonstração para praticar a estrutura do conjunto, a validação e a separação:

```powershell
receptor demo --output-dir data/demo
receptor validate data/demo/manifest.jsonl
receptor split data/demo/manifest.jsonl --output-dir data/demo/splits
```

Os áudios da demonstração são **tons sintéticos, não fala humana**. Os identificadores representam participantes fictícios. Esses arquivos servem somente para exercitar o fluxo de arquivos e não permitem treinar ou avaliar reconhecimento de fala de forma significativa. A marcação de consentimento usada nesse exercício não substitui o processo exigido para dados reais. Os comandos preservam arquivos de saída já existentes; em caso de conflito, escolha outro diretório.

## Transcrição e qualidade

A referência deve descrever o áudio, não aquilo que o anotador imagina que a pessoa quis dizer. Definir uma convenção consistente para hesitações, repetições, pontuação, números e palavras incompreensíveis. Não corrigir silenciosamente gramática nem completar conteúdo ausente. Discutir a convenção com os participantes e documentá-la junto à versão privada do conjunto.

Quando não for possível estabelecer uma referência confiável, separar o trecho para revisão. Não colocar marcadores de dúvida no alvo de treinamento sem um protocolo deliberado: o modelo pode aprender a reproduzi-los. Sempre que possível, permitir que a própria pessoa confira a referência.

Verificar cortes de palavras, silêncio, ruído, sobreposição de vozes e divergências entre áudio e texto. Remover ou revisar gravações sem autorização, duplicadas ou contendo terceiros sem o procedimento previsto. Manter condições variadas relevantes ao uso real, sem confundir variação legítima de fala com erro no dado.

## Separação dos conjuntos

A separação automática exige **pelo menos três participantes distintos** e mantém cada participante em apenas um dos conjuntos: `train`, `validation` ou `test`. Ela estima desempenho em pessoas não vistas no treino. Três participantes permitem executar a divisão, mas não constituem por si só evidência suficiente de qualidade ou representatividade.

O algoritmo usa uma semente fixa por padrão e distribui participantes; não garante equilíbrio de duração ou de condições de fala. A validação rejeita áudios com conteúdo PCM idêntico, mesmo que o nome do arquivo ou os metadados WAV sejam diferentes. O treinamento também verifica participantes e gravações compartilhados entre treino e validação.

Não mover trechos da mesma pessoa entre conjuntos para melhorar números. Auditar também arquivos duplicados, versões recortadas e gravações compartilhadas, pois pseudônimos diferentes não garantem independência. Verificar o conteúdo dos manifestos depois da divisão; caminhos relativos de cada manifesto devem continuar apontando para os áudios corretos.

Para um futuro modelo personalizado para uma única pessoa, o problema é diferente: separar sessões e momentos de coleta, reservando sessões futuras para avaliação. Essa estratégia **ainda não é implementada pela divisão automática** e não deve ser simulada dando pseudônimos diferentes à mesma pessoa.

Ver [AVALIACAO.md](AVALIACAO.md) para o uso correto de cada conjunto e [MODEL_CARD.md](MODEL_CARD.md) para o registro do modelo resultante.
