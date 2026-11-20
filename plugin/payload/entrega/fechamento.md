# Checar, revisar e enviar

A ordem importa: primeiro o que é de graça, depois o que custa.

## 1. Ambiente de pé

O ambiente da feature (banco, fila, contêiner do navegador) já está de pé desde o despacho e
fica assim até o envio. Confira com `.harness/up`, sozinho: se já está no ar, ele só avisa.
Depois de integrar um ticket que mudou o schema, rode `.harness/prepare` de novo.

Você não sobe o aplicativo à mão. Os testes de ponta a ponta compilam e sobem o aplicativo
do commit atual por conta própria (o `webServer` do Playwright), e o derrubam ao terminar.

## 2. Checagem

```bash
.harness/validate --profile merge
```

É a checagem completa: testes de unidade e de integração, fronteiras, build e ponta a ponta.
Falhou por defeito do código: é uma rodada de correção (`.harness/entrega/despacho.md`), com a
saída como achado. Falhou porque o ambiente não respondeu: conserte o ambiente e rode de novo;
isso não é rodada de correção. Revisor só roda sobre código que passou aqui.

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

E a caça a bugs final, sobre a branch inteira, que procura o que só aparece olhando os módulos
juntos. O pedido é o dos revisores, sem a linha `ticket:`:

```pedido harness:revisor-bugs
spec: docs/specs/exemplo/spec.md
diff: BASE...HASH_DO_COMMIT
commit: HASH_DO_COMMIT
```

Dispare os quatro na mesma mensagem, com `run_in_background` como `false`, e espere todos
voltarem. O push exige os quatro vereditos sobre o mesmo commit.

Cada revisor termina com `VEREDITO: APPROVED` ou `VEREDITO: REJECTED`. A aprovação é
gravada por um hook a partir dessa resposta. Você não grava aprovação e não tem como.

- **Um revisor reprovou:** é uma rodada de correção, com a resposta dele como achado. Depois
  dela, volte ao passo 2: commit novo pede os quatro vereditos de novo.
- **A qualidade reprovou:** leia o resumo. Se foi o ambiente que não respondeu, conserte-o e
  dispare só a qualidade de novo. Se foi teste ou build, é rodada de correção.
- **O caçador de bugs reprovou:** é rodada de correção para os tickets donos dos arquivos
  apontados; cada caso entra como teste junto com a correção.
- **Os quatro aprovaram:** siga.

## 4. Enviar

```bash
.harness/push
```

É o único caminho até o remoto. Se ele negar, leia o motivo: aprovação faltando para o
commit atual quer dizer que houve commit depois da revisão, ou que um revisor não fechou
a resposta no formato: dispare de novo o que faltou. Se o motivo for a branch padrão
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
