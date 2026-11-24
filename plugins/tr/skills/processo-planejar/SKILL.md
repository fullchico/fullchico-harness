---
name: processo-planejar
description: Abre e conduz uma demanda até a entrega validada — entrevista o dono, escreve a spec e os tickets, orquestra a execução e passa pelos portões.
---

# Planejar e conduzir a demanda

Você é a sessão que planeja e orquestra (modelo opus). Quem executa os tickets são subagentes; o hook
do trilho escolhe o modelo deles pela `Complexidade:` do ticket (`simples` → haiku, `complexa` →
sonnet). Quem valida são os validadores dos portões, em contexto limpo. O meio é seu; o começo e o fim
são barrados por hook até as etapas acontecerem.

Depois que o dono aprovar o planejamento e os portões de entrada passarem, conduza a demanda até a
entrega sem pedir confirmação para escolhas rotineiras de implementação. Use a recomendação do plano,
as convenções do projeto e o resultado dos verificadores. Uma mudança de formatação sem alteração de
conteúdo, como linhas em branco em `PRODUCT.md`, é uma decisão de engenharia: mantenha-a se for
inofensiva, ou corrija-a de forma segura, e registre a escolha. Volte ao dono apenas se o pedido
precisar mudar de escopo, faltar uma decisão que o plano não permite inferir ou houver uma ação
irreversível ainda não autorizada.

## 1. Entrevista

Chame `/tr:grill-me`, incluída no plugin a partir do fluxo `grilling` de Matt Pocock, e, quando
disponível, `domain-modeling` (do `mattpocock-skills`). A entrevista segue em rodadas até não
sobrar decisão que mude o que será feito. O glossário e as ADRs que surgirem ficam onde
`domain-modeling` os grava.

## 2. Spec com passaporte

`docs/specs/<slug>/spec.md` (ou o caminho do portão de início do projeto: veja `portao`): problema,
solução, histórias, decisões, o que fica de fora, e como testar. Uma linha diz os portões de fim que esta
demanda pede, além dos obrigatórios do registro:

Grave o slug em `.claude/demanda-atual` para que os passaportes de demandas antigas não entrem na
entrega atual. Ao começar outra demanda, atualize esse arquivo.

```
Portões: e2e, acessibilidade
```

Escolha pelo que a demanda toca (tela → acessibilidade e e2e; página pública → seo). Os obrigatórios
valem sempre; esta linha só acrescenta os opcionais. Sem a linha, todos os portões de fim são exigidos.

## 3. Tickets

`docs/specs/<slug>/issues/NN-<slug>.md`, fatias verticais (cada uma entrega algo verificável sozinha),
cada uma com o seu passaporte:

```
Status: open
Complexidade: simples | complexa
Bloqueado por: NN, NN | nenhum
Entrada: design | nenhum
Portões: e2e, acessibilidade | api | nenhum
Arquivos: apps/web/**, packages/ui/**
```

`simples`: mecânico e local (texto, estilo, um campo, um teste a mais). `complexa`: regra de negócio,
contrato, dado, concorrência, ou mais de uma camada. Na dúvida, `complexa`.
`Portões:` lista os portões de fim específicos deste ticket. Uma task de backend não recebe
`acessibilidade` só porque outra task da demanda altera uma tela. Todos os nomes precisam existir
no registro, e os portões `sempre: true` continuam exigidos da integração inteira.
`Entrada:` lista os portões de início específicos do ticket, por exemplo uma proposta de tela
conferida contra o design system. Portões de início com `sempre: false` só liberam os tickets
que os citam. O fiscal carimba o plano antes de o executor desse ticket ser disparado.
`Arquivos:` lista os caminhos ou globs que o ticket pode alterar. Se algum desses arquivos mudar
depois do carimbo, o passaporte fica pendente e o fiscal precisa revalidar o estado atual.
Os portões de entrada do projeto liberam o início da demanda; artefatos como padrões de design
ou uma proposta de tela podem ser exigidos aí antes de qualquer código.

## 4. Portão de início

Prepare a spec e os tickets. Dispare `/tr:qualidade-verificar` para o portão de início
`processo`: um fiscal independente roda `portao processo` e carimba o plano. Passou, a escrita de
código fica liberada. O mesmo vale para qualquer outro portão de início do registro.

## 5. Execução

Os tickets sem bloqueio e com `Entrada:` carimbada são a fronteira. Para cada um, um subagente implementador com o caminho do
ticket no pedido (o hook lê a `Complexidade:` dele), a skill `tdd`, e um contexto isolado quando houver
mais de um em paralelo. Para **cada portão do passaporte**,
dispare o fiscal correspondente em contexto limpo. Quem implementou não valida.
Se reprovar, devolva os achados ao implementador; ele corrige e o fiscal reexamina.
A aprovação carimba o estado atual do projeto.

Só depois dos carimbos, registre `Status: done` no ticket e abra a próxima fronteira.
Se o projeto usa Git, `Entrega:` pode registrar o commit validado.
Você orquestra, junta e decide.

## 6. Portões de fim

Antes de declarar a entrega, confira a branch como trabalho de engenharia: `git status`, arquivos
ignorados e não rastreados, diff do que será incluído, resultados dos testes e carimbos. Corrija
arquivo local incluído por engano e mudanças sem relação com a demanda. O revisor de cada portão
examina o estado que será entregue; quem executou não aprova seu próprio trabalho. Não exija PR,
push ou remoto se o projeto não os configurou como portão.

Quando o executor declarar a implementação pronta, rode `portao`: ele confere os passaportes e mostra a
fronteira ainda aberta. Rode também `/tr:qualidade-verificar` (um verificador por portão global
de comando) e `/tr:bugs-cacar`. Falhou ou reprovou: um implementador corrige e o fiscal
revalida o que mudou. Por fim, rode `fullchico-harness entregar` ou `portao entrega`.
Só declare a entrega concluída quando esse comando passar. No início da resposta final escreva
`ENTREGA: concluída`; o hook Stop confere novamente os carimbos. Respostas intermediárias e perguntas
não usam essa marca. Git é iniciado pelo instalador; push e PR são ações separadas.
