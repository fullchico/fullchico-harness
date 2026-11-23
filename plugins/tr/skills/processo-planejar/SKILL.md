---
name: processo-planejar
description: Abre e conduz uma demanda do começo ao envio — entrevista o dono, escreve a spec com o passaporte e os tickets, orquestra a execução e passa pelos portões. Use quando o dono pedir uma mudança, funcionalidade ou correção nova, ou quando a escrita de código foi barrada pelo portão de início.
---

# Planejar e conduzir a demanda

Você é a sessão que planeja e orquestra (modelo opus). Quem executa os tickets são subagentes; o hook
do trilho escolhe o modelo deles pela `Complexidade:` do ticket (`simples` → haiku, `complexa` →
sonnet). Quem valida são os validadores dos portões, em contexto limpo. O meio é seu; o começo e o fim
são barrados por hook até as etapas acontecerem.

## 1. Entrevista

Chame a skill `grilling` e, junto, a `domain-modeling` (do `mattpocock-skills`): uma pergunta por vez,
até não sobrar decisão que mude o que será feito. O glossário e as ADRs que surgirem ficam onde a
`domain-modeling` os grava. Sem essas skills, faça você as perguntas, uma por vez, com a sua
recomendação em cada uma.

## 2. Spec com passaporte

`docs/specs/<slug>/spec.md` (ou o caminho do portão de início do projeto: veja `portao`): problema,
solução, histórias, decisões, o que fica de fora, e como testar. Uma linha diz os portões de fim que esta
demanda pede, além dos obrigatórios do registro:

```
Portões: e2e, acessibilidade
```

Escolha pelo que a demanda toca (tela → acessibilidade e e2e; página pública → seo). Os obrigatórios
valem sempre; esta linha só acrescenta os opcionais. Sem a linha, todos os portões de fim são exigidos.

## 3. Tickets

`docs/specs/<slug>/issues/NN-<slug>.md`, fatias verticais (cada uma entrega algo verificável sozinha),
cada uma com:

```
Status: open
Complexidade: simples | complexa
Bloqueado por: NN, NN | nenhum
```

`simples`: mecânico e local (texto, estilo, um campo, um teste a mais). `complexa`: regra de negócio,
contrato, dado, concorrência, ou mais de uma camada. Na dúvida, `complexa`.

## 4. Commit e portão de início

Faça o commit da spec e dos tickets e rode `portao processo` sozinho na chamada. Passou, a escrita de
código fica liberada.

## 5. Execução

Os tickets sem bloqueio são a fronteira. Para cada um, um subagente implementador com o caminho do
ticket no pedido (o hook lê a `Complexidade:` dele), a skill `tdd`, e o próprio worktree quando houver
mais de um em paralelo. Junte cada um à branch da demanda, marque `Status: done` e abra a próxima
fronteira. Você não implementa ticket: orquestra, junta e decide.

## 6. Portões de fim

Com tudo junto e commitado: `/tr:qualidade-verificar` (um verificador por portão de comando) e
`/tr:bugs-cacar`. Falhou ou reprovou: um implementador corrige, commit, e valide de novo só o que falta
(`portao` mostra). Todos carimbados, o envio (`git push`, `gh pr create`) passa pelo trilho.
