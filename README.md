<img src="site/trem.svg" alt="" width="72" align="right">

# FullChico Harness

[![npm](https://img.shields.io/npm/v/@fullchico/harness?label=npm&color=1d1b16)](https://www.npmjs.com/package/@fullchico/harness)
[![ci](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml)

[Página do projeto](https://fullchico.github.io/fullchico-harness/) · [Pacote no npm](https://www.npmjs.com/package/@fullchico/harness)

```bash
npx @fullchico/harness install .
```

Um plugin para o Claude Code que troca instrução por trilhos e portões (hooks, guards e
scripts), para que agentes levem uma mudança da entrevista ao pull request sem que nada
chegue ao remoto sem revisão independente.

## Sumário

- [O conceito](#o-conceito)
- [Como é usar](#como-é-usar)
- [A entrevista](#a-entrevista)
- [Quem faz o quê](#quem-faz-o-quê)
- [Os portões](#os-portões)
- [O que é recusado por máquina](#o-que-é-recusado-por-máquina)
- [O que é instalado e o que é exigido](#o-que-é-instalado-e-o-que-é-exigido)
- [Instalar num projeto](#instalar-num-projeto)
- [Comandos](#comandos)
- [Configuração](#configuração)
- [Arquitetura que o harness espera](#arquitetura-que-o-harness-espera)
- [Ambiente por feature](#ambiente-por-feature)
- [Memória do projeto](#memória-do-projeto)
- [Projeto sem remoto](#projeto-sem-remoto)
- [Atualizar o harness](#atualizar-o-harness)
- [O que já foi provado e o que ainda não](#o-que-já-foi-provado-e-o-que-ainda-não)
- [Desenvolver o harness](#desenvolver-o-harness)
- [Licença](#licença)

## O conceito

Uma instrução escrita num arquivo é texto, e texto o agente interpreta: ele pode ler de outro
jeito, esquecer no meio de uma sessão longa ou decidir que aquele caso é exceção. Um trilho
é diferente: é um hook, um guard ou um script que confere a regra e recusa o que não passa.
O agente não precisa concordar com ele, e não tem como atravessá-lo.

O harness aplica essa ideia ao ciclo inteiro de uma mudança. O que pode ser conferido por
máquina é conferido por máquina; o texto fica só para o que exige julgamento.

<img src="site/img/fluxo.svg" alt="Fluxo de uma entrega: pedido, entrevista, spec, revisão da spec, tickets, implementação em paralelo, integração, checagem, revisão e envio, com os portões entre as etapas">

São três princípios:

1. **Quem escreve não aprova.** Revisão no mesmo contexto não é revisão. Todo revisor é um
   subagente de contexto novo, que recebe só ponteiros para os documentos e para o diff, sem
   a conversa nem a opinião de quem escreveu. A aprovação é gravada por um hook, a partir do
   veredito do revisor, num lugar onde o agente não escreve.
2. **Nada sai sem os portões.** O shell do agente roda no sandbox do Claude Code, sem rede
   para o servidor de git. O único caminho até o remoto é `.harness/push`, que exige quatro
   vereditos sobre o commit do topo da branch.
3. **Paralelismo por contrato e posse de arquivo.** Cada ticket é dono de pastas (`Owns:`).
   Dois tickets que rodam ao mesmo tempo nunca possuem o mesmo caminho, o ticket de contrato
   fecha antes de todos os outros, e a integração recusa a branch que mexer fora da posse.

## Como é usar

O loop é: pedido curto, entrevista, pronto. Você abre um worktree para a feature, faz o
pedido numa sessão do Claude Code dentro dele e responde à entrevista. O resto corre sem você.

```text
/harness:entregar quero um sistema de agendamento para uma barbearia
```

O que acontece em cada etapa:

| Passo | O que acontece | Quem faz |
|---|---|---|
| 1. Entrevistar | perguntas até não sobrar decisão em aberto; o vocabulário vai para o `GLOSSARY.md` e as decisões difíceis de reverter viram ADRs | a sua sessão, com você |
| 2. Especificar | a spec é escrita em `docs/specs/<slug>/spec.md` e entra em commit | a sua sessão |
| 3. Revisar a spec | um revisor de contexto novo lê a spec como quem vai implementá-la sem poder perguntar, e aponta o que falta | `revisor-spec` |
| 4. Fatiar | um arquivo por ticket em `docs/specs/<slug>/issues/`, com o que o bloqueia e o que ele possui | `orquestrador` |
| 5. Implementar | os tickets da fronteira do grafo rodam em paralelo, cada um num worktree próprio, com TDD | `implementador` |
| 6. Integrar | cada ticket passa pela caça a bugs e só então é juntado à branch da feature, um por vez | `revisor-bugs` e `.harness/integrate` |
| 7. Checar | a checagem completa do projeto, sem custo de IA | `.harness/validate` |
| 8. Revisar | quatro vereditos, em paralelo, sobre o mesmo commit | `seguranca`, `revisor`, `revisor-bugs`, `qualidade` |
| 9. Enviar | push, pull request, e o aplicativo deixado de pé | `.harness/push` e `.harness/pr` |

A entrega tem duas metades de propósito. O **desenho** (passos 1 a 3) acontece na sua sessão,
onde o raciocínio mais caro paga e onde você participa. A **execução** (passos 4 em diante) é
entregue a um subagente `orquestrador`, em modelo mais barato, que recebe só o caminho da
spec: o que ficou só na conversa não chega até ele.

No fim, o relato traz o link do pull request, o endereço do aplicativo que ficou rodando (com
o usuário de teste e como parar), o que entrou, o que ficou de fora, quantas rodadas de
correção houve e as decisões tomadas sem você. Depois do merge, `/harness:aprender` fecha o
ciclo.

### Quando você é chamado

| Parada | Quando |
|---|---|
| A entrevista | sempre, no começo |
| Aprovar a spec (PARADA 1) | depois da revisão da spec: você resolve cada achado e aprova |
| Um ticket que não fecha (PARADA 2) | só se um ticket não fechar em 3 rodadas de correção |
| Remover um ambiente | `.harness/destroy` apaga dados, então sempre pergunta |
| Instalar uma skill nova | `.harness/skills-add` pergunta a cada skill |
| O merge | sempre seu, preservando os commits, sem squash |

Todo o resto roda sem pergunta: os comandos dentro do sandbox e os scripts do harness. Se
quiser alguma pergunta de volta, acrescente a regra em `permissions.ask` num fragmento do
projeto (`harness.d/settings.json`); pergunta vence liberação.

### Seguir sem você

Se você disser "segue até o fim" (ou "pode seguir com o recomendado", "confio na sua análise"),
a entrega passa a correr em modo autônomo, e continua assim até você dizer o contrário:

- toda pergunta recebe a resposta recomendada, na entrevista e nos achados do revisor da spec;
- a aprovação da spec deixa de ser uma parada;
- cada decisão tomada sem você fica escrita na spec, na seção "Decisões tomadas sem o dono",
  com o que foi escolhido, a alternativa descartada e o motivo.

O que continua parando: remover um ambiente, um ticket que não fecha em 3 rodadas, uma
decisão que depende de um dado que só você tem, e o merge. O modo autônomo não muda os
portões, as revisões nem o sandbox.

### Quando o pedido é um bug

Bug entra pela skill `diagnosing-bugs` no lugar da entrevista. Não há spec nem tickets: a
própria sessão corrige, com teste, em commits `fix`, e depois passa pela mesma checagem,
pelos mesmos revisores e pelo mesmo envio.

## A entrevista

A entrevista (grilling) é uma sequência de perguntas ao dono, até não sobrar decisão em
aberto. Ela vem antes de qualquer código porque quem executa não tem a quem perguntar: o
orquestrador e os implementadores nascem sem a conversa e trabalham só com o que está nos
documentos. Uma decisão que ficou de fora da spec vira um ticket reaberto no meio da entrega,
e uma rodada perdida para todos os que dependem dele.

<img src="site/img/entrevista.svg" alt="A entrevista: o pedido curto vira perguntas ao dono, e delas saem o glossário, os ADRs e a spec, que é revisada antes da execução">

Quem faz são skills do plugin de terceiros `mattpocock-skills`:

| Skill | Para quê |
|---|---|
| `grilling` | conduz a entrevista com o dono |
| `domain-modeling` | registra o vocabulário no `GLOSSARY.md` e as decisões difíceis de reverter em ADRs (`docs/adr/`) |
| `diagnosing-bugs` | substitui a entrevista quando o pedido é um bug |

O que sai da entrevista é a spec, escrita para alguém que vai implementar sem ter visto a
conversa. As seções dela:

| Seção | O que traz |
|---|---|
| Problema e Solução | o que incomoda hoje e o que passa a acontecer, do ponto de vista de quem usa |
| Histórias | lista numerada, cobrindo casos de erro e estados vazios, não só o caminho feliz |
| Decisões de implementação | módulos que nascem ou mudam, contratos, mudanças de esquema, e cada escolha da entrevista com o motivo |
| Decisões de teste | os pontos de costura: por onde cada comportamento é testado |
| Critérios de aceite | numerados; cada um vira um teste de ponta a ponta |
| Módulos e contrato | os módulos do back e as fatias do front, cada um com a sua pasta (daqui sai a posse de cada ticket); as operações entre front e back; o que cada módulo oferece e consome dos outros |
| Ambiente e execução | os serviços de que os testes dependem, como os implementadores se isolam e, em projeto novo, o conteúdo do `harness.conf` |
| Fora de escopo | o que não entra, dito com todas as letras |

Antes da execução, a spec é revisada pelo `revisor-spec`, um subagente que não recebe nada da
conversa. Ele procura premissa não declarada, requisito ambíguo, decisão que falta, módulo
que depende de outro sem contrato, nome fora da língua do código, teste sem ponto de costura,
conflito com o glossário ou com um ADR, e risco de implementação. Ele não dá veredito nem
reescreve a spec: quem resolve os achados e aprova é o dono (ou a própria sessão, no modo
autônomo).

## Quem faz o quê

Três papéis:

- **Elefante:** o agente raiz da sessão. Carrega o contexto e desenha com o dono: entrevista
  e spec. Entrega a execução ao orquestrador e não revisa o que orquestrou.
- **Goldfish:** todo subagente. Nasce sem a conversa, entrega o trabalho e não valida o
  próprio resultado.
- **Dono:** você. Aprova a spec e faz o merge.

<img src="site/img/papeis.svg" alt="Os papéis: o dono e a sessão desenham; o orquestrador conduz a execução; implementadores escrevem; revisores de contexto novo dão os vereditos">

Os oito agentes do plugin:

| Agente | Modelo | O que faz | O que recebe | O que não pode |
|---|---|---|---|---|
| `orquestrador` | Sonnet | executa a spec aprovada: fatia, despacha, integra, checa, passa pelos revisores e envia | `spec`, `leitura` | escrever o código da feature, revisar o que orquestrou, juntar branch à mão, perguntar ao dono |
| `implementador` | Haiku (Sonnet no ticket de contrato) | implementa um ticket, com TDD, num worktree próprio | `spec`, `ticket`, `leitura`, `achado` | mexer fora do `Owns:`, subir ou parar ambiente, enviar, abrir pull request |
| `revisor-spec` | o da sua sessão | lê a spec como quem vai implementá-la sem poder perguntar | `spec`, `leitura` | editar arquivos, dar veredito, propor a solução |
| `revisor-bugs` | Sonnet | caça defeito: por ticket antes de integrar, e na branch inteira antes do push | `spec`, `ticket`, `diff`, `commit`, `leitura`, `achado` | editar, corrigir, trocar o commit do worktree |
| `revisor-ambiente` | Opus | só no ticket de contrato: confere que o que ele monta funciona numa cópia limpa | `spec`, `ticket`, `diff`, `commit`, `leitura`, `achado` | editar, corrigir, trocar o commit do worktree |
| `seguranca` | Sonnet | revisão de segurança da branch inteira | `diff`, `commit`, `spec`, `leitura` | editar, corrigir, reprovar por estilo ou risco hipotético |
| `revisor` | Sonnet | revisão de código: padrões do repositório, aderência à spec, arquitetura e clareza | `diff`, `commit`, `spec`, `leitura` | editar, corrigir |
| `qualidade` | Haiku | roda a checagem completa no commit e atesta o resultado | `commit` | revisar, opinar, consertar, rodar de novo "para ver se passa" |
| `revisor-visual` | Opus | só em projeto com `SCREENS_DIR`: abre cada captura de tela do commit e julga o que vê | `diff`, `commit`, `spec`, `leitura` | editar, corrigir, aprovar pelo código sem abrir a imagem, reprovar por gosto |

Uma rodada de correção de um ticket sobe de modelo: vai em Sonnet e, depois de duas
reprovações, em Opus. Se o projeto tem um agente próprio em `.claude/agents/` cuja descrição
cobre a área do ticket, ele é usado no lugar do `implementador`.

O pedido a qualquer um desses agentes só aponta, uma chave por linha (`spec:`, `ticket:`,
`diff:`, `commit:`, `leitura:`, `achado:`). Narrativa e opinião são recusadas por um hook: o
documento é a única interface, e uma lacuna se corrige no documento, não por fora.

```mermaid
sequenceDiagram
    actor Dono
    participant Sessao as Sessão (elefante)
    participant RS as revisor-spec
    participant Orq as orquestrador
    participant Impl as implementadores
    participant Rev as revisores
    participant Remoto

    Dono->>Sessao: /harness:entregar pedido
    Sessao->>Dono: entrevista (grilling)
    Sessao->>Sessao: spec em commit
    Sessao->>RS: spec
    RS-->>Sessao: achados
    Sessao->>Dono: PARADA 1, aprovar a spec
    Sessao->>Orq: spec aprovada
    Orq->>Orq: fatia em tickets e valida o grafo
    loop cada onda do grafo
        Orq->>Impl: tickets da fronteira, em paralelo
        Impl-->>Orq: branch de cada ticket
        Orq->>Rev: revisor-bugs por ticket
        Rev-->>Orq: veredito
        Orq->>Orq: .harness/integrate, um ticket por vez
    end
    Orq->>Orq: .harness/validate --profile merge
    Orq->>Rev: seguranca, revisor, revisor-bugs e qualidade
    Rev-->>Orq: quatro vereditos sobre o mesmo commit
    Orq->>Remoto: .harness/push e .harness/pr
    Orq-->>Sessao: relato
    Sessao-->>Dono: link do PR e endereço do aplicativo
    Dono->>Remoto: merge
```

## Os portões

<img src="site/img/portoes.svg" alt="Os portões: revisão por ticket antes de integrar, checagem completa, e os quatro vereditos sobre o commit do topo antes do push">

### Os quatro vereditos sobre o commit

Nada sai da máquina sem quatro aprovações sobre o commit do topo da branch:

| Veredito | Quem dá | O que atesta |
|---|---|---|
| segurança | `seguranca` | sem segredo, injeção, autorização ausente, dado sensível exposto, dependência duvidosa ou guardrail desligado no diff da branch |
| revisão de código | `revisor` | o código segue os padrões do repositório, a spec e a arquitetura |
| caça a bugs | `revisor-bugs` | o passe final sobre a branch inteira: o que só aparece olhando os módulos juntos |
| qualidade | `qualidade` | a checagem completa do projeto (testes, fronteiras, build, ponta a ponta) passou naquele commit |

Em projeto com tela (o `harness.conf` define `SCREENS_DIR`) há um quinto, o visual: o
`revisor-visual` abre cada captura de tela que a suíte de ponta a ponta tirou naquele commit, no
celular e no computador, e reprova o que está quebrado na tela renderizada. Sem a chave, nada muda.

Todo revisor termina a resposta com um bloco fixo:

```text
VEREDITO: APPROVED   (ou REJECTED)
COMMIT: <hash completo do commit revisado>
RESUMO: <uma linha>
```

Um hook lê esse bloco e grava a aprovação, e só quando o commit revisado é o topo atual.
Nenhum agente carimba aprovação. Commit local é livre; entrou commit novo, a validação é
refeita. Além dos vereditos, uma branch com commit `feat` precisa trazer a spec da mudança em
`docs/specs/<slug>/spec.md`. O carimbo manual, `.harness/approve`, é do dono e exige terminal.

### A revisão por ticket, antes de integrar

Cada ticket passa pela caça a bugs antes de ser juntado: um `revisor-bugs` por ticket, sobre a
ponta da branch do implementador. O diff de um ticket é pequeno, e é aí que a revisão funda
funciona: o defeito não chega aos tickets que dependem dele. O `.harness/integrate` recusa a
branch que não foi aprovada naquele commit exato.

O ticket de contrato tem duas leituras, juntas, porque é a base de todos os outros:

- o `revisor-bugs` procura defeito de comportamento e o que falta no contrato (cada porta que
  um módulo consome, as respostas de erro comuns, as constantes de regra);
- o `revisor-ambiente` procura o que só funciona na pasta de quem escreveu: dependência fora
  do commit, checagem que depende da ordem, valor fixo onde devia vir do ambiente, instalação
  não reproduzível.

A integração exige as duas aprovações nesse commit.

### Pendências

Achado simples não reprova. Um achado é severo quando quem usa recebe resultado errado, um
dado se perde ou fica inconsistente, uma proteção não protege, uma falha some, ou um teste
passa sem exercitar o que diz. O que sobra é simples: o revisor aprova com linhas
`PENDENCIA:`, o hook as registra, e o ticket segue.

- O teto é de duas pendências abertas por ticket. Passou disso, a aprovação não é gravada,
  mesmo que o revisor tenha escrito `APPROVED`.
- As pendências são corrigidas no fechamento, cada uma com o teste que a pegaria.
- Só um revisor fecha uma pendência: o `revisor-bugs`, no passe final, responde
  `RESOLVIDA: <id>` depois de conferir a correção no código.
- O push é recusado enquanto houver uma aberta. `.harness/pendings` lista.

### Teto de rodadas

Quando a checagem ou um revisor reprova, o achado é gravado em
`docs/specs/<slug>/achados/`, o ticket é reaberto e despachado de novo, e o revisor que
reprovou confere a correção. As rodadas são contadas por ticket, e só reprovação conta. Cada
ticket tem limite de 3 rodadas de correção: na quarta, o orquestrador para e devolve o relato
do que travou. Os outros tickets continuam andando enquanto um está em correção.

## O que é recusado por máquina

| Regra | Quem recusa |
|---|---|
| `git push`, `git fetch` e `gh` diretos | sandbox do Claude Code: a rede para o servidor de git é negada |
| Gravar em `.harness/`, `harness.conf`, `harness.d/`, `.claude/skills/`, `skills-lock.json`, `CLAUDE.md`, `docs/agents/` | sandbox (`filesystem.denyWrite`) e `permissions.deny` |
| Desligar o sandbox num comando | `allowUnsandboxedCommands: false` nas configurações geradas |
| Editar a região gerenciada do `AGENTS.md` | hook `managed_guard` |
| Pular hooks de git (`--no-verify`, `core.hooksPath`) | hook `service_guard` |
| Encadear ou embrulhar um script que sai do sandbox (`.harness/up && ...`) | hook `service_guard` |
| Implementador ou revisor subir, parar ou remover ambiente, rodar o aplicativo, enviar ou abrir pull request | hook `service_guard` |
| Revisor trocar o commit do worktree (`git checkout`, `switch`, `reset`, `restore`, `stash`, `clean`) | hook `service_guard` |
| Orquestrador juntar branch à mão (`git merge`, `rebase`, `cherry-pick`) | hook `service_guard` |
| Proposta de `harness.conf` fora do formato, ou que remove uma checagem já gravada | hook `service_guard`, ao rodar `.harness/conf-apply` |
| Pedido a um agente do harness com narrativa, chave que ele não recebe ou caminho que não existe | hook `dispatch_guard` |
| Pedido de revisão cujo `commit` não é o topo ou cujo `diff` não cobre a branch inteira | hook `dispatch_guard` |
| Implementador despachado por quem não é o orquestrador, ou sem worktree isolado | hook `dispatch_guard` |
| Orquestrador despachado com a spec fora de commit, ou sem `harness.conf` no projeto nem na spec | hook `dispatch_guard` |
| Aprovação sem veredito `APPROVED` de um revisor sobre o commit do topo, ou com mais de duas pendências no ticket | hook `gate_stamp`, que só então grava |
| Grafo de tickets com ciclo, referência inexistente, cabeçalho faltando, posse sobreposta entre paralelos ou ticket que não espera o contrato | `.harness/tickets_check.py` |
| Integrar branch sem a caça a bugs naquele commit (e, no ticket de contrato, sem a conferência de ambiente) | `.harness/integrate` |
| Integrar branch que mexeu fora do `Owns:` do ticket, ou que conflita | `.harness/integrate` |
| Integrar branch que quebra a checagem do projeto | `.harness/integrate`, que desfaz a junção |
| Marcar um ticket como `Status: done` num commit em que a checagem não passa | hook de git `pre-commit` |
| Assunto de commit fora de `tipo(escopo): descrição`, com mais de 80 caracteres, ou com co-autoria ou assinatura de IA | hook de git `commit-msg` |
| Módulo do back importando por dentro de outro módulo | `.harness/arch_check.py`, dentro do `.harness/validate` |
| Arquivo gerenciado alterado fora da atualização | `.harness/manifest_check.py`, dentro do `.harness/validate` |
| Push sem os quatro vereditos sobre o commit do topo | `.harness/gate-check`, chamado pelo `.harness/push` e pelo hook `pre-push` |
| Push de branch com commit `feat` e sem spec | `.harness/gate-check` |
| Push com pendência aberta | `.harness/gate-check` |
| Pull request com título fora do formato, sem o parágrafo de abertura, sem as seções "Critérios de aceite" e "Validação", com assinatura de IA, ou de branch que não passou pelo push | `.harness/pr` |
| Compose que dá a um contêiner acesso a algo fora da pasta do projeto | `.harness/compose_check.py`, dentro do `.harness/up` |
| Carimbo manual de aprovação por um agente | sandbox e exigência de terminal no `.harness/approve` |

Um erro interno de um guard vira negação, nunca liberação.

## O que é instalado e o que é exigido

### Pré-requisitos da máquina

| Item | Para quê |
|---|---|
| macOS ou Linux | os scripts são shell e Python |
| `git` | o projeto precisa ser um repositório git; o remoto, quando houver, por HTTPS |
| `python3` 3.9 ou mais novo | hooks, guards e validadores |
| Node.js 18 ou mais novo | o `npx` do instalador e da instalação das skills |
| Docker com Compose v2 | o ambiente por feature |
| Claude Code com sandbox disponível | a barreira de escrita e de rede |
| `gh` | abrir o pull request (`.harness/pr`) |
| `rtk` (recomendado) | comprime a saída de git e de testes; sem ele, o hook é ignorado |

### Plugins de terceiros

O instalador registra os marketplaces e instala, no escopo do projeto, o plugin do harness e
estes:

| Plugin | Origem | Para que serve aqui |
|---|---|---|
| `mattpocock-skills` | marketplace oficial `claude-plugins-official` | `grilling` e `domain-modeling` na entrevista, `tdd` na implementação, `diagnosing-bugs` para bugs; traz também skills avulsas, como `code-review`, `prototype`, `research` e `codebase-design` |
| `ponytail` | `DietrichGebert/ponytail` | sempre ligado: segura o tamanho do código que o agente escreve; a `ponytail-review` dá ao revisor os critérios de duplicação e enxugamento |
| `frontend-design` | marketplace oficial `claude-plugins-official` | direção visual das telas, para o implementador de front |

Os três entram como estão, sem adaptação no conteúdo.

### As 20 skills de stack

São skills públicas dos autores de cada tecnologia, copiadas para `.claude/skills/` e fixadas
no `skills-lock.json`. Cada papel usa só as suas; onde uma skill diverge das regras do
projeto, vale o que está em `docs/agents/stack.md`.

| Papel | Skill | Origem | Para quê |
|---|---|---|---|
| quem fatia | `parallel-feature-development` | `wshobson/agents` | fatiar para trabalho paralelo: um dono por arquivo, contrato primeiro |
| ticket de contrato | `pnpm` | `antfu/skills` | monorepo e dependências |
| ticket de contrato e páginas públicas | `seo` | `addyosmani/web-quality-skills` | SEO técnico |
| implementadores | `zod` | `anivar/zod-skill` | validação e contrato |
| todos | `vitest` | `antfu/skills` | testes de unidade e integração |
| módulo do back | `hexagonal-architecture` | `affaan-m/ecc` | use case, portas, adaptadores, ponto único de montagem |
| módulo do back | `nestjs-best-practices` | `kadajett/agent-nestjs-skills` | NestJS: módulos, injeção, erros, testes |
| módulo do back | `drizzle-orm-patterns` | `giuseppe-trisciuoglio/developer-kit` | acesso a banco |
| módulo do back | `supabase-postgres-best-practices` | `supabase/agent-skills` | esquema e consultas no Postgres |
| módulo do back | `bullmq` | `jgamaraalv/ts-dev-kit` | filas |
| módulo do back e caçador de bugs | `property-based-testing` | `trailofbits/skills` | teste por propriedade em regra com borda (data, dinheiro, intervalo) |
| fatia do front | `feature-sliced-design` | `feature-sliced/skills` | camadas, fatias, entrada pública |
| fatia do front | `nextjs-app-router-patterns` | `wshobson/agents` | Next.js: App Router, componentes de servidor e de cliente |
| fatia do front | `vercel-react-best-practices` | `vercel-labs/agent-skills` | React e desempenho no front |
| fatia do front | `shadcn` | `shadcn-ui/ui` | componentes de interface |
| ticket de ponta a ponta | `playwright-best-practices` | `currents-dev/playwright-best-practices-skill` | testes de ponta a ponta |
| revisor de código | `clean-code-guard` | `amelnagdy/guard-skills` | a rubrica do revisor: nomes, funções, SOLID, DRY |
| revisor de código | `accessibility` | `addyosmani/web-quality-skills` | acessibilidade |
| revisor de segurança | `owasp-security` | `agamm/claude-code-owasp` | lista do que procurar na revisão de segurança |
| quem fecha a entrega | `write-pr-description` | `warpdotdev/common-skills` | texto do pull request |

As 20 valem no perfil `fullstack-typescript`. O perfil `livre` recebe
`hexagonal-architecture`, `parallel-feature-development` e `clean-code-guard`; o perfil
`existente`, as duas últimas. Para outra tecnologia, `/harness:buscar-skills` procura, lê e
mostra candidatas, e só instala o que você aprovar.

### Arquivos gravados no projeto

| Caminho | O que é | Quem muda |
|---|---|---|
| `.harness/` | os scripts, os hooks, os hooks de git e os roteiros da entrega | gerenciado: só `.harness/update` |
| `.claude/settings.json` | plugins, hooks, sandbox e permissões | gerenciado; o que é do projeto entra por `harness.d/settings.json` |
| `CLAUDE.md` | aponta para o `AGENTS.md` | gerenciado |
| `docs/agents/` | onde ficam o glossário, os ADRs e os tickets e, no perfil padrão, a stack (`stack.md`) | gerenciado |
| `orca.yaml` | integração com o Orca: prepara o worktree ao abrir | gerenciado |
| `AGENTS.md` | papéis, ciclo, arquitetura e portões, entre os marcadores `harness:begin` e `harness:end` | a região entre os marcadores é gerenciada; o que está abaixo dela é do projeto |
| `harness.conf` | a configuração do projeto | o dono, ou o agente por `.harness/conf-apply` |
| `harness.d/settings.json` | hooks, permissões, servidores MCP e sites liberados só do projeto, somados na geração | só o dono |
| `.claude/skills/` e `skills-lock.json` | as skills dos autores | só `.harness/skills-add`, com a sua confirmação |

Arquivo gerenciado não se edita no projeto: uma mudança de padrão se faz no repositório do
harness e chega por atualização. Ficam livres o código, o `CLAUDE.local.md` e a parte do
`AGENTS.md` abaixo da região gerenciada. Durante o trabalho, os arquivos temporários ficam em
`.harness-run/`, fora do versionamento.

## Instalar num projeto

Um comando, no seu terminal, na pasta do projeto (um repositório git):

```bash
npx @fullchico/harness install .
```

É só isso. Ele grava os arquivos do harness, registra o marketplace, instala o plugin e as
skills. Depois abra o Claude Code na pasta e faça o pedido:

```text
/harness:entregar quero um sistema de agendamento para uma barbearia
```

Na primeira vez o Claude Code pergunta se você confia na pasta: aceite. O remoto pode vir
depois: sem ele a entrega roda até o fim, e só o envio e o pull request ficam esperando.

### Deixar o Claude instalar

Se preferir, cole este pedido numa sessão do Claude Code aberta na pasta do projeto:

```text
Instale o FullChico Harness neste projeto e deixe-o pronto para a primeira entrega. Pare se algo falhar, mostrando o erro exato.

1. Confira os pré-requisitos: esta pasta é um repositório git (se não for, pergunte antes de criar um), e existem `python3`, `node`, `docker compose` e `claude`. Diga o que falta.
2. Rode `npx @fullchico/harness install .` fora do sandbox do Bash, pedindo a minha permissão: o instalador precisa alcançar o GitHub para registrar o plugin, e dentro do sandbox isso é bloqueado. Um comando só faz tudo: grava os arquivos, registra o marketplace e instala o plugin e as skills.
3. Confira o que foi gravado: `.harness/`, `.claude/settings.json`, `.claude/skills/`, `AGENTS.md`, `CLAUDE.md` e `harness.conf`. Não edite arquivo gerenciado pelo harness.
4. Faça o commit do que foi gerado, numa branch.
5. Peça-me para reiniciar o Claude Code nesta pasta, para o plugin e os hooks carregarem.

No fim, relate em poucas linhas o que foi instalado e o comando para começar a primeira entrega: `/harness:entregar <o que eu quero construir>`, num worktree de feature.
```

### Se algo não funcionar

- **Rodei o comando de dentro de uma sessão do Claude Code e o plugin não apareceu.** O
  sandbox da sessão bloqueia o GitHub. Rode de novo no seu terminal, fora da sessão; o comando
  pode ser repetido sem dano.
- **"A origem não bate com uma entrada já registrada".** Há um marketplace `fullchico` antigo
  nas suas configurações: `claude plugin marketplace remove fullchico` e rode o instalador de novo.
- **Projeto que já tinha código.** Depois de instalar, rode `/harness:setup` numa sessão: ele
  propõe o `harness.conf` a partir do que encontra.

Ele grava `.harness/`, `.claude/settings.json`, `AGENTS.md`, `CLAUDE.md`, `docs/agents/` e
`orca.yaml`, registra os marketplaces, e instala no escopo do projeto o plugin do harness e os
de terceiros (`mattpocock-skills`, `ponytail`, `frontend-design`). Se o `harness.conf` já
estiver preenchido, também grava as portas no `.env` e instala as dependências. Pode ser
rodado de novo. Arquivo gerenciado alterado à mão trava a instalação; `--force` substitui.

### Perfis

O instalador aceita `--profile`, e a escolha fica no `harness.conf`:

| Perfil | Para quê | O que traz além do núcleo |
|---|---|---|
| `fullstack-typescript` (padrão) | projeto novo na stack padrão: NestJS, Next.js, Drizzle, Zod | a arquitetura, o arquivo da stack e as skills dela |
| `livre` | projeto novo em outra stack | os conceitos de arquitetura; a stack é escolhida na spec |
| `existente` | projeto que já tinha código | nada de arquitetura nem de língua: vale o que o projeto já usa |

O núcleo vale nos três: sandbox, os portões do push, tickets com posse de arquivo, contrato
primeiro e paralelismo.

O que é só do projeto (hooks, permissões, servidores MCP, sites liberados) vai em
`harness.d/settings.json`, que é somado na geração.

## Comandos

### Os comandos do plugin

| Comando | Para quê |
|---|---|
| `/harness:entregar <pedido>` | conduz uma mudança da entrevista ao pull request, dentro do worktree de uma feature |
| `/harness:setup` | configura o harness num projeto que já tinha código: propõe o `harness.conf` e a parte do projeto no `AGENTS.md` |
| `/harness:buscar-skills` | procura skills públicas para a stack do projeto, lê cada candidata, mostra o que achou e só instala o que você aprovar |
| `/harness:mapear` | gera ou atualiza o mapa do código e as âncoras do glossário e dos ADRs |
| `/harness:direto <pedido>` | libera a edição direta de código nesta sessão, para ajuste pequeno. Sem ele, escrever código do aplicativo fora do ciclo de entrega é negado. Só você invoca |
| `/harness:aprender` | depois do merge: atualiza o mapa, mede o consumo por papel, faz a retrospectiva e consolida as notas |
| `/harness:dream` | transforma o que as sessões ensinaram sobre o projeto em notas curtas, ancoradas no código |

### Os scripts do projeto

| Script | Para quê | Quem roda |
|---|---|---|
| `.harness/up` | sobe a infra da feature | você ou o orquestrador |
| `.harness/prepare` | migration e seed (`AFTER_UP`) | você ou o orquestrador |
| `.harness/dev` | o aplicativo (`DEV_CMD`); `--background` deixa rodando | você ou o orquestrador |
| `.harness/down` | para o aplicativo e os contêineres, mantém os dados | você ou o orquestrador |
| `.harness/destroy` | remove o ambiente da feature e apaga os dados | você, ou o agente com a sua permissão |
| `.harness/design gallery <pasta>` e `choose <pasta> <direção>` | monta a vitrine das direções de design, com o selo de leitura, e grava a escolhida em `DESIGN.md` | o agente da entrevista; quem escolhe é você |
| `.harness/screens check` e `gallery` | confere que as capturas de tela em `SCREENS_DIR` são do commit atual, e monta a galeria delas | o revisor visual e o orquestrador; quem olha a galeria antes do merge é você |
| `.harness/logs [serviço]` | mostra o estado e o fim do log do ambiente | qualquer agente; só lê |
| `.harness/ports-free` | encerra processo esquecido numa porta da feature | o orquestrador; roda sozinho quando um revisor termina |
| `.harness/setup-worktree` | prepara um worktree: `.env` e dependências | o Orca ao abrir o worktree, você, ou cada implementador |
| `.harness/worktree-env` | deriva o projeto Docker e as portas da feature e grava no `.env` | chamado pelos outros scripts |
| `.harness/conf-apply` | grava o `harness.conf` que o agente propôs, depois de conferido | o agente |
| `.harness/ticket claim\|reopen` | marca tickets como em andamento, ou reabre um, já com o commit | o orquestrador |
| `.harness/integrate <ticket> <branch>` | junta o trabalho de um implementador: revisão, posse, merge, checagem | o orquestrador |
| `.harness/resume <pasta da spec>` | diz o estado real de cada ticket em andamento (commit, revisão) e a próxima ação; só lê | o orquestrador, ao começar e ao retomar |
| `.harness/board [--text\|--json\|--watch [s]]` | gera o painel da entrega em `.harness-run/painel.html`: situação, tickets, agentes ativos, portões, pendências, linha do tempo e onde ver o resultado; a página recarrega sozinha, e `--watch` a refaz em laço | você, para acompanhar sem perguntar à sessão; só lê |
| `.harness/agents-clean` | remove os worktrees de agente já integrados | o orquestrador |
| `.harness/pendings` | lista as pendências abertas da feature | você ou o agente |
| `.harness/doctor [--hours N] [--json]` | diz se os trilhos estão de pé: hooks, arquivos gerenciados, negações recentes, portões no commit, pedidos de permissão vistos; `--prune` limpa aprovações de commit que não existe mais | você ou o agente; só lê (`--prune`, só você, no terminal) |
| `.harness/validate --profile push\|merge` | checagens do projeto, sem custo de IA | você ou o agente |
| `.harness/fetch` | atualiza as referências do remoto | o agente |
| `.harness/push` | envia a branch, depois do portão | o agente |
| `.harness/pr create\|view` | abre ou consulta o pull request | o agente |
| `.harness/skills-search <termo>` | procura skills públicas | o agente |
| `.harness/skills-show <repositório> <skill>` | mostra o texto de uma skill candidata | o agente |
| `.harness/skills-add <repositório> <skill>` | instala uma skill e a fixa no `skills-lock.json` | o agente, com a sua confirmação |
| `.harness/memory` | o mapa do código, as âncoras e as notas: `check`, `slice <caminho>`, `index`, `units`, `record`, `anchor`, `note` | você ou o agente |
| `.harness/learn` | as sessões passadas: `sessions`, `usage`, `digest`, `mark` | você ou o agente |
| `.harness/approve <portão> "<resumo>"` | a sua aprovação manual de um portão | só você, no terminal |
| `.harness/update <tag>` | leva o projeto para uma versão do harness | só você, no terminal |

Os scripts que saem do sandbox (`up`, `down`, `destroy`, `conf-apply`, `push`, `fetch`, `pr`,
`ports-free` e os de skills) rodam sozinhos, um por chamada, na forma exata: sem `&&`, `;`,
`|` nem `bash` na frente. Para você, no terminal, nada muda.

## Configuração

O `harness.conf` fica na raiz do projeto, no formato `CHAVE=valor`, uma por linha. Em projeto
novo ele é preenchido na primeira entrega, a partir da spec; em projeto que já tinha código,
`/harness:setup` propõe o conteúdo.

| Chave | O que define | Exemplo |
|---|---|---|
| `PROFILE` | o perfil do projeto; mudar pede nova sincronização | `fullstack-typescript` |
| `PROJECT` | o nome usado no projeto Docker de cada worktree | `meuapp` |
| `SERVICES` | os serviços que precisam de porta; a ordem define o deslocamento dentro do bloco | `"web api postgres redis"` |
| `COMPOSE_FILE` | o compose do ambiente | `docker-compose.dev.yml` |
| `INSTALL_CMD` | a instalação de dependências, rodada ao criar um worktree | `"pnpm install --frozen-lockfile"` |
| `AFTER_UP` | o que roda depois de a infra ficar saudável: migration, seed | `"pnpm db:migrate"` |
| `DEV_CMD` | o processo do aplicativo | `"pnpm dev"` |
| `VALIDATE_PUSH` | a checagem ao fechar e ao integrar cada ticket, e no push feito à mão | `"pnpm test"` |
| `VALIDATE_MERGE` | a checagem completa, antes de abrir o pull request; é onde entram os testes de ponta a ponta | `"pnpm test && pnpm build"` |
| `CONTRACT_PATHS` | os caminhos do que é comum (o contrato, a camada `shared` do front): só o ticket de contrato os possui | `"packages/contracts apps/web/src/shared"` |
| `MODULE_ROOTS` | onde ficam os módulos do back; o harness recusa a importação por dentro de outro módulo | `"apps/api/src/modules"` |
| `VALIDATE_ARCH` | o comando que confere as demais fronteiras, com a ferramenta da linguagem | `"pnpm exec depcruise apps/api/src && pnpm exec steiger apps/web/src"` |
| `DEFAULT_BRANCH` | a branch padrão, quando não for `main` nem `master` e o remoto não a anunciar | `trunk` |
| `MAX_PARALLEL` | o máximo de implementadores em paralelo (3, se não houver) | `3` |
| `MAP_DEPTH` | a profundidade das unidades do mapa do código | `2` |
| `MAP_EXCLUDE` | as pastas que ficam fora do mapa | `"docs .harness .claude .github"` |
| `ADR_REVIEW_COMMITS` | quantos commits na área de um ADR pedem que ele seja relido | `20` |
| `CONDUCTOR` | gera também a integração com o Conductor (`.conductor/settings.toml`) | `1` |
| `ENV_<NOME>` | variável derivada das portas, gravada no `.env` do worktree | `ENV_DATABASE_URL='postgresql://app:app@localhost:${POSTGRES_PORT}/app'` |

Os perfis estão em [Instalar num projeto](#perfis).

## Arquitetura que o harness espera

No perfil `fullstack-typescript`, a arquitetura vem junto e está na seção Arquitetura do
`AGENTS.md`. As skills dos autores ensinam o como; onde elas divergem, vale o `AGENTS.md`.

| Parte | Stack padrão |
|---|---|
| back | NestJS, Drizzle, Postgres; filas com BullMQ sobre Redis |
| front | Next.js (App Router), shadcn, Tailwind |
| contrato e validação | Zod, num pacote comum importado pelos dois lados |
| testes | Vitest (unidade e integração) e Playwright (ponta a ponta) |
| monorepo | pnpm |

- **Módulos com contrato.** O back se divide em módulos por área de negócio. Um módulo nunca
  importa outro por dentro: o que um oferece ao outro é uma porta definida no que é comum,
  pelo ticket de contrato. O que front e back trocam fica num pacote comum, importado pelos dois.
- **Portas e adaptadores no back.** Dentro de cada módulo: domínio, use cases, portas e
  adaptadores, com as dependências apontando para dentro. Um use case por comportamento,
  recebendo as portas por injeção, sem importar framework. Porta só para o que sai do
  processo (banco, fila, serviço externo); log, relógio e utilitário não viram porta.
- **Feature-Sliced Design no front.** O código nasce na página, cada fatia tem entrada
  pública, e só se importa de camada abaixo.
- **Código em inglês.** Identificadores, arquivos, pastas, rotas e mensagens de commit. Em
  português ficam o texto que o usuário vê, a spec, os tickets e o glossário, que traz o nome
  em inglês de cada termo de domínio.

Uma spec pode escolher outra peça da stack, dizendo o motivo. No perfil `livre` valem os
conceitos (módulos, portas, contrato num lugar só) em qualquer linguagem; no perfil
`existente` vale a organização que o repositório já tem.

## Ambiente por feature

Uma feature é um worktree, e cada worktree tem o próprio ambiente: um projeto Docker e um
bloco de portas derivados do nome da pasta, gravados no `.env`. Ninguém escolhe porta à mão.
Os worktrees de agente, onde os implementadores trabalham, usam o ambiente da feature de onde
saíram. O ambiente só sobe quando a validação exige; `docker` solto não funciona dentro do
sandbox, e o caminho é `.harness/up`, que confere o compose antes de subir.

## Memória do projeto

- **O mapa do código.** `/harness:mapear` gera um resumo curto de cada parte do repositório,
  escrito por subagentes em Haiku e guardado fora dos arquivos versionados. Cada resumo fica
  ancorado no commit em que foi escrito: `.harness/memory check` diz, sem custo de IA, o que
  envelheceu, e só isso é refeito. Toda sessão começa com o índice do mapa.
- **Glossário e ADRs ancorados.** O `check` também aponta termos do glossário cujo código não
  existe mais e ADRs cuja área mudou bastante. A decisão sobre eles é do dono.
- **Depois do merge.** `/harness:aprender` atualiza o mapa, mostra os tokens de cada papel
  (`.harness/learn usage`), faz a retrospectiva da entrega e, com `/harness:dream`, grava
  notas ancoradas no código. Uma nota só entra se o código de hoje a confirma. As propostas
  de melhoria ficam guardadas no repositório, fora do worktree (`.harness/learn proposals` lista).

## Projeto sem remoto

O harness não exige remoto para começar. Sem ele, a entrega roda até o fim: os tickets são
integrados, a checagem passa, os quatro vereditos são dados, e `.harness/push` confere os
portões do mesmo jeito e termina dizendo que a branch está aprovada e que nada foi enviado.
Não há pull request; o aplicativo fica de pé e o relato diz o que falta para publicar. Quando
o remoto existir, o primeiro envio da branch padrão é seu, no terminal.

## Atualizar o harness

Uma mudança de padrão se faz no repositório do harness e sai numa versão. No projeto, no seu
terminal, para ir à mais recente:

```bash
npx @fullchico/harness@latest update
```

Para uma versão específica, `.harness/update <tag>` (por exemplo `v0.2.0`). Os dois executam o
sincronizador daquela versão, para que o plugin, a pasta `.harness/` e os arquivos gerados saiam
todos com a mesma versão. Depois, faça o commit do que mudou. Arquivo gerenciado que foi
alterado à mão trava a atualização, que lista o que encontrou; `--force` substitui. O agente
não roda a atualização: dentro do sandbox ele não grava em `.harness/`.

## O que já foi provado e o que ainda não

**O que tem prova:**

- As peças têm testes automáticos: os guards, o carimbo a partir do veredito, o portão de
  push, o validador do grafo de tickets, a integração com posse, as pendências, as fronteiras
  entre módulos, o instalador, a atualização e os scripts de ambiente. A suíte roda no CI.
- Os testes também conferem a coerência entre o que os roteiros mandam fazer e o que os
  guards aceitam.
- O ciclo completo foi exercitado em entregas que partem de um projeto do zero, com um pedido
  curto, no perfil `fullstack-typescript`.

**O que ainda não foi provado:**

- **Uma segunda entrega sobre código que já existe.** As entregas exercitadas partiram de um
  projeto vazio. Evoluir um sistema já entregue, com o mapa, o glossário e a suíte de ponta a
  ponta protegendo o que funciona, ainda não foi posto à prova.
- **Os perfis fora do `fullstack-typescript`.** `livre` e `existente` têm testes das peças,
  mas não uma entrega de ponta a ponta.
- **Achar defeito continua dependendo de um revisor que é um modelo.** Os trilhos garantem
  que a revisão acontece, sobre o commit certo, por quem não escreveu o código. Não garantem
  que o revisor enxergue todo defeito.
- **A orquestração em si não tem teste automático.** Ela é conduzida por um modelo: os testes
  cobrem as peças, não a condução.

**Limites conhecidos:**

- Sem o sandbox ligado, os portões protegem contra descuido, não contra um agente que insiste.
- Um servidor de desenvolvimento que vigia arquivos pode não subir dentro do sandbox (visto
  com o `next dev`). Os testes de ponta a ponta rodam sobre o build de produção.
- O navegador dos testes de ponta a ponta não abre dentro do sandbox: ele roda num contêiner
  do ambiente.
- No Linux o sandbox não alcança `localhost`; `prepare` e `dev` precisariam de outra saída.
- Os implementadores de uma mesma feature dividem o ambiente dela; a spec precisa dizer como
  cada um isola o seu banco de teste.
- O sandbox só alcança o registro do npm. Dependência de outro lugar pede um domínio liberado
  em `harness.d/settings.json`, e liberar é do dono.
- O carimbo automático lê o veredito da transcrição do subagente. Se ele não acontecer, a
  falha é fechada: o push fica negado, e o dono usa `.harness/approve`.
- Não há suporte ao Codex ainda.

## Desenvolver o harness

```bash
python3 -m unittest discover -s tests
```

Os testes gravam em `~/.claude/harness/` e apagam ao sair, então não rodam de dentro de
uma sessão com o sandbox ligado. Alguns usam Docker de verdade e são pulados sem ele.

## Licença

MIT.
