# Fatiar a spec em tickets

## Antes de fatiar

**O `harness.conf`.** Se o projeto ainda não tem `PROJECT` nele, grave agora, com o que a spec
diz: escreva o conteúdo em `.harness-run/harness.conf` e rode exatamente `.harness/conf-apply`,
sozinho, sem `&&` nem `;`. O comando confere a proposta e grava o arquivo, sem perguntar ao
dono. Faça o commit do `harness.conf`. É antes de fatiar porque `CONTRACT_PATHS` muda o que o
validador do grafo aceita.

**Entrega retomada.** Se a pasta `issues/` da spec já existe, não fatie de novo: valide o grafo
e continue da fronteira.

## O que é um ticket

Um ticket entrega um comportamento que funciona e se testa sozinho, dentro de uma pasta que é
só dele: um módulo do back, ou uma fatia do front. Não é uma camada técnica do sistema inteiro
("criar todas as tabelas", "fazer todas as telas").

- Cada ticket cabe numa sessão de um implementador.
- O primeiro ticket é o de contrato: o que front e back trocam, o que é comum, as dependências,
  o compose do ambiente e o que liga os módulos ao aplicativo. Ele bloqueia todos os outros e
  não tem teste que dependa do ambiente, porque é ele que o traz.
- O ticket de contrato também entrega as duas provas de que o resto pode confiar:
  a checagem de fronteira (`VALIDATE_ARCH`), com um caso de teste que viola cada regra e
  precisa ser recusado (inclusive importação só de tipo, e a direção entre domínio, use case
  e adaptador); e um teste de contrato, que falha se front e back divergirem em rota, método,
  status ou formato.
- Com o contrato fechado, o módulo do back e a fatia do front do mesmo recurso são tickets
  separados e rodam juntos: cada lado testa contra o contrato.
- O último ticket é o de ponta a ponta: transforma os critérios de aceite da spec em testes que
  exercitam o sistema inteiro, numa pasta só dele, e é bloqueado por todos os outros. É ele
  que protege o que já funciona quando alguém mexer em outra parte. O navegador roda num
  contêiner do ambiente (o serviço entra no compose pelo ticket de contrato), porque dentro
  do sandbox ele não abre; os testes se conectam a ele pelo endereço do `.env`.
- Dois tickets que não se bloqueiam serão feitos ao mesmo tempo. Se precisam do mesmo arquivo,
  um bloqueia o outro.

## Formato

Um arquivo por ticket, em `docs/specs/<slug>/issues/<NN>-<nome>.md`, numerados a partir
de `01`. Nas primeiras linhas, `Status:`, `Blocked by:` e `Owns:`. Os valores de `Status` são
`open`, `claimed` e `done`. `Blocked by:` traz os números dos tickets que precisam estar
concluídos antes, separados por vírgula, ou fica vazio. `Owns:` traz as pastas ou arquivos
que são só deste ticket, separados por vírgula.

## Um dono por arquivo, contrato primeiro

Use a skill `parallel-feature-development` para decidir a posse. Nela, "team-lead" é você, e
os implementadores não trocam mensagens: quem precisa de algo que não é seu relata a lacuna.

- **Posse.** A unidade é o módulo no back e a fatia no front: uma pasta. Dois tickets que
  podem rodar ao mesmo tempo nunca possuem o mesmo caminho. O validador recusa, e na
  integração a branch que mexer fora da posse é recusada.
- **O que é comum tem um ticket só.** O contrato entre front e back, os tipos e regras usados
  por mais de um módulo, as peças de interface de uso geral, os manifestos de dependência e o
  schema do banco pertencem ao ticket de contrato (ou de fundação). É ele que adiciona
  dependência nova. Com `CONTRACT_PATHS` no `harness.conf`, o validador exige que todos os
  outros tickets esperem por ele.
- **Com o contrato fechado, back e front do mesmo recurso rodam juntos:** cada lado testa
  contra o contrato, sem esperar o outro existir.
- **Nada de arquivo central editado por vários.** Cada módulo monta as próprias dependências
  dentro da pasta dele. O que liga os módulos ao aplicativo, o índice geral e o schema único
  são do ticket de contrato, ou então são descobertos por convenção.
- **Da skill, não use:** posse por camada, substituto escrito por um implementador para
  destravar outro, e junção feita à mão. Aqui a posse é por pasta e quem junta é o
  `.harness/integrate`.

```ticket 01-contrato-da-foto.md
# Contrato da troca de foto

Status: open
Blocked by:
Owns: packages/contracts

## O que entregar

Os tipos do envio de foto e da resposta, e os erros definidos na spec, no pacote que front e
back importam.

## Como validar

A checagem de tipos passa nos dois lados.
```

```ticket 02-guardar-foto.md
# Guardar a foto enviada

Status: open
Blocked by: 01
Owns: apps/api/src/modules/arquivos

## O que entregar

O envio de uma imagem válida grava o arquivo e devolve o endereço dele. Imagem maior que
o limite ou de tipo não aceito é recusada com o erro do contrato.

## Como validar

Pelo use case de guardar foto: uma imagem válida, uma grande demais e uma de tipo errado.
```

```ticket 03-mostrar-foto-no-perfil.md
# Mostrar a foto nova no perfil

Status: open
Blocked by: 01
Owns: apps/web/src/pages/perfil

## O que entregar

Depois de trocar a foto, o perfil mostra a nova, sem recarregar a página.

## Como validar

Pela tela de perfil, com as respostas do contrato simuladas.
```

Os tickets 02 e 03 rodam juntos: possuem pastas diferentes e esperam só o contrato.

## Antes de seguir

```bash
python3 -I .harness/tickets_check.py docs/specs/<slug>
```

Tem de responder `ok: N tickets`. Ciclo, referência a ticket que não existe, cabeçalho
faltando, posse sobreposta entre tickets paralelos e ticket que não espera o contrato são
recusados, com o ticket apontado. Corrija e rode de novo.

Faça o commit: `docs(spec): slice <slug> into tickets`.
