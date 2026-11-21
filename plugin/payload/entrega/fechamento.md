# Checar, revisar e enviar

A ordem importa: primeiro o que é de graça, depois o que custa.

## 1. Ambiente de pé

O ambiente da feature (banco, fila, contêiner do navegador) já está de pé desde o despacho e
fica assim até o envio. Confira com `.harness/up`, sozinho: se já está no ar, ele só avisa.
Depois de integrar um ticket que mudou o schema, rode `.harness/prepare` de novo.

Você não sobe o aplicativo à mão antes do envio. Os testes de ponta a ponta compilam e sobem
o aplicativo do commit atual por conta própria (o `webServer` do Playwright), e o derrubam ao
terminar. Se o aplicativo ficou de pé de uma execução anterior, ele ocupa as portas de que os
testes precisam: rode `.harness/down` e depois `.harness/up`.

## 2. Checagem

```bash
.harness/validate --profile merge
```

É a checagem completa: testes de unidade e de integração, fronteiras, build e ponta a ponta.
Falhou por defeito do código: é uma rodada de correção (`.harness/entrega/despacho.md`), com a
saída como achado. Falhou porque o ambiente não respondeu: conserte o ambiente e rode de novo;
isso não é rodada de correção. Revisor só roda sobre código que passou aqui.

## 3. Pendências

```bash
.harness/pendings
```

São os achados simples que o caçador de bugs deixou abertos para os tickets passarem. Se a
lista veio vazia, siga. Senão, cada pendência é corrigida agora, com o teste que ela indica:
grave a lista em `docs/specs/<slug>/achados/pendencias.md`, faça o commit, e despache um
`harness:implementador` por ticket dono dos arquivos apontados, com esse arquivo como `achado:`
(reabra o ticket com `.harness/ticket reopen`). Integre como qualquer rodada de correção e
volte ao passo 2. Quem fecha a pendência é o caçador de bugs, no passe final abaixo: você não
tem como fechá-la.

## 4. Revisão

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
juntos e confere cada pendência aberta (responde `RESOLVIDA: <id>` para as que foram corrigidas). O pedido é o dos revisores, sem a linha `ticket:`:

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
- **Os quatro aprovaram:** rode `.harness/pendings`. Vazio: siga. Se sobrou pendência, ela
  não foi corrigida: volte ao passo 3.

## 5. Enviar

```bash
.harness/push
```

**Projeto sem remoto.** O comando confere os quatro portões do mesmo jeito e termina dizendo
que a branch está aprovada e que nada foi enviado. É um fim válido: pule o passo 6 (não há
pull request), faça o passo 7 e diga ao dono, no relato, o que falta para publicar.

É o único caminho até o remoto. Se ele negar, leia o motivo: aprovação faltando para o
commit atual quer dizer que houve commit depois da revisão, ou que um revisor não fechou
a resposta no formato: dispare de novo o que faltou. Se o motivo for a branch padrão
do remoto ter andado, rode `.harness/fetch` e envie de novo; as aprovações continuam
valendo. Não há como contornar o portão.

## 6. Pull request

Escreva o corpo em português, sem assinatura de IA, com a skill `write-pr-description` se
ela estiver instalada, neste padrão. `.harness/pr` recusa o corpo sem a abertura e sem as
duas seções marcadas com obrigatória:

```markdown
<uma a três frases: o que a entrega faz e por quê; quem lê só isto sabe se é o revisor certo>

## Critérios de aceite          (obrigatória)

| Critério da spec | Teste que o cobre |
|---|---|
| <critério, como está na spec> | <arquivo do teste e nome do caso> |

## O que mudou

<por módulo; decisão que tinha alternativa real, e por que a alternativa perdeu>

## Validação                    (obrigatória)

<os quatro vereditos com o commit, e a linha final de `.harness/validate --profile merge`>

## Riscos e pendências

<o que pode quebrar fora dos arquivos tocados; o que ficou de fora; "nenhum" se for o caso>
```

Critério sem teste que o cubra não entra na tabela como coberto: escreva "sem teste" e
explique em Riscos e pendências. O arquivo do corpo não entra em commit:

```bash
mkdir -p .harness-run && { [ -f .harness-run/.gitignore ] || echo '*' > .harness-run/.gitignore; }
```

Grave o corpo em `.harness-run/pr-body.md` e abra o pull request:

```bash
.harness/pr create "<título>" .harness-run/pr-body.md
```

O título segue o formato dos commits e carrega o tipo mais alto da mudança: `feat` manda
sobre `fix`. Use só letras, números, espaço e pontuação simples: `&`, `$`, crase, `<`, `>`,
`;` e `|` fazem o comando ser negado. Os commits são preservados no merge, sem squash.

## 7. Deixar o aplicativo de pé e dizer onde

A entrega só termina quando o dono consegue ver o resultado, sem ter de montar nada. Depois
do envio (`up` sozinho na chamada):

1. `.harness/up` e `.harness/prepare`: o ambiente está de pé e o banco, pronto.
2. `.harness/dev --background`: o aplicativo sobe.
3. Confira que ele responde: o front e a API nos endereços do `.env` desta feature
   (`curl -s -o /dev/null -w "%{http_code}"`). Se uma porta estiver ocupada, `.harness/ports-free`.

No relato final, logo depois do link do pull request:

- o endereço do aplicativo, e o da caixa de e-mail de teste se houver;
- o usuário e a senha de teste, se o sistema tem login;
- como parar: `.harness/down`.

Se o aplicativo não respondeu, diga isso com a última linha de `.harness-run/dev.log`, em vez
do endereço. Não diga que está de pé sem ter conferido.
