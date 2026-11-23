# Melhoria: o sandbox como gargalo do ambiente

Aberta em 2026-11-21, a partir da entrega `agendamento-barbearia` no `agenda-ai-app` (lib
v0.1.8). Nada aqui foi implementado nem testado: é diagnóstico e proposta. O que é fato
conferido e o que é hipótese está marcado.

## O que aconteceu na entrega

Em menos de uma hora (17:39 a 18:31), com três tickets de base:

| Hora | Ticket | Falha dentro do sandbox | Custo |
|---|---|---|---|
| 17:39 | 01 | `steiger` cai com `EMFILE` | achado severo, uma rodada de revisão |
| 18:05 | 01 | CLI do `tsx`: `listen EPERM /tmp/claude-501/tsx-501/*.pipe` no `db:seed` | ticket integrado reaberto |
| 18:13 | 03 | `ui.shadcn.com` negado pela rede | componentes shadcn escritos à mão |
| 18:28 | 01 | `next dev` (Turbopack): `unable to start FSEvent stream`, e o `concurrently -k` derruba API e contratos | ticket integrado reaberto pela segunda vez; bundler de dev trocado para webpack sem o dono |
| 18:30 | 01 | implementador e os dois revisores negados em `.harness/dev` | a correção foi integrada sem ninguém ter subido o app para conferir |

Dois dos cinco não são do sandbox do sistema, e sim regra nossa: a última linha é o
`service_guard` (`_CONDUCTOR`, item V3 das pendências da v8), e a lista de domínios é do
`plugin/templates/settings.json`.

### Negações contadas nas transcrições (17:34 a 19:30, 4 tickets integrados)

Contagem de resultados de comando com a mensagem, somando sessão principal e agentes.

| Negação | Vezes | Agentes | Efeito |
|---|---|---|---|
| `EMFILE` em vigia de arquivos | 29 | 11 | `steiger`, Watchpack do Next |
| `unable to start FSEvent stream` | 8 | 5 | Turbopack |
| `nice(5) failed` | 8 | vários | só ruído: o comando em segundo plano roda mesmo assim |
| `kill` negado | 6 | 2 | dois servidores órfãos na porta do front |
| `listen EPERM` em socket de `TMPDIR` | 6 | 6 | CLI do `tsx` |
| `EPERM` ao gravar `packages/contracts/dist` no worktree de outro agente | 7 | revisores | revisor não consegue compilar o pacote de contratos na cópia do implementador |
| `ps` negado | 3 | 3 | agente não consegue listar processos para achar o que deixou de pé |
| `.harness/env-common.sh: cannot create temp file for here document` | 2 | 2 | script do próprio harness falha no sandbox |

As duas últimas linhas e a do `dist` não estavam na lista inicial: são limites que atingem a
revisão e os scripts da lib, não o aplicativo.

## Por que vira gargalo

1. **O app roda dentro do sandbox.** `.harness/up` está em `excludedCommands` e sobe só a
   infra (Docker). `.harness/prepare` e `.harness/dev` rodam o código do projeto dentro do
   sandbox, por desenho: `up` não executa nada do projeto justamente porque sai do sandbox.
   Então toda ferramenta de desenvolvimento que observa arquivos ou abre socket local esbarra
   no Seatbelt.
2. **Três falhas, duas causas.**
   - *Vigia de arquivos.* Turbopack não abre o fluxo do FSEvents. O `EMFILE` do `steiger`
     é provavelmente a mesma causa (sem FSEvents, o chokidar cai para um descritor por
     arquivo). **Hipótese**: nenhuma fonte lida confirma o mecanismo.
   - *Socket Unix em `TMPDIR`.* O sandbox aponta `TMPDIR` para `/tmp/claude-<uid>` e nega
     `bind`/`listen` de socket ali, embora deixe gravar arquivo. Há issues do Claude Code com
     esse título exato (41254, 41817, 50165); só os títulos foram lidos.
3. **A lib já sabia de uma delas e não virou trilho.** `docs/verificacao-plataforma.md`
   registra em 2026-11-19: "`next dev` (Turbopack) não sobe dentro do sandbox". A entrega de
   hoje redescobriu isso às 18:28, depois de três tickets integrados.
4. **A falha aparece tarde e no ticket errado.** O problema só surge quando um ticket
   posterior usa a ferramenta (o seed do 02, o `dev` depois do 03), e o conserto é atribuído
   ao 01, que já estava integrado, mexendo em arquivo de outro ticket.
5. **Quem conserta não pode conferir.** O achado manda confirmar com `.harness/dev`; o guard
   nega esse comando a implementador e revisor. O commit saiu dizendo "Not yet verified".
6. **O agente contorna mudando o aplicativo.** Sem saída no ambiente, a correção vai para o
   `package.json` do projeto (`tsx` por `node --import tsx`, Turbopack por webpack). São
   decisões de stack do dono tomadas para acomodar a ferramenta de entrega.

## O que a plataforma oferece (lido na documentação em 2026-11-21)

- `sandbox.network.allowMachLookup`: lista de serviços Mach/XPC liberados, só macOS. É o
  candidato para o FSEvents. **Não confirmado**: a documentação não cita FSEvents, e o nome do
  serviço precisa sair do log (`log show --predicate 'sender == "Sandbox"'`).
- `sandbox.network.allowUnixSockets` e `allowAllUnixSockets`: lista de caminhos de socket.
  Pelos títulos das issues, não cobrem `bind`/`listen`. **Não confirmado**.
- `sandbox.excludedCommands`: casamento exato com o texto da chamada; o comando roda fora do
  sandbox. É o que já usamos.
- Subagentes usam a mesma configuração de sandbox da sessão. Não há sandbox por subagente
  documentado.
- Turbopack não documenta modo de polling.

## Propostas, da mais barata para a mais cara

1. **Sonda do sandbox na preparação.** Um script (`.harness/sandbox-check`, rodado pelo
   `setup` e antes do primeiro ticket) que tenta, dentro do sandbox, o que a entrega vai
   precisar: abrir vigia de arquivos, escutar em socket Unix em `TMPDIR`, escutar em porta
   local, alcançar os domínios que o projeto declarou. O resultado vai para o orquestrador e
   para o dono antes de qualquer código. Troca cinco descobertas no meio da entrega por um
   relato no começo.
2. **Testar `allowMachLookup` para o FSEvents.** Uma sessão mínima, como as de
   `verificacao-plataforma.md`: `next dev` com e sem o serviço liberado, conferindo no log do
   sistema. Se funcionar, entra no modelo de `settings.json` e some a causa das linhas 1 e 4
   da tabela. Avaliar o que mais esse serviço abre antes de adotar.
3. **Conferência do ambiente ao alcance de quem corrige.** Hoje `_CONDUCTOR` nega `dev` a
   todos menos o orquestrador. Duas saídas, a escolher:
   - um comando só de leitura (`.harness/status`: o que está de pé, em que porta, fim do log)
     liberado a todos; ou
   - o achado de ambiente dar ao implementador dele o direito de reiniciar o app (o
     `dispatch_guard` já lê o campo `achado:`).
   Sem uma das duas, correção de ambiente continua sendo integrada sem prova.
4. **Decisão de stack por causa do sandbox pede o dono.** Quando a correção de um achado de
   ambiente troca ferramenta do projeto (bundler, executor de TypeScript), isso é registrado
   como decisão pendente do dono, não como ajuste silencioso. Hoje o arquivo se declara "não
   conta como rodada" e segue.
5. **Domínios do projeto na entrevista.** O `setup` pergunta de quais registros e sites a
   stack depende (aqui, `ui.shadcn.com`) e propõe a lista de `allowedDomains`. Liga com o
   item 20 da v8 (skill `shadcn`).
6. **O app em contêiner, junto com a infra.** O `harness.conf` do projeto já declara
   `SERVICES="web api postgres playwright"`, mas `DEV_CMD="pnpm dev"` roda no host. Se o
   perfil `fullstack-typescript` subisse `web` e `api` pelo compose, o app sairia do Seatbelt
   sem que código do projeto rodasse solto na máquina: o contêiner é a barreira, e o
   `compose_check.py` já confere o que ele alcança. É a mudança maior, e a que tira a classe
   inteira de problema.

### Direção do dono (2026-11-21, 19:25)

O dono indicou a proposta 6 como caminho: o Docker monta o ambiente inteiro (front, API,
banco, cache), não só a infra. O que ela resolve além da vigia de arquivos:

- **Processo órfão.** Hoje foram dois na porta do front (18:35, do revisor; 19:17, que o
  `.harness/down` deixou). Com o app em contêiner, `compose down` encerra tudo, e ninguém
  precisa de `kill` nem de `ports-free` para o app.
- **Decisão de stack por causa do sandbox.** O `dev` do front voltaria a ser o `next dev`
  normal, com hot reload; `tsx` e Turbopack deixam de ser problema.
- **Quem pode subir.** `.harness/up` já sai do sandbox sem executar código do projeto na
  máquina; o código roda dentro do contêiner, conferido pelo `compose_check.py`.

O que precisa ser desenhado antes:

- **`node_modules` do contêiner separado do host.** Binários nativos (swc do Next, esbuild)
  são de macOS no host e de Linux no contêiner; o contêiner precisa de volume próprio e do
  seu próprio `pnpm install`.
- **Vigia de arquivos em pasta montada do macOS.** A conferir no Docker Desktop atual; se
  falhar, é polling, só dentro do contêiner.
- **Qual pasta é montada.** O ambiente é da feature; os agentes escrevem em worktrees
  próprios. O app do contêiner mostra a branch da feature, depois do `integrate`.
- **Testes continuam no host, dentro do sandbox.** `lint`, `typecheck`, `test` e `build` já
  rodam lá sem problema; só o que fica de pé (servidores) vai para o contêiner.
- **Quem escreve o Dockerfile e o compose do app.** Hoje o perfil gera o compose da infra;
  o do app depende da stack e entraria no ticket de base, sob o `compose_check.py`.

## O que não fazer

**Pôr `.harness/dev` ou `.harness/prepare` em `excludedCommands`.** Eles executam `DEV_CMD` e
`AFTER_UP`, que são scripts do `package.json`, graváveis pelo agente. Fora do sandbox, um
agente escreveria num script o que quisesse e o rodaria sem barreira, inclusive gravar em
`.harness/` e nas aprovações. É exatamente o que o sandbox foi adotado para impedir
(`verificacao-plataforma.md`, seção de 2026-11-19).

## Intervenções do dono durante a entrega

Cada linha é um ponto em que a entrega só andou porque alguém de fora agiu. É a lista do que
os trilhos ainda não resolvem sozinhos.

| Hora | O que travou | Intervenção | O que faltou no harness |
|---|---|---|---|
| 19:16 | Porta 35520 presa por 44 min pelo `next dev` que o revisor de ambiente subiu às 18:35 para conferir a correção. O `kill` é negado no sandbox; o `.harness/ports-free` poupa processo que roda da pasta da feature; o `.harness/dev` caiu por porta ocupada e o orquestrador ficou 24 min num laço esperando a porta liberar, sem avisar o dono. | `kill 63953` rodado de fora do sandbox, por uma sessão de monitoria, com o sim do dono. | (a) Revisor que sobe servidor precisa de um jeito de encerrá-lo: hoje o `ports-free` roda no `SubagentStop`, mas não pega processo cuja pasta é a da feature, e o revisor trabalha justamente nela. (b) O `ports-free` poderia distinguir "o app que o `.harness/dev` subiu" (PID em `.harness-run/dev.pid` e filhos) de qualquer outro processo na porta, em vez de decidir pela pasta. (c) Bloqueio que o orquestrador descreve como fora do alcance dele deve virar parada com pedido ao dono, não espera em silêncio. (d) A sessão principal recebeu "concluído" do orquestrador duas vezes e não repassou o bloqueio. |

| 20:01 | Segundo órfão na porta 35520: o `.harness/down` das 19:16 disse "App parado (PID 73993)", mas o `next start` filho (PID 74205) ficou vivo 44 min, adotado pelo PID 1. O orquestrador tentou `kill`, foi negado e seguiu sem registrar. | `kill 74205` de fora do sandbox, antes de travar a checagem da onda. | O `kill_tree` do `down` percorre os filhos por `pgrep -P`; o `next start` sob `pnpm`/`concurrently` escapa. Encerrar pelo grupo de processos, ou conferir as portas da feature ao fim do `down` e falhar com aviso se alguma continuar ocupada. É o item 7 das pendências da v8. |
| 20:02 | Onda parada por 44 min (19:18 a 20:02) por um **pedido de permissão aberto na tela da sessão principal**: o modo automático do Claude Code pediu confirmação para um `grep` de leitura do implementador do ticket 05 ("3 consecutive actions were blocked"). O implementador ficou mudo, o orquestrador esperou por ele com o ticket 06 já aprovado, e a sessão principal dizia "não há nada para eu fazer". Pela transcrição parecia agente morto; só a tela do terminal mostrava o pedido. | Leitura da tela pelo CLI do Orca (`terminal read --screen`) e resposta "Yes" com Enter, depois de conferir que o comando era o `grep` de leitura. O implementador voltou a escrever em 5 segundos. | (a) Pedido de permissão de subagente em segundo plano não aparece em nenhum arquivo que o harness lê: precisa de um sinal (hook de `Notification`/`PermissionRequest` gravando em `.harness-run/`, ou aviso ao dono). (b) O perfil de permissões gerado deveria cobrir os comandos de leitura que os agentes usam o tempo todo (`grep`, `find`, `git log`), para o modo automático não ter o que perguntar. (c) O orquestrador não distingue "implementador trabalhando" de "implementador parado esperando o dono": falta tempo limite por despacho. (d) Onda não deveria reter ticket aprovado (06) por causa de outro (05) independente. |

## A verificar antes de decidir

- O nome do serviço Mach do FSEvents e se `allowMachLookup` basta.
- Se `allowUnixSockets` com caminho em `/tmp/claude-<uid>` libera `listen` na versão atual do
  Claude Code (ler o corpo e o estado das issues 41254, 41817 e 50165).
- Se o `EMFILE` do `steiger` some com o FSEvents liberado.
- Se o `--webpack` realmente sobe no sandbox. Primeira evidência, do revisor de ambiente às
  18:35: o Next diz "Ready", o Watchpack solta `EMFILE: too many open files, watch` em série e
  o `curl` na raiz estoura 90 s sem resposta. Ou seja, trocar o bundler não resolveu: a causa
  é a vigia de arquivos, não o Turbopack. O revisor também não conseguiu encerrar o servidor
  que ele mesmo subiu (`kill: operation not permitted`), e a porta ficou ocupada.
- Vigia de arquivos em contêiner com pasta montada do macOS, para a proposta 6.

## Portões que não atuaram no teste de 2026-11-22 (v2.0.1, `porgy`)

Assunto vizinho ao sandbox: o ambiente deixou o trabalho passar por fora dos trilhos.

**O que aconteceu.** Entre 19:09 e 19:28 a sessão da lib (huchen) subiu o `porgy` para a
2.0.1, escreveu a spec da tela A, mandou um subagente implementar, deu `git push` e abriu a
PR #3 do agenda-ai-app. Nenhum portão barrou nada. Ninguém rodou `portao` em nenhum momento,
então não há carimbo de `processo`, `qualidade` nem `bugs`. A própria sessão deixou o portão
`bugs` "para o dono".

**Causa 1: o plugin não estava carregado.** `tr`, `bugs` e `qualidade` estão instalados com
escopo de projeto (só no `porgy`) e ligados no `.claude/settings.json` dele. A sessão foi aberta
no huchen, que não tem `settings.json` de projeto nem `trilho.json`, e operou o `porgy` por
`cd`. Nas transcrições da sessão e do subagente rodaram só os hooks do rtk, do ponytail e o
genérico do ambiente. `gate.py` e `sign.py` não aparecem nenhuma vez.

**Causa 2: mesmo carregado, o gate olharia o repositório errado.** O `gate.py` (linha 72 na
0.3.0 do `tr`) tira a raiz de `payload.cwd`, o diretório da sessão. Em
`cd ~/orca/workspaces/agenda-ai-app/porgy && git push …` a raiz continua sendo o huchen. Lá não
há registro, e o gate sai em `if not reg: return 0`. O `ledger.is_send` reconhece o push; o erro
está só em qual repositório ele consulta.

**Prova.** Chamei `registry.missing` do próprio plugin com a raiz no `porgy`, sem disparar o
hook. Faltam `processo` (início) e `qualidade` e `bugs` (fim). Numa sessão aberta no `porgy`, a
escrita em `apps/`, o push e o `gh pr create` seriam barrados.

**O que isso diz da lib.**
- A barreira inteira mora em hooks do Claude Code ligados ao projeto aberto. Quem opera o
  repositório de fora (outra sessão, um subagente com outro `cwd`, o terminal) passa livre.
- O gate deveria resolver a raiz pelo alvo do comando: `cd X &&`, `git -C X`,
  `gh --repo`/`-R` e o caminho absoluto do `file_path` em `Edit`/`Write`. Hoje usa só o
  `cwd` da sessão.
- Falta uma barreira no próprio repositório para o portão de fim: um hook de git `pre-push`
  que leia o mesmo carimbo. Assim o push sem carimbo falha venha de onde vier. Ela não cobre
  o `gh pr create` de uma branch que já está no remoto; para isso, um check de CI que leia o
  carimbo, ou o carimbo publicado junto da branch.
- O teste de uma versão da lib precisa ser feito numa sessão aberta dentro do projeto
  testado. Do contrário mede o agente, não o harness.
- Também visto no teste: o `settings.json` do `porgy` fixa o marketplace em `ref: v0.6.0`,
  que não tem o plugin `tr`. Funcionou porque o cache já tinha a versão nova. Numa máquina
  limpa, a instalação pode falhar ou trazer o `trilho` antigo. O `update` da lib deveria
  atualizar esse `ref`.
- Os plugins `qualidade` e `bugs` têm um gate de push próprio, além do `tr`. No `porgy` estão
  instalados na 0.1.0, que barra o envio sozinha sempre que o commit do topo não tem carimbo. A
  0.2.0 da lib cede ao `tr` quando há `trilho.json` com `portoes`. A cópia 0.2.0 no cache foi
  marcada como órfã às 19:58, então o projeto ficou com plugins de gerações diferentes. No
  teste, o `619db56` do `porgy` não tinha carimbo de `qualidade` nem de `bugs`: o push deveria
  ter sido barrado três vezes (`tr`, `qualidade`, `bugs`). Nenhum dos três estava carregado na
  sessão. Se estivessem, o `qualidade` olharia o huchen (raiz pelo `cwd` da sessão) e barraria
  por falta de carimbo lá: certo por acaso, no repositório errado.
