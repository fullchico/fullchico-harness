# Modelos por etapa e handoff

## Decisão

O harness configura três papéis personalizáveis por projeto:

1. **Início / planejamento**: conduz entrevista, define requisitos, grafo de tarefas, dependências e critérios de entrega.
2. **Meio / execução**: executa os nós do grafo, inclusive os independentes em paralelo quando houver isolamento adequado.
3. **Revisão**: examina o resultado e os portões aplicáveis, devolvendo pendências ao executor até a entrega ser validada. O autor de uma alteração não aprova a própria alteração.

Cada papel escolhe uma CLI (`claude` ou `codex`) e um modelo. Há também um **modelo de apoio** configurável para continuidade quando o modelo principal não puder prosseguir por limite. Cada portão de agente pode escolher seu próprio modelo revisor em `modelos.portoes`; o fiscal permanece independente de quem executou.

## Três momentos dos portões

Os três papéis de modelo e os três momentos dos portões são conceitos distintos. Os momentos são:

1. **Início**: verifica se entrevista, requisitos, proposta, plano e passaporte da demanda estão prontos antes da execução.
2. **Meio**: acompanha os nós do grafo, suas dependências, evidências e critérios locais; só libera um nó dependente quando os anteriores estiverem válidos. Pode ocorrer em paralelo para tarefas independentes.
3. **Fim**: o revisor independente confere resultado, evidências e todos os carimbos exigidos antes da entrega. Pendências voltam ao meio.

O registro (`.claude/trilho.json`) aceita `inicio`, `meio` e `fim`. O portão de meio é declarado no campo `Meio:` do ticket, validado com `portao <nome> --ticket <caminho>` e carimbado pelo fiscal. O carimbo vincula ticket e estado do código; alterar o resultado invalida a aprovação. Portões de meio aceitam `comando` ou `artefato`.

Um portão final aceita `tentativas` (inteiro não negativo, 3 por padrão) e `aprovacao` (`auto` por padrão, ou `humana`). Reprovações dentro do limite retornam ao executor sem perguntar ao dono. Na reprovação seguinte, o orquestrador faz um handoff para intervenção humana. Se a aprovação humana foi escolhida, o dono assina somente depois da validação técnica com `fullchico-harness portoes --aprovar <nome>`; a assinatura vale para aquele estado do código.

## Espelhos iniciais

| Claude | Codex | Uso no handoff |
| --- | --- | --- |
| Opus | Sol | Continuidade do papel configurado com Opus |
| Sonnet | Luna | Continuidade do papel configurado com Sonnet |
| Haiku | Terra | Continuidade do papel configurado com Haiku |
| Fable | Astra | Continuidade do papel configurado com Fable, caso esse nome esteja disponível na instalação |

Essa tabela é um **dicionário inicial configurável**, não uma afirmação de equivalência de capacidade ou custo. A direção inversa usa o mesmo par. O apoio explícito prevalece sobre o espelho. Hoje `modelos mostrar` verifica a presença da CLI no PATH; a verificação de acesso ao modelo ainda falta.

## Configuração por projeto

`fullchico-harness modelos configurar` apresenta planejamento, execução, revisão e apoio. `fullchico-harness modelos mostrar` exibe a escolha e os espelhos. A configuração fica na chave `modelos` do registro do projeto. O congelamento em manifesto de execução ainda falta.

Exemplo conceitual:

```json
{
  "planejamento": {"cli": "claude", "modelo": "opus"},
  "execucao": {"cli": "codex", "modelo": "luna"},
  "revisao": {"cli": "codex", "modelo": "sol"},
  "apoio": {"cli": "claude", "modelo": "sonnet"}
}
```

## Handoff e limites

Claude e Codex são processos separados quando um papel passa de uma plataforma para outra. O harness entrega um pacote estruturado com ticket, estado do grafo, arquivos e alterações, decisões, evidências, pendências e próximo passo. O destino confirma o recebimento, continua no espaço de trabalho isolado da tarefa e devolve resultado estruturado. Cada passagem registra origem, destino, modelo efetivamente usado e motivo.

Quando a CLI oferece sinal confiável de limite iminente, o harness pode preparar a passagem. Caso contrário, reage ao erro de limite e retoma do último estado persistido. Uma passagem só ocorre depois de registrar um estado consistente; trabalho parcial não recebe carimbo de revisão. Trocar de modelo não dispensa o revisor independente nem os portões finais.

## Estado e próximos passos

- Configuração por projeto e comando interativo ou não interativo: implementados.
- Portões de meio por ticket e validação na entrega: implementados.
- `modelos executar` inicia um papel em Claude ou Codex, resolve os aliases Codex conhecidos,
  salva um manifesto fora do repositório e tenta o apoio quando a CLI retorna erro de limite.
- O executor Codex CLI recebe `workspace-write` e revisão automática. Para Docker e serviços
  locais bloqueados, pede elevação específica ao revisor automático; a política pode negá-la.
  O fiscal mantém leitura; o Claude usa as configurações da sessão ou do projeto em que foi
  aberto. Desligar o sandbox Claude não altera o Codex automaticamente.
- `modelos validar-portao` abre o fiscal independente no modelo configurado para o portão;
  o subagente orquestrador coordena tickets liberados e revisões até a entrega ou intervenção.
- Portões finais têm limite de reprovações e aprovação humana opcionais por projeto.
- Validar acesso aos IDs de modelos antes da execução e mostrar um plano congelado.
- Persistir uma retomada mais detalhada do loop quando a sessão inteira termina no meio de uma demanda.
- Registrar provedor e modelo real nas evidências de revisão; rejeitar carimbo que não corresponda ao manifesto.
- Testar troca por limite, retomada sem duplicar alterações e revisão independente.
