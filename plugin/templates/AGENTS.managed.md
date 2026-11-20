# Como se trabalha neste repositório

Esta região é gerenciada pelo harness e muda só por `.harness/update`. O que é
do projeto fica abaixo do marcador final.

## Papéis

- **Elefante:** o agente raiz da sessão. Carrega o contexto e desenha com o dono:
  entrevista e spec. Entrega a execução ao `orquestrador`.
- **Goldfish:** todo subagente. Nasce sem a conversa, entrega o trabalho e não
  valida o próprio resultado.
- **Dono:** aprova a spec e faz o merge.

Três regras:

1. **O documento é a única interface.** O pedido a um revisor só aponta: `spec:`,
   `ticket:`, `diff:`, `commit:`, `leitura:`, `achado:`. Sem narrativa nem opinião.
2. **Lacuna se corrige no documento.** Se quem implementa não consegue construir
   só com a spec e o ticket, corrija a spec; não explique por fora.
3. **Revisão no mesmo contexto não é revisão.** Quem escreveu não revisa, e o
   elefante não revisa o que orquestrou.

## Ciclo de uma mudança

O dono roda `/harness:entregar` no worktree da feature. O elefante desenha (passos 1 a 3) e
entrega a execução ao `orquestrador`, em modelo mais barato (passos 4 em diante).

| Passo | O que acontece |
|---|---|
| 1. Entrevistar | elefante e dono, com `grilling` e `domain-modeling`; atualiza `GLOSSARY.md` e ADRs |
| 2. Especificar | spec em `docs/specs/<slug>/spec.md` |
| 3. Revisar a spec | goldfish `revisor-spec`; o dono resolve os achados e aprova |
| 4. Fatiar | um arquivo por ticket em `docs/specs/<slug>/issues/`, com o que o bloqueia |
| 5. Implementar | goldfish em paralelo, um worktree cada, com `tdd` |
| 6. Integrar | o orquestrador junta tudo na branch da feature |
| 7. Checar | `.harness/validate`, sem custo de IA |
| 8. Revisar | goldfish `seguranca`, `revisor` e `qualidade`, em paralelo |
| 9. Enviar | push e PR |

Toda `feat` passa pelo ciclo inteiro. Bug entra por `diagnosing-bugs`. Spec já
mesclada é histórico: a verdade é o código, os testes e o histórico do git.

## Arquitetura

<!-- perfil: fullstack-typescript -->
Vale neste projeto. As skills dos autores ensinam o como; onde elas divergem, vale o que
está aqui. A stack padrão e a skill de cada papel estão em `docs/agents/stack.md`.
<!-- /perfil -->
<!-- perfil: livre -->
Vale neste projeto, em qualquer linguagem. A stack é a que a spec escolher. As skills dos
autores ensinam o como; onde elas divergem, vale o que está aqui.
<!-- /perfil -->
<!-- perfil: existente -->
Este projeto já tinha código antes do harness. Siga a organização, os nomes e a língua que o
código já usa: o padrão é o que está no repositório. Só mude de padrão se a spec mandar, e
então a mudança é o assunto da spec, não um efeito colateral.
<!-- /perfil -->

<!-- perfil: fullstack-typescript, livre -->
- **Back:** módulos por área de negócio. Dentro de cada um: domínio, use cases, portas e
  adaptadores, com as dependências apontando para dentro (skill `hexagonal-architecture`).
  Um use case por comportamento, recebendo as portas por injeção, sem importar framework.
- **Porta só para o que sai do processo** (banco, fila, serviço externo). Ali ela vale mesmo
  com uma implementação só. Log, relógio e utilitário não viram porta, e o use case não
  precisa de interface de entrada: ele mesmo é a entrada.
- **Cada módulo monta as próprias dependências,** dentro da pasta dele.
<!-- /perfil -->
<!-- perfil: fullstack-typescript -->
- **Front:** Feature-Sliced Design puro (skill `feature-sliced-design`): o código nasce na
  página, cada fatia tem entrada pública, e só se importa de camada abaixo.
- **Contrato:** o que front e back trocam fica num pacote comum, importado pelos dois. O
  `shared` do front é outra coisa: a camada interna dele, sem regra de negócio.
- **DRY é conhecimento num lugar só.** No front a cópia temporária de uma regra entre páginas
  é aceita, marcada com `shortcut: cópia de <caminho>; extrair quando divergir`. "Reutilize o
  que existe" vale para o que já está numa camada abaixo, nunca para importar do vizinho.
<!-- /perfil -->
<!-- perfil: livre -->
- **Contrato:** o que duas partes do sistema trocam fica num lugar só, do qual as duas
  dependem. Se forem da mesma linguagem, um pacote comum; senão, um formato neutro com os
  tipos de cada lado gerados dele.
- **DRY é conhecimento num lugar só.** Texto parecido não é duplicação; a mesma regra de
  negócio em dois lugares é.
<!-- /perfil -->
<!-- perfil: existente -->
- **DRY é conhecimento num lugar só.** Antes de escrever, procure o que o projeto já tem.
<!-- /perfil -->
<!-- perfil: fullstack-typescript, livre -->
- **Código em inglês:** identificadores, arquivos, pastas, rotas e mensagens de commit. Em
  português ficam o texto que o usuário vê, a spec, os tickets e o glossário, que traz o
  nome em inglês de cada termo de domínio.
<!-- /perfil -->
- **Clareza:** nome que diz o que é, função que faz uma coisa, retorno nomeado.
- **Um dono por arquivo.** Cada ticket possui pastas (`Owns:`) e não mexe fora delas. O que é
  comum, as dependências e o contrato são do ticket de contrato; faltou algo, relate.
- `clean-code-guard` é a rubrica do revisor. Não a aplique por conta própria nem emita a
  linha de fechamento dela.

## Portões de push

Nada sai da máquina sem três vereditos sobre o commit do topo da branch:
`seguranca`, `revisor` e `qualidade` (a checagem completa do projeto, com os testes de
ponta a ponta, rodou e passou naquele commit). Commit local é livre. Entrou commit novo, a validação
é refeita.

- Branch com commit `feat` precisa trazer a spec em `docs/specs/<slug>/spec.md`.
- Nenhum agente carimba aprovação. Ela nasce do veredito do revisor. O carimbo
  manual, `.harness/approve`, é do dono.
- O remoto só é alcançado pelos scripts do harness: `.harness/push` (envia a
  branch atual, depois do portão), `.harness/fetch` (atualiza as referências) e
  `.harness/pr create "<título>" <arquivo>` ou `.harness/pr view`. `git push`,
  `git fetch` e `gh` diretos não funcionam: a rede para o servidor de git é
  negada dentro do sandbox.
- Push negado se corrige pela causa. Agentes nunca usam `--no-verify`.
- O Bash roda em sandbox: escrita em `.harness/`, `harness.conf` e no estado dos
  portões é negada pelo sistema. Não é erro a contornar.

Todo revisor termina a resposta com este bloco, cada item numa linha inteira:

```
VEREDITO: APPROVED   (ou REJECTED)
COMMIT: <hash completo do commit revisado>
RESUMO: <uma linha>
```

## Ambiente

Uma feature é um worktree, e cada worktree tem o próprio ambiente: projeto Docker
e bloco de portas derivados do nome da pasta. Subagentes trabalham em cima do
worktree da feature e usam o ambiente dela.

- O ambiente só sobe quando a validação exige. Teste que roda sem infra não sobe nada.
- `.harness/up` sobe a infra, `.harness/down` para, `.harness/destroy` remove e
  apaga os dados. Só o `destroy` pergunta ao dono. Rodam sozinhos, sem `&&` nem `;`.
- `.harness/prepare` roda migration e seed; `.harness/dev` roda o app
  (`--background` para deixar rodando). Os dois usam as portas da feature.
- As portas estão no `.env` do worktree. Não se escolhe porta à mão.
- `docker` solto não funciona dentro do sandbox: o caminho é `.harness/up`.

## Memória

O mapa do código fica fora dos arquivos versionados, ancorado no commit em que cada
resumo foi escrito. `.harness/memory check` diz, sem custo, o que envelheceu;
`.harness/memory slice <caminho>` mostra o resumo de uma área; `/harness:mapear` atualiza.
Depois do merge de uma entrega, `/harness:aprender` mede o consumo, faz a retrospectiva e
consolida em notas o que as sessões ensinaram.
Spec já mesclada é histórico. A verdade é o código, os testes e o histórico do git.

## Arquivos

- **Gerenciados, não edite:** `.harness/`, `.claude/settings.json`, `CLAUDE.md`,
  `docs/agents/` e esta região.
- **Do projeto:** `harness.conf` muda por `.harness/conf-apply` ou pelo dono; `harness.d/` é
  só do dono. `.claude/skills/` e `skills-lock.json` são das skills dos autores: não edite.
- **Livres:** `CLAUDE.local.md`, o código, e o que está abaixo desta região.

Mudança de padrão se faz no repositório do harness, não aqui.

## Commits e PRs

O git é a memória do porquê. Cada commit é um contexto coerente:

- assunto `tipo(escopo): descrição`, em inglês, até 80 caracteres; tipos `feat`,
  `fix`, `chore`, `docs`, `refactor`, `test`;
- corpo livre e longo quando precisar: o porquê, a decisão tomada, o que foi
  descartado;
- **nunca** co-autoria nem assinatura de IA, em commit ou em PR.

Antes de mexer numa área, leia o histórico dela: `git log -- <caminho>`. PRs são
escritos em português e mesclados preservando os commits, sem squash.
