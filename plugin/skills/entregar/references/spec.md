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
Esta seção é obrigatória: é ela que permite implementar e validar sem subir ambiente.

**Fora de escopo.** O que não entra, dito com todas as letras.

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

Em `leitura` vão o glossário e só os ADRs que tocam a área. Specs antigas não entram:
são histórico, e a verdade é o código.
