# Checar, revisar e enviar

A ordem importa: primeiro o que é de graça, depois o que custa.

## 1. Checagem

```bash
.harness/validate --profile merge
```

Falhou: é uma rodada de correção (`.harness/entrega/despacho.md`), com a saída da checagem como
achado. Revisor só roda sobre código que passou aqui.

## 2. Ambiente, se a validação exigir

A maior parte se valida sem ambiente, pelos pontos de costura da spec. Suba só quando o
que falta conferir depende do conjunto funcionando:

```bash
.harness/up
.harness/prepare
.harness/dev --background
```

Rode cada um sozinho, sem encadear. Confira o comportamento pelas portas do `.env`. Deixe o
ambiente de pé: uma rodada de correção ainda pode precisar dele. `.harness/down` só depois do
envio.

O app roda dentro do sandbox. Um servidor de desenvolvimento que vigia arquivos pode não
subir ali (o `next dev` é um caso). Não é defeito do código: pare o `.harness/dev`, gere o
build de produção e suba os processos compilados nas mesmas portas do `.env`. Diga no relato
que a validação foi feita sobre o build.


## 3. Revisão

Daqui em diante não se faz mais commit: cada commit novo invalida a revisão. Pegue o
commit do topo e a base da branch:

```bash
git rev-parse HEAD
python3 -I .harness/hooks/common.py branch-base "$(git rev-parse HEAD)"
```

O pedido aos dois revisores é o mesmo. O intervalo cobre a branch inteira, da base
ao topo:

```pedido harness:seguranca
diff: BASE...HEAD
commit: HASH_DO_COMMIT
```

```pedido harness:revisor
diff: BASE...HEAD
commit: HASH_DO_COMMIT
spec: docs/specs/exemplo/spec.md
leitura: GLOSSARY.md
```

No lugar de `BASE` e de `HASH_DO_COMMIT` vão os dois hashes que você acabou de obter. A
linha `leitura` é opcional e só lista arquivos que existem. Sem spec, como numa correção de
bug, o pedido ao `revisor` vai sem a linha `spec:`.

Junto com os dois revisores, dispare o portão de qualidade, que roda a checagem completa do
projeto naquele commit, com o ambiente de pé:

```pedido harness:qualidade
commit: HASH_DO_COMMIT
```

Dispare os três na mesma mensagem, com `run_in_background` como `false`, e espere os três
voltarem. O push exige os três vereditos sobre o mesmo commit.

Cada revisor termina com `VEREDITO: APPROVED` ou `VEREDITO: REJECTED`. A aprovação é
gravada por um hook a partir dessa resposta. Você não grava aprovação e não tem como.

- **Reprovou:** é uma rodada de correção, com a resposta do revisor como achado. Depois
  dela, volte ao passo 1.
- **Os dois aprovaram:** siga.

## 4. Enviar

```bash
.harness/push
```

É o único caminho até o remoto. Se ele negar, leia o motivo: aprovação faltando para o
commit atual quer dizer que houve commit depois da revisão, ou que um revisor não fechou
a resposta no formato: dispare de novo o revisor que faltou. Se o motivo for a branch padrão
do remoto ter andado, rode `.harness/fetch` e envie de novo; as aprovações continuam
valendo. Não há como contornar o portão.

## 5. Pull request

Escreva o corpo com a skill `pr`, em português, sem assinatura de IA, num arquivo que não
entra em commit:

```bash
mkdir -p .harness-run && { [ -f .harness-run/.gitignore ] || echo '*' > .harness-run/.gitignore; }
```

Grave o corpo em `.harness-run/pr-body.md` e abra o pull request:

```bash
.harness/pr create "<título>" .harness-run/pr-body.md
```

O título segue o formato dos commits e carrega o tipo mais alto da mudança: `feat` manda
sobre `fix`. Use só letras, números, espaço e pontuação simples: `&`, `$`, crase, `<`, `>`,
`;` e `|` fazem o comando ser negado. Depois do envio, `.harness/down`. Os commits são preservados no merge, sem squash.
