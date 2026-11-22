# A spec de uma mudança

Uma spec por mudança, em `docs/specs/<slug>/spec.md`. O `<slug>` é curto, em minúsculas,
com hífens: `editar-foto-do-usuario`.

A spec é escrita para alguém que vai implementar sem ter visto a entrevista. Use os termos
do `GLOSSARY.md` e respeite os ADRs da área.

## Seções

**Problema.** O que incomoda hoje, do ponto de vista de quem usa.

**Solução.** O que passa a acontecer, do ponto de vista de quem usa.

**Histórias.** Lista numerada e extensa: "Como <quem>, quero <o quê>, para <por quê>".
Cubra os casos de erro e os estados vazios, não só o caminho feliz.

**Decisões de implementação.** Módulos que nascem ou mudam, contratos entre eles, mudanças
de esquema, e cada escolha que foi feita na entrevista, com o motivo.

**Decisões de teste.** Os pontos de costura: por onde cada comportamento é testado. Prefira
um ponto de costura que já existe e o mais alto possível. Diga o que é um bom teste aqui
(comportamento observável, não detalhe interno) e aponte testes parecidos que já existem.
Esta seção é obrigatória: é ela que permite implementar cada ticket sem o sistema inteiro no ar.

**Critérios de aceite.** Numerados, do ponto de vista de quem usa: o que precisa acontecer para
a entrega valer. Cada um vira um teste de ponta a ponta, e é essa suíte que protege o que já
funciona nas entregas seguintes.

**Módulos e contrato.** Os módulos do back e as fatias do front que nascem ou mudam, cada um
com a sua pasta. É daqui que sai a posse de cada ticket. O contrato tem duas partes, e as duas
ficam definidas aqui, antes de qualquer implementação:

- **Entre front e back:** as operações (método, rota, status) e os tipos de entrada e saída.
- **Entre módulos:** para cada módulo, o que ele **oferece** aos outros e o que ele **consome**
  de outros: a porta, o que ela recebe e devolve, e quem a implementa. Um módulo nunca
  importa outro: consome uma porta que mora no que é comum. Todo "consome" tem de ter um
  "oferece" correspondente. Liste também o que os testes de todos precisam em comum (como
  isolar banco e fila entre implementadores que rodam juntos).

Defina também o que todos os módulos fazem igual: a resposta para identificador inválido, para
corpo malformado e para erro não previsto, e o formato do erro.

O que ficar de fora daqui vira um ticket reaberto no meio da entrega, e uma rodada perdida
para todos os que dependem dele.

**Ambiente e execução.** Quem executa a spec não tem a quem perguntar, então diga aqui:
os serviços de que os testes dependem (banco, fila), o serviço do compose em que o aplicativo
roda em desenvolvimento, e como cada implementador isola o seu
quando vários rodam ao mesmo tempo no mesmo ambiente (um banco de teste por ticket, por
exemplo); e, se o projeto ainda não tem `harness.conf` preenchido, uma subseção `harness.conf`
com o conteúdo do arquivo, incluindo `CONTRACT_PATHS` (os caminhos do contrato e do que é
comum), `MODULE_ROOTS` (a pasta dos módulos do back: de outro módulo só se importa a entrada pública, e o harness recusa o resto), `VALIDATE_ARCH` (o comando que confere as demais fronteiras), o serviço `playwright` em
`SERVICES` com o endereço dele em `ENV_PW_TEST_CONNECT_WS_ENDPOINT`, e os testes de ponta a
ponta só no `VALIDATE_MERGE`. Sem ela o orquestrador não é despachado. Se existir
`docs/agents/stack.md`, ele diz o que vale para a stack: leia antes de escrever esta seção. No
perfil de stack livre, é a spec que escolhe a stack, e diz por quê. O sandbox só alcança o registro do npm: se o projeto instala dependências de outro
lugar, diga ao dono já na entrevista, porque liberar um domínio é dele (`harness.d/settings.json`).

**Fora de escopo.** O que não entra, dito com todas as letras.

## Nomes

Todo nome que vai virar código (rota, pasta, arquivo, tabela, campo, identificador) é escrito
na spec já na língua que o `AGENTS.md` define para o código. O texto que o usuário vê fica na
língua do produto. Os termos vêm do glossário, que traz o nome de código de cada um.

## O que não entra na spec

Caminho de arquivo e trecho de código envelhecem rápido. Descreva o módulo e o contrato.
A exceção é um trecho curto que fixa uma decisão melhor que a prosa, como o formato de um
tipo ou os estados de uma máquina.

## Depois de escrever

Faça o commit: `docs(spec): add <slug>`. Então peça a revisão:

```pedido harness:revisor-spec
spec: docs/specs/exemplo/spec.md
leitura: GLOSSARY.md, docs/adr/0001-exemplo.md
```

A linha `leitura` é opcional e só lista arquivos que existem: o pedido é negado se apontar
para um caminho que não está lá. Nela vão o glossário e só os ADRs que tocam a área. Specs antigas não entram:
são histórico, e a verdade é o código.
