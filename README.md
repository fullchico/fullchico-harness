<img src="site/trem.svg" alt="" width="72" align="right">

# FullChico Harness

[![npm](https://img.shields.io/npm/v/@fullchico/harness?label=npm&color=1d1b16)](https://www.npmjs.com/package/@fullchico/harness)
[![ci](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml)

[Página do projeto](https://fullchico.github.io/fullchico-harness/) · [Pacote no npm](https://www.npmjs.com/package/@fullchico/harness)

```bash
npx @fullchico/harness install .
```

Ambiente de desenvolvimento com agentes, para o Claude Code. Um plugin que padroniza, em
todo projeto que o adota, o fluxo de uma mudança, os guardrails e o ambiente de
desenvolvimento por feature.


## O que ele faz

- **Conduz uma mudança da entrevista ao pull request,** com `/harness:entregar`: entrevista,
  spec, revisão da spec, tickets em grafo, implementação em paralelo por subagentes,
  checagem, revisão de segurança e de código, envio.
- **Traz a arquitetura junto.** Back em módulos com use cases, portas e adaptadores; front em
  Feature-Sliced Design; contrato entre os dois num pacote comum. O ofício vem de skills dos
  autores, copiadas para o projeto e fixadas no `skills-lock.json`; as convenções que resolvem
  os atritos entre elas estão no `AGENTS.md`.
- **Paraleliza por contrato.** Cada ticket é dono de pastas (`Owns:`). Dois tickets paralelos
  nunca possuem o mesmo caminho, o contrato fecha antes dos demais começarem, e a integração
  recusa a branch que mexer fora da posse ou quebrar a checagem.
- **Gasta o modelo caro só onde ele paga.** A sua sessão (Opus) faz a entrevista e a spec. A
  execução inteira é de um orquestrador em Sonnet, que recebe só a spec; os implementadores e
  os revisores também são Sonnet, e os implementadores e o trabalho bruto são Haiku.
- **Não deixa código sem revisão chegar ao remoto.** O shell do agente roda no sandbox do
  Claude Code, sem rede para o servidor de git. O único caminho é `.harness/push`, que
  exige quatro aprovações sobre o commit (segurança, revisão de código, caça a bugs e
  qualidade: a checagem completa do projeto passou nele) e, para uma `feat`, a spec da mudança.
- **Nenhum agente aprova o próprio trabalho.** A aprovação nasce do veredito de um revisor
  de contexto novo, gravada por um hook, num lugar onde o agente não escreve.
- **Dá a cada feature o próprio ambiente Docker,** com portas e projeto isolados, levantado
  sem pedir nada a você.
- **Mantém um mapa do código que não envelhece calado.** Cada resumo guarda o commit em que
  foi escrito, e o git diz, sem custo, o que mudou desde então. Toda sessão começa com o índice.
- **Liga o `ponytail` e o `rtk` em todo projeto.** O `ponytail` segura o tamanho do código que
  o agente escreve; o `rtk` comprime a saída de git e de testes. Os dois entram como estão, sem
  adaptação.
- **Mantém a configuração igual entre projetos.** O que o harness instala não é editado no
  projeto: muda aqui e chega por atualização.

## Pré-requisitos

macOS ou Linux, `git`, `python3` 3.9 ou mais novo, Docker com Compose v2, e o Claude Code
com sandbox disponível. O remoto do projeto precisa ser HTTPS. Recomendado: `rtk`.

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
de terceiros (`mattpocock-skills`, `ponytail`). Se o `harness.conf` já estiver preenchido,
também grava as portas no `.env` e instala as dependências. Pode ser rodado de novo. Arquivo
gerenciado alterado à mão trava a instalação; `--force` substitui.

### Perfis

O instalador aceita `--profile`, e a escolha fica no `harness.conf`:

| Perfil | Para quê | O que traz além do núcleo |
|---|---|---|
| `fullstack-typescript` (padrão) | projeto novo na stack padrão: NestJS, Next.js, Drizzle, Zod | a arquitetura, o arquivo da stack e as skills dela |
| `livre` | projeto novo em outra stack | os conceitos de arquitetura; a stack é escolhida na spec |
| `existente` | projeto que já tinha código | nada de arquitetura nem de língua: vale o que o projeto já usa |

O núcleo vale nos três: sandbox, os três portões do push, tickets com posse de arquivo,
contrato primeiro e paralelismo.

O que é só do projeto (hooks, permissões, servidores MCP, sites liberados) vai em
`harness.d/settings.json`, que é somado na geração.

## O que muda no dia a dia

**O shell do agente passa a rodar em sandbox.** Ele grava só dentro do projeto, não alcança
o servidor de git e só acessa os sites liberados. Para você, no terminal, nada muda.

**Os comandos do harness:**

| Comando | Para quê | Quem roda |
|---|---|---|
| `.harness/up` | sobe a infra da feature | você ou o agente |
| `.harness/prepare` | migration e seed | você ou o agente |
| `.harness/dev` | o app | você ou o agente |
| `.harness/down` | para o ambiente, mantém os dados | você ou o agente |
| `.harness/destroy` | remove o ambiente da feature | você ou o agente, com a sua permissão |
| `.harness/conf-apply` | grava o `harness.conf` que o agente propôs | o agente |
| `.harness/integrate <ticket> <branch>` | junta o trabalho de um implementador: posse, merge, checagem | o agente |
| `.harness/ticket claim\|reopen` | marca tickets como em andamento, ou reabre um, já com o commit | o agente |
| `.harness/agents-clean` | remove os worktrees de agente já integrados | o agente |
| `.harness/fetch` | atualiza as referências do remoto | o agente |
| `.harness/push` | envia a branch, depois do portão | o agente |
| `.harness/pr` | abre ou consulta o pull request | o agente |
| `.harness/validate` | checagens do projeto, sem custo de IA | você ou o agente |
| `.harness/memory` | mapa do código, âncoras e notas: `check`, `slice <caminho>`, `index`, `notes` | você ou o agente |
| `.harness/learn` | sessões passadas: `sessions`, `usage`, `digest` | você ou o agente |
| `.harness/approve` | sua aprovação manual de um portão | só você, no terminal |
| `.harness/update <tag>` | leva o projeto para uma versão do harness | só você, no terminal |

**O princípio é máximo de qualidade com máximo de autonomia e mínimo de interrupção.** Você é
chamado para aprovar a spec (e nem isso no modo autônomo), para remover um ambiente, que apaga
dados, e para fazer o merge. Todo o resto roda sem pergunta: os comandos dentro do sandbox e os
scripts do harness. A qualidade não depende da sua atenção: vem dos portões, dos revisores e do
sandbox. Se quiser alguma pergunta de volta, acrescente a regra em `permissions.ask` num
fragmento do projeto (`harness.d/settings.json`); pergunta vence liberação.

## Uma primeira entrega

1. Abra um worktree para a feature, pelo Orca ou com `git worktree add`. O
   `.harness/setup-worktree` grava as portas dela no `.env` e instala as dependências.
2. Na sessão do Claude Code, dentro do worktree: `/harness:entregar`.
3. Responda a entrevista. Leia os achados do revisor da spec e aprove a spec.
4. Acompanhe: os tickets são criados, os implementadores trabalham em paralelo, a
   checagem roda, os dois revisores e o portão de qualidade dão o veredito, a branch é enviada e o pull request é aberto.
5. Faça o merge, preservando os commits.

## Seguir sem você

Se você disser "segue até o fim" durante uma entrega, ela corre em modo autônomo: toda
pergunta recebe a resposta recomendada, a aprovação da spec deixa de ser uma parada, e cada
decisão tomada sem você fica escrita na spec, na seção "Decisões tomadas sem o dono". Você
só é chamado se a entrega não fechar em três rodadas de correção, se faltar um dado que só
você tem, e para o merge.

## O mapa do código

`/harness:mapear` gera o mapa na primeira vez e depois refaz só o que mudou. O trabalho de
ler o código é de subagentes no modelo mais barato. `.harness/memory check` mostra o que
envelheceu, inclusive termos do glossário cujo código não existe mais e decisões de
arquitetura cuja área mudou bastante.

## Depois do merge

`/harness:aprender` fecha o ciclo: atualiza o mapa, mostra quanto cada papel gastou em tokens
(`.harness/learn usage`), faz a retrospectiva da entrega e, com `/harness:dream`, transforma o
que as sessões ensinaram sobre o projeto em notas ancoradas no código. As propostas de
melhoria ficam em `.harness-run/propostas/`; o que for do harness você traz para este
repositório.

## Atualizar

Uma mudança de padrão se faz neste repositório e sai numa tag. No projeto:

```bash
.harness/update v0.2.0
```

Arquivo gerenciado que foi alterado à mão trava a atualização, que lista o que encontrou.

## O que ainda não foi verificado

Tudo abaixo passou em testes automáticos ou em sessões sem interface, mas não numa sessão
interativa com um projeto de verdade. É a lista para a primeira validação:

- `.harness/conf-apply`, `up` e `down` rodando sem pergunta, e a pergunta do `destroy` aparecendo.
- `.harness/push` enviando para o GitHub com as suas credenciais, e `.harness/pr` com o `gh`.
- `/harness:setup` e `/harness:entregar` de ponta a ponta. A orquestração é conduzida por
  um modelo e não tem teste automático: os testes cobrem as peças e a coerência entre o que
  a skill manda fazer e o que os guards aceitam.
- O carimbo automático a partir do veredito dos revisores, com os dois revisores. Só o
  de segurança rodou de ponta a ponta numa sessão real.
- Instalar dependências (`pnpm install`) dentro do sandbox, num projeto com muitas.
- A trava contra desligar o sandbox, numa sessão interativa.
- `/harness:aprender` e `/harness:dream` sobre uma entrega de verdade: se a leitura das
  transcrições reconhece o formato das suas sessões, se os números de consumo batem, e se as
  notas que saem valem a pena.
- `/harness:mapear` num projeto de verdade: a qualidade dos resumos, o custo da primeira
  geração, e o hook que injeta o índice no começo da sessão.
- Um push por SSH: a rede é negada por nome de servidor, e não foi conferido se isso cobre SSH.

Limites conhecidos, que não são falha de teste:

- Sem o sandbox ligado, os portões protegem contra descuido, não contra um agente que insiste.
- Um servidor de desenvolvimento que vigia arquivos pode não subir dentro do sandbox (visto com
  o `next dev`). A validação é feita então sobre o build de produção.
- No Linux o sandbox não alcança `localhost`; `prepare` e `dev` precisariam de outra saída.
- Subagentes em paralelo na mesma feature compartilham o banco.
- Não há suporte ao Codex ainda.
- Seis revisões adversariais acharam falhas reais, todas corrigidas. Isso mostra que
  revisar funciona, e não que não reste nenhuma.

## Desenvolver o harness

```bash
python3 -m unittest discover -s tests
```

Os testes gravam em `~/.claude/harness/` e apagam ao sair, então não rodam de dentro de
uma sessão com o sandbox ligado. Alguns usam Docker de verdade e são pulados sem ele.

Licença MIT.
