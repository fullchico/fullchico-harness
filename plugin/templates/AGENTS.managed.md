# Como se trabalha neste repositório

Esta região é gerenciada pelo harness e muda só por `.harness/update`. O que é
do projeto fica abaixo do marcador final.

## Papéis

- **Elefante:** o agente raiz da sessão. Carrega o contexto, desenha com o dono,
  dispara e monta tudo.
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

O dono roda `/harness:entregar` no worktree da feature, e o elefante conduz o ciclo.

| Passo | O que acontece |
|---|---|
| 1. Entrevistar | elefante e dono, com `grilling` e `domain-modeling`; atualiza `GLOSSARY.md` e ADRs |
| 2. Especificar | spec em `docs/specs/<slug>/spec.md` |
| 3. Revisar a spec | goldfish `revisor-spec`; o dono resolve os achados e aprova |
| 4. Fatiar | um arquivo por ticket em `docs/specs/<slug>/issues/`, com o que o bloqueia |
| 5. Implementar | goldfish em paralelo, um worktree cada, com `tdd` |
| 6. Integrar | elefante junta tudo na branch da feature |
| 7. Checar | `.harness/validate`, sem custo de IA |
| 8. Revisar | goldfish `seguranca` e `revisor`, em paralelo |
| 9. Enviar | push e PR |

Toda `feat` passa pelo ciclo inteiro. Bug entra por `diagnosing-bugs`. Spec já
mesclada é histórico: a verdade é o código, os testes e o histórico do git.

## Portões de push

Nada sai da máquina sem dois vereditos sobre o commit do topo da branch:
`seguranca` e `revisor`. Commit local é livre. Entrou commit novo, a validação
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
  apaga os dados. Os três perguntam ao dono antes de rodar. Só o orquestrador os chama.
- `.harness/prepare` roda migration e seed; `.harness/dev` roda o app
  (`--background` para deixar rodando). Os dois usam as portas da feature.
- As portas estão no `.env` do worktree. Não se escolhe porta à mão.
- `docker` solto não funciona dentro do sandbox: o caminho é `.harness/up`.

## Arquivos

- **Gerenciados, não edite:** `.harness/`, `.claude/settings.json`, `CLAUDE.md`,
  `docs/agents/` e esta região.
- **Do projeto, só o dono edita:** `harness.conf` e `harness.d/`.
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
