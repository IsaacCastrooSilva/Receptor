# Avaliação do Receptor

O objetivo é verificar se o Receptor ajuda a pessoa a se comunicar com menos esforço. Uma melhora na transcrição automática é uma evidência útil, mas não demonstra sozinha acessibilidade, utilidade ou eficácia clínica.

## Comparação inicial

Durante o desenvolvimento, comparar o modelo original e o modelo adaptado na validação. Depois de escolher a versão final, comparar ambos nos **mesmos áudios de teste**, com idioma, opções de decodificação, preparação do áudio e normalização do texto equivalentes. Registrar qualquer diferença necessária entre as execuções.

- **Treino:** dados usados para atualizar os parâmetros.
- **Validação:** dados usados para escolher parâmetros de treinamento, checkpoints e outras decisões.
- **Teste:** dados reservados para avaliar uma versão já escolhida.

Não escolher a melhor versão repetindo ajustes sobre o teste. Se os resultados do teste passarem a orientar o desenvolvimento, será necessário reservar dados independentes para a próxima avaliação final.

A divisão automática por participante avalia generalização para pessoas não vistas no treino. Personalização individual é uma pergunta diferente e exige sessões independentes; não está coberta por essa divisão.

## Métricas de transcrição

| Métrica | O que informa | Limite |
| --- | --- | --- |
| WER | Erros de substituição, exclusão e inserção de palavras divididos pelo número de palavras da referência | Não mede diretamente compreensão ou utilidade; pode exceder 100% |
| CER | A mesma contagem de erros em caracteres, dividida pelo número de caracteres da referência | Pequenas diferenças de escrita podem pesar sem mudar a mensagem |
| Resultados por participante | Como o desempenho se distribui entre as pessoas avaliadas | Amostras pequenas podem ser muito instáveis |

Reportar WER e CER agregados sobre as referências do conjunto e também por participante. Não confundir a taxa calculada pela soma dos erros e unidades com a média simples das taxas de cada áudio. Se calcular uma média por participante, nomeá-la explicitamente e informar os denominadores.

Registrar o número de participantes, áudios e duração total de cada conjunto. Documentar a normalização aplicada, incluindo caixa, pontuação, acentos e números. Usar a mesma regra no modelo original e no adaptado; não mudar a regra depois de ver o resultado para melhorar a pontuação.

A implementação atual devolve WER e CER como frações: `0.20` representa 20%. Calcula taxas agregadas sobre todas as referências e por participante. A normalização aplica Unicode NFC e minúsculas, troca pontuação por espaços e reduz espaços repetidos. Preserva acentos, números e outros símbolos; o CER conta os espaços normalizados. `receptor validate` informa a duração total do conjunto.

Inspecionar erros que alterem a mensagem, como negação, nomes ou quantidades, com referências aprovadas e dados autorizados. A taxa global pode ocultar falhas importantes ou piora para alguns participantes.

## Executar a avaliação

Após seguir a instalação no [README](../README.md) e preparar dados autorizados, medir a referência na validação e treinar:

```powershell
receptor evaluate data/splits/validation.jsonl --model openai/whisper-tiny --output artifacts/baseline-validation.json
receptor train --config configs/train.toml
receptor evaluate data/splits/validation.jsonl --model artifacts/whisper-receptor --output artifacts/adapted-validation.json
```

Os caminhos do TOML são relativos à pasta do arquivo de configuração. A configuração inicial lê `data/splits/train.jsonl` e `data/splits/validation.jsonl` e salva em `artifacts/whisper-receptor`. O treinamento avalia a validação uma vez ao final, sem selecionar automaticamente a melhor época. Usar um diretório de saída novo para cada experimento e nomes novos para relatórios já existentes.

Quando as escolhas estiverem concluídas, avaliar no teste reservado:

```powershell
receptor evaluate data/splits/test.jsonl --model openai/whisper-tiny --output artifacts/baseline-test.json
receptor evaluate data/splits/test.jsonl --model artifacts/whisper-receptor --output artifacts/adapted-test.json
```

Os comandos com `artifacts/whisper-receptor` pressupõem que o treinamento já produziu um modelo nesse diretório. Não há resultado de treinamento com participantes ou pontuação de reconhecimento fornecidos com esta base.

Os relatórios de avaliação incluem quantidades e WER/CER gerais e por participante, mas não referências nem transcrições geradas. Tratar os resultados individuais como dados privados. Se a equipe produzir registros adicionais com textos para inspecionar erros, revisar seu conteúdo e autorizações antes de compartilhar; trocar nomes por pseudônimos não basta para anonimizar transcrições.

## Teste de uso com participantes

Estas medidas devem ser planejadas para a PWA, interface principal do protótipo, e complementam a avaliação pela CLI:

- **Utilidade:** a pessoa conseguiu comunicar a mensagem que queria? O destinatário a compreendeu após a confirmação?
- **Correção:** quantas intervenções foram necessárias e quanto tempo ou esforço elas exigiram?
- **Latência:** nesta versão, tempo entre acionar **Transcrever áudio** e aparecer uma sugestão, tempo até a mensagem confirmada e demora para iniciar a voz após **Falar mensagem**. Em uma futura gravação pelo microfone, medir também a espera desde o fim da fala.
- **Autonomia:** a pessoa conseguiu iniciar, revisar, cancelar e confirmar usando a forma de entrada de sua preferência?
- **Preferência e conforto:** a experiência foi melhor que o recurso já utilizado naquela situação?

Medir no dispositivo e nas condições de uso previstos. Registrar sistema, processador, GPU quando houver, memória, versão do modelo e duração do áudio. Distinguir download e carregamento inicial do tempo das transcrições seguintes. A avaliação funcional não deve exigir divulgar mensagens pessoais para a equipe.

Para a PWA, registrar também navegador, voz local disponível, forma de entrada e conexão com o backend Python. Testar o app shell offline separadamente: texto e frases podem permanecer disponíveis, mas a transcrição exige acesso ao backend. A síntese deve usar apenas vozes locais de português; não presumir que uma voz disponível em um aplicativo Windows também esteja disponível no navegador.

## Critérios para avançar

Definir critérios com os participantes antes da comparação. Não estabelecer um WER universal como requisito de utilidade, nem considerar apenas a média do grupo. Uma melhora agregada com piora para determinadas pessoas deve ser investigada e registrada.

Antes de ampliar um piloto, obter evidência de revisão e confirmação acessíveis, tempo de resposta aceitável para o contexto, utilidade observada e um procedimento de correção e retirada de dados. Se o reconhecimento não atender uma pessoa, considerar outras formas de comunicação no produto.

Atualizar [MODEL_CARD.md](MODEL_CARD.md) com resultados reais, versão dos dados, limitações e decisões. Manter os campos pendentes enquanto não houver evidência.
