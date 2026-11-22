---
name: entregar
description: Conduz uma mudança da entrevista ao pull request, dentro do worktree de uma feature. Entrevista, spec, revisão da spec, tickets, implementação em paralelo, checagem, revisão e envio. Use sempre que o dono pedir, com ou sem o comando, algo que mude o aplicativo (feature, tela, comportamento), em vez de implementar direto.
---

# Entregar uma mudança

A entrega tem duas metades, com modelos diferentes de propósito:

- **Desenho,** nesta sessão: a entrevista, o vocabulário e a spec. É onde o raciocínio mais
  caro paga, e onde o dono participa.
- **Execução,** num subagente `harness:orquestrador`, em modelo mais barato: tickets,
  implementadores em paralelo, integração, checagem, revisores, envio. Ele recebe só a spec.

Você conduz o desenho e entrega a execução. Não fatie, não despache implementador e não
integre nada você mesmo: cada passo desses feito aqui custa o contexto inteiro desta sessão.

## Modo autônomo

Se o dono mandar seguir até o fim ("segue", "pode seguir com o recomendado", "confio na sua
análise"), a entrega passa a correr sem ele, e continua assim até ele dizer o contrário:

- **Toda pergunta recebe a resposta recomendada.** Na entrevista, nos achados do revisor da
  spec e em qualquer escolha do caminho, você decide pelo que recomendaria e segue.
- **A PARADA 1 não acontece.** Você resolve os achados do revisor da spec e continua.
- **Cada decisão fica escrita.** A spec ganha a seção `## Decisões tomadas sem o dono`: uma
  linha por decisão, com o que foi escolhido, a alternativa descartada e o motivo. É por ela
  que o dono confere depois.
- **Não peça ao dono nada que tenha comando próprio.** O `harness.conf` se grava com
  `.harness/conf-apply` e o ambiente sobe com `.harness/up`, os dois sem pergunta. Pedir que
  ele cole um arquivo ou rode um script, e esperar um "pronto", é falha sua.

O que continua parando, mesmo assim: remover um ambiente (`.harness/destroy`), a PARADA 2, uma
decisão sem alternativa recomendável (falta um dado que só o dono tem), e o merge, que é
sempre dele. O que o modo autônomo não muda: os portões, as revisões e o sandbox.

A execução corre sempre sem o dono, com ou sem modo autônomo: o orquestrador não tem a quem
perguntar.

## 0. Antes de começar

- Confira que a sessão está num worktree de feature, numa branch que não é a padrão. Se
  estiver na branch padrão, pare e peça ao dono para abrir o worktree da feature.
- Confira que há remoto: `git remote get-url origin`, e que a branch padrão já está nele
  (`git ls-remote origin`). Sem remoto não existe push nem pull request; sem a branch padrão
  lá, o pull request não tem base, e o primeiro envio dela é do dono, no terminal. Avise o dono já agora, numa linha, e siga: sem remoto a entrega vai até o fim
  (portões conferidos, aplicativo de pé) e só o envio e o pull request ficam para depois.
- Rode `.harness/fetch`. Se a branch padrão do remoto andou, traga-a para dentro da feature
  com `git merge origin/<branch padrão>`, antes de qualquer outra coisa.
- Leia `GLOSSARY.md` e os ADRs em `docs/adr/`, se existirem.
- **Só este worktree é fonte.** Não leia outros worktrees deste repositório, outras branches
  de feature nem pastas vizinhas à procura de uma spec ou de código parecido: outra tentativa
  do mesmo pedido não é requisito, e o que ela decidiu não foi decidido aqui. O que vale é o
  que o dono disse, o que está nesta branch e o que a branch padrão do remoto já tem.
- Rode `.harness/memory check`. Se o mapa da área que a mudança vai tocar está envelhecido ou
  não existe, atualize-o antes com a skill `mapear`.

## 1. Entrevistar

Com o dono, usando a skill `grilling`, até não sobrar decisão em aberto. Registre o
vocabulário e as decisões difíceis de reverter com a skill `domain-modeling`.

Se o pedido é um bug, use a skill `diagnosing-bugs` no lugar da entrevista. Bug não tem
spec nem tickets: corrija você mesmo, com teste, em commits `fix`. Como é código escrito fora de
um ticket, o harness só deixa com a edição direta aberta: se a escrita for negada, peça ao dono
para enviar `/harness:direto` e siga. Feche seguindo
`.harness/entrega/fechamento.md`, do qual valem a checagem, a revisão, o envio e o pull
request. Onde ele manda despachar implementador ou reabrir ticket, é você quem corrige: sem
spec não há orquestrador nem implementador, e o guard nega o despacho. A revisão recomeça a
cada correção.

### O design, quando o projeto tem tela e ainda não tem `DESIGN.md`

O dono não é designer, e descrever um visual em palavras não o ajuda a escolher. Ele escolhe
vendo. São protótipos rápidos e descartáveis: servem para achar o caminho; a implementação de
verdade vem depois, seguindo o que ele escolheu.

1. **Escolha a tela-chave** do produto (a que o usuário mais vai ver) e fixe um conteúdo
   fictício realista. Todas as direções mostram essa mesma tela com esse mesmo conteúdo: só o
   visual muda.
2. **Derive três direções do produto,** não de um catálogo: quem usa, em que situação, o que
   deve sentir. Elas diferem em layout, densidade e tipografia, não só em cor. Cada uma tem um
   nome e uma frase de intenção. Se a skill `frontend-design` estiver disponível, use o plano
   de tokens dela, uma vez por direção. Referência que o dono citar (um site, uma marca) vira
   atributos (espaçoso, fotos grandes, cantos arredondados), nunca cópia de logotipo, nome ou
   combinação exata de cores.
3. **Um subagente por direção,** na mesma mensagem, escreve em
   `.harness-run/design/<slug>/<direção>/`:
   - `tokens.css`: as variáveis em `:root` (claro) e `.dark` (escuro), com os nomes do shadcn
     (`--background`, `--foreground`, `--primary`, `--muted-foreground`, `--ring`, `--radius`...);
   - `index.html`: a tela, autocontida, que carrega o `tokens.css` e só usa as variáveis, com
     `<script>if(location.search.includes('theme=dark'))document.documentElement.classList.add('dark')</script>`
     no `<head>`;
   - `direcao.md`: o nome na primeira linha, a intenção na segunda.
4. **Monte a vitrine:** `.harness/design gallery .harness-run/design/<slug>`. O selo de leitura
   de cada direção é calculado pelo harness, pelo contraste dos tokens. Direção reprovada se
   corrige (escurecer ou clarear um tom quase não muda a aparência) antes de ir ao dono.
5. **Mostre ao dono** o caminho do arquivo da vitrine, que ele abre no navegador, e uma linha
   por direção: para quem ela é melhor e o que custa. **Pare e espere a escolha.** Vale "a B"
   e vale "a B com as cores da A": nesse caso ajuste a direção, monte a vitrine de novo e
   confirme. No modo autônomo, escolha a que você recomendaria, registre em `## Decisões
   tomadas sem o dono` e diga onde está a vitrine, para ele trocar depois se quiser.
6. **Grave:** `.harness/design choose .harness-run/design/<slug> <direção>` escreve o
   `DESIGN.md` na raiz, e recusa direção que não passa no contraste. Faça o commit. A spec
   aponta para ele, e o `harness.conf` ganha `TOKENS_CSS`. Sem `DESIGN.md` em commit, o
   orquestrador de um projeto com tela não é despachado.

Projeto que já tem `DESIGN.md` não repete este passo: telas novas seguem o que está lá.

## 2. Especificar

Escreva a spec seguindo `references/spec.md` e faça o commit. Ela é tudo o que a execução vai
ter: o que ficou só na conversa não chega ao orquestrador. Se o projeto é novo, a spec diz
também o conteúdo do `harness.conf`.

## 3. Revisar a spec

Dispare o `revisor-spec` com o pedido de `references/spec.md`. Apresente os achados ao dono.

**PARADA 1, fora do modo autônomo.** O dono resolve cada achado e aprova a spec. Ajuste a spec com o que ele
decidir, faça o commit, e só então siga.

## 4. Executar

Com a spec aprovada e em commit, dispare o `harness:orquestrador`, em segundo plano, só com
ponteiros:

```pedido harness:orquestrador
spec: docs/specs/exemplo/spec.md
leitura: GLOSSARY.md
```

A linha `leitura` é opcional e só lista arquivos que existem. Diga ao dono, em uma linha, que
a execução começou, e espere o orquestrador voltar. Enquanto ele trabalha você não faz nada:
não acompanhe, não confira o repositório, não repita o trabalho dele.

**PARADA 2, só se acontecer.** Se o orquestrador voltar porque um ticket não fechou em
3 rodadas de correção, relate ao dono o que travou: o achado que se repete, o que foi tentado, e a sua
leitura do motivo. Se ele voltar por lacuna na spec, corrija a spec, faça o commit e dispare
de novo.

**Se o orquestrador voltar sem terminar** (a API caiu, ou ele devolveu `PARADA` e o motivo já
foi resolvido), dispare-o de novo com o mesmo pedido de uma linha. Ele retoma sozinho: começa por
`.harness/resume`, que acha o commit de cada ticket nos worktrees de agente e diz a próxima
ação. Não cole commit, branch nem relato no pedido: o guard recusa, e ele não precisa.

## 5. Relatar

Diga ao dono o que o orquestrador devolveu: o link do pull request, o endereço do aplicativo
que ficou de pé (com o usuário de teste e como parar), o que entrou, o que ficou
de fora, quantas rodadas de correção houve, as decisões tomadas sem ele (que estão na spec), e
qualquer coisa que os subagentes relataram fora do escopo.

Depois do merge, o dono fecha o ciclo com `/harness:aprender`.
