# Teste dos portões com a LP (2026-11-22): pontos de falha

Projeto: agenda-ai-app, worktree `porgy`, branch `fullchico/lp-barbearia` (a partir de `origin/main`).
Sessão de teste aberta dentro do projeto, pelo Orca. Esta lista é da monitoria de fora: o que
falhou, quando, e o que foi feito para o fluxo seguir. Horários locais (UTC−3).

O relatório da própria sessão fica no projeto, em `docs/uso/2026-11-22-teste-portoes-lp.md`.

## Pontos de falha

| # | Hora | Onde | O que falhou | Destrave aplicado |
|---|------|------|--------------|-------------------|
| 1 | 21:59 | Instalação | `npx @fullchico/harness@2.0.1 install` não roda: o pacote expõe `fullchico-harness` e `cc`, não um bin com o nome do pacote. O comando que a própria lib divulga (`npx @fullchico/harness@latest install`) dá `could not determine executable to run`. | A sessão achou sozinha: `npx -p @fullchico/harness@2.0.1 fullchico-harness …`. |
| 2 | 22:00 | Instalação dentro da sessão | O sandbox do projeto legado (v0.1.8) nega escrita em `.claude/settings.json`, em `~/.claude/.cc-writes/` e no `.cc-writes` do projeto, e bloqueia a rede para `github.com`. Nenhum `claude plugin install` conclui. A lib não consegue se instalar de dentro de uma sessão num projeto que ela mesma protegeu. | Rodei o `install --padrao` e o `add qualidade bugs` fora do sandbox, da sessão de monitoria. |
| 3 | 22:00 | `portoes --padrao --gravar` | Grava `.claude/trilho.json` primeiro e só depois tenta proteger o `settings.json`: com o settings protegido, sai com stack trace e deixa o registro meio-vivo. O roteiro de "próximos passos" é impresso mesmo assim. | Nenhum; a segunda execução, fora do sandbox, completou. |
| 4 | 22:07 | `install --padrao` | Liga só `tr` e `memoria`. O registro padrão que ele mesmo grava tem os portões `qualidade` e `bugs`, mas os plugins `qualidade` e `bugs` não são instalados. Os portões ficam sem quem os assine. | `fullchico-harness add qualidade bugs --project .` |
| 5 | 22:07 | `install --padrao` | Não migra do legado: `harness@fullchico` segue ligado e os hooks de `.harness/hooks/` continuam no `settings.json`. Legado e 2.0.1 rodam juntos. | Não mexi. Fica como dado do teste; precisa de decisão do dono. |
| 6 | 22:07 | `install --padrao` | O `ref` do marketplace `fullchico` continua `v0.1.8`. Os plugins vieram da versão nova só porque o marketplace já estava no disco. Numa máquina limpa, a instalação usaria a v0.1.8, que não tem `tr`. | Não mexi. |
| 7 | 22:07 | `portoes --padrao` | O portão `qualidade` padrão usa `npm test`, num monorepo pnpm cujo comando real é `pnpm lint && pnpm typecheck && pnpm test`. O padrão não olha o projeto. | Fica para o `tr:configurar` da sessão. |
| 8 | 22:02 | Monitoria | A sessão lançada como chat do Orca não aceita mensagem de fora: não dá para destravar nem responder pedido de permissão. | Relancei a continuação como terminal. |
| 9 | 22:16 | `tr:configurar` | A skill manda o agente chamar o CLI `portoes`, mas o `.claude/trilho.json` está em `denyWrite` do sandbox (protegido pela própria lib): o CLI sai com `PermissionError`. A configuração dos portões pela entrevista não funciona de dentro da sessão. | Rodei `portoes --definir qualidade …` e `portoes --registrar <esboço>` de fora, com o esboço que a sessão deixou. |
| 10 | 22:16 | CLI `portoes` | O `--registrar <arquivo>` existe no código, mas não aparece no `uso:` nem no `--help`. Só a leitura do script revela como acrescentar portão novo. | Nenhum. |
| 11 | 22:16 | Carimbo × árvore suja | O `portao qualidade` passou, mas o hook recusou assinar porque `.claude/settings.json` e `.claude/trilho.json` estavam sem commit. O `bugs:cacar` também exige árvore limpa. A instalação da lib deixa a árvore suja e não diz que é preciso commitar antes de carimbar. | Autorizei a sessão a commitar os dois na branch. |
| 12 | 22:16 | Portões `seo` e `performance` | O Lighthouse precisa de um Chrome; dentro do sandbox não sobe. A lib não prevê navegador para portões de comando. | Subi um Chrome headless fora do sandbox com CDP em `localhost:9333` e passei `LIGHTHOUSE_CDP_PORT=9333`. Ainda não sei se o sandbox deixa conectar. |
| 13 | 22:16 | Envio da PR | O `tr` só reconhece `git push` e `gh pr create`. O `.harness/push` legado passa por fora dele; quem negou foi o legado, que exige quatro vereditos de agentes `harness:*` inexistentes. E o `git push` direto cai no `deniedDomains: github.com` do sandbox. Com legado e 2.0.1 juntos, não há caminho de envio que funcione de dentro. | Orientei a usar `git push` pelo `tr`; se a rede barrar, o push sai de fora, depois de conferir os carimbos. |
| 14 | 22:16 | `gate.py` | Falso positivo: um heredoc que escrevia um `.md` em `docs/` foi barrado porque o texto citava um redirecionamento para `apps/`. O `bash_targets` lê o conteúdo do heredoc como comando. | Nenhum; a sessão escreveu de outro jeito. |
| 15 | 22:16 | Contexto | O legado (`session_context.py`) e o `memoria` injetam o mesmo mapa do código no começo da sessão. | Nenhum. |
| 16 | 22:25 | Carimbo × commit | Um commit só de relatório (`3a829e9`) derrubou os 6 carimbos de fim, como previsto, e o push foi barrado. Mas o efeito prático é que o relatório do teste não pode registrar os carimbos do próprio commit: gravá-los é um commit novo, que os derruba. Um commit só de documentação custa a rodada inteira de portões. | Nenhum; a sessão refez a rodada no `d499da8`. |
| 17 | 22:26 | Carimbo `bugs` | O plugin `bugs` e o `tr` assinam os dois o mesmo veredito do `bugs:cacador` (duas linhas `assinou` no livro). | Nenhum. |
| 18 | 22:26 | Comando do portão | O comando do portão tem de ser exatamente `portao <nome>`, sem variável na frente; a sessão teve de pôr `LIGHTHOUSE_CDP_PORT=9333` no `.env` do worktree. Não há como passar ambiente para um portão. | Nenhum. |
| 19 | 22:26 | Envio | Com os 7 carimbos no topo, o `tr` deixou o `git push` passar, e o sandbox barrou: `deny network-outbound github.com:443`. O portão de fim funciona, mas o envio é impossível de dentro da sessão com o sandbox atual. | Push e `gh pr create` feitos de fora, depois de conferir HEAD igual a `d499da8`, árvore limpa e `portao` sem faltas. PR #4. |

## Guardrails confirmados (o que funcionou)

- 22:07:42: `Write` em `apps/web/src/pages/landing/probe.ts` antes do `processo` foi barrado pelo `gate.py` do `tr`. O mesmo aconteceu com a escrita por `Bash` (22:07:46 e 22:09:18).
- 22:07:45: `Edit` no `.claude/trilho.json` foi barrado ("só o dono altera").
- 22:07:47: `git push` sem os portões de fim foi barrado, listando `qualidade` e `bugs`. O `qualidade` e o `bugs` 0.2.0 cederam ao `tr`, sem mensagem em dobro.
- Spec commitada (`6b65e51`), `processo` carimbado, e a escrita em `apps/` liberou.
- 22:24–22:25: os 7 portões de fim carimbaram no `49bf22b`, um por chamada, cada um pelo hook (`portao <nome>` → `assinou` no log): `qualidade` (209 + 29 testes), `bugs` (`bugs:cacador`, 20 s), `acessibilidade` (3 testes axe), `seo` (5 testes, Lighthouse SEO 1.0), `performance` (Lighthouse 1.0) e `analytics` (4 testes). O Lighthouse conectou ao Chrome de fora pelo CDP `localhost:9333`.

## A observar nos portões (qualidade do que eles provam)

- O `seo` passa com o canonical e o sitemap apontando para `localhost`: o caçador de bugs notou que, sem `SITE_URL`, as URLs saem com localhost. O portão confere a presença das tags, não se as URLs são as de produção.
- O `performance` dá 1.0 rodando localmente, contra o build servido na própria máquina. Isso não representa a rede real; o portão prova pouco sem um alvo publicado ou uma limitação de rede mais dura.
- O `bugs:cacador` assinou em 20 s, com duas observações simples. Vale conferir se a revisão leu o diff inteiro da branch ou só o último commit.

## O que a lib corrigiu (2026-11-22, sem versão publicada)

| Ponto | Correção |
|---|---|
| 1 | `package.json` expõe também o bin `harness`: `npx @fullchico/harness <comando>` funciona. |
| 2, 9 | `install` e `portoes` testam a escrita antes de mexer em qualquer coisa. Sem permissão, param com "rode no terminal, fora da sessão" e não gravam nada. A skill `tr:configurar` passou a montar o esboço fora do repositório e entregar os comandos ao dono, sem insistir. |
| 3 | Sem registro pela metade: a checagem vem antes da gravação, e os "próximos passos" só aparecem quando o `install` termina sem erro. |
| 4 | O `install` instala o plugin dos portões que assinam por agente (`bugs:cacador` → `bugs`). O `qualidade` não entra, porque o `tr` já assina os portões de comando. |
| 5, 13, 15 | `install` avisa quando acha o harness antigo; `install --migrar` desliga o `harness@fullchico` e os hooks de `.harness/hooks/` no settings. O `.harness/` fica para o dono apagar. |
| 6 | `install` e `add` prendem o marketplace `fullchico` em `v<versão da lib>`. |
| 7 | `--padrao` tira o comando de qualidade do `package.json` do projeto; sem scripts, fica `@definir`, nunca `npm test` às cegas. |
| 10 | `--registrar <esboço.json>` aparece no `uso:` do CLI e no README. |
| 11 | Os próximos passos do `install` mandam commitar `settings.json` e `trilho.json` antes de carimbar. |
| 14 | O `gate.py` e o `is_send` ignoram o corpo de heredoc; a linha que abre o heredoc (o alvo real) continua contando. |
| 16 | Commit só de documentação (`docs/` ou `.md`) depois do carimbo de fim mantém o carimbo; qualquer outra mudança, inclusive no registro, derruba. `portao` mostra de qual commit veio o carimbo e avisa quando tudo está liberado. |
| 17 | Com registro de portões, o plugin `bugs` não assina o veredito: só o `tr` assina. |
| novo | `fullchico-harness custo`: tokens e US$ por modelo, principal contra subagentes, tempo ativo contra paradas, eventos dos portões. |

Fica em aberto, por decisão:
- 12 e 18: navegador e variável de ambiente para portão de comando. A checagem lê do `.env` do projeto; a skill diz isso.
- 19: o push de dentro da sessão continua impossível com o sandbox que nega `github.com`. Liberar `git push` fora do sandbox abriria um caminho para rodar código sem sandbox (hook de git e config local, ambos graváveis pelo agente). O envio fica como passo do dono, com o `tr` conferindo os carimbos antes.
- 8: chat do Orca sem mensagem de fora não é da lib.

## Custo medido com `fullchico-harness custo`

| Entrega | Janela | Parede | Ativo | Parado | US$ (estimativa) | Principal / subagentes |
|---|---|---|---|---|---|---|
| v0.1.8, 14 tickets (21/11) | 14:10 → 22:54 | 524 min | 232 min | 292 min | 52,67 | 14,44 / 38,24 |
| 2.0.1, LP (22/11) | 21:59 → 22:31 | 32 min | 25 min | 7 min | 8,41 | 7,61 / 0,80 |

As duas entregas não têm o mesmo escopo; a tabela mostra a forma do gasto, não ganho de velocidade. Na v0.1.8, 73% do custo foi de subagentes (orquestrador, implementadores, revisores) e 56% do tempo foi parada.
