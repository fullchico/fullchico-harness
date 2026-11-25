# Guardrails com Docker e sem sandbox nativo

## Decisão operacional

O instalador **não liga o sandbox nativo**. Isso mantém o trabalho normal do projeto, inclusive
`docker compose`, testes de integração e ferramentas que precisam do socket Docker. O harness
usa entrevista, plano aprovado, hooks, fiscais independentes, carimbos e checagem explícita de
entrega para controlar o **fluxo**. Esses mecanismos não são isolamento de segurança do host.

O projeto pode ligar o sandbox nativo por decisão própria. A documentação do Claude Code diz
que comandos `docker` são incompatíveis com seu sandbox e recomenda `excludedCommands` para
executá-los fora dele. Uma exclusão desse tipo concede ao comando acesso fora do sandbox; deve
ser delimitada ao comando necessário. Fonte: [Claude Code, sandboxing](https://code.claude.com/docs/en/sandboxing).

Docker isola os processos **dentro dos contêineres**. Um agente que recebe acesso ao socket do
daemon no host pode criar contêineres e montar caminhos do host. Portanto, usar Docker para a
infra da aplicação não isola automaticamente o próprio agente. Fontes: [Docker Engine security](https://docs.docker.com/engine/security/),
[Docker socket](https://docs.docker.com/engine/security/protect-access/).

## O que os guardrails atuais cobrem

| Camada | Garantia prática | Limite |
| --- | --- | --- |
| `PreToolUse` do `tr` | Confere chamadas de edição, Bash e disparo de subagente que chegam ao hook. | O analisador de Bash identifica formas conhecidas de escrita; scripts e ferramentas externas podem modificar arquivos por outros caminhos. |
| `SubagentStop` e assinaturas | Exige fiscal separado e veredito para os portões de agente. | Sem isolamento do processo, o mesmo usuário do sistema pode gravar no livro de carimbos fora do repositório. |
| `portao entrega` | Reconfere portões e passaportes antes de declarar a entrega. | Quem não chama o comando ou usa outra sessão não passa por esse controle local. |
| Codex local | Hooks do projeto fazem as verificações nas chamadas cobertas. | Hooks não gerenciados exigem revisão e confiança; um hook alterado é ignorado até nova confiança. |
| Docker da aplicação | Executa serviços e testes do projeto. | Acesso ao socket Docker não é uma fronteira de segurança para o agente. |

Fontes dos limites de hooks: [Claude Code, hooks](https://code.claude.com/docs/en/hooks),
[Codex, hooks](https://learn.chatgpt.com/docs/hooks).

## Melhorias recomendadas

1. **Falhar fechado no hook que barra escrita.** Adicionar `onFailure: "block"` aos hooks
   `PreToolUse` do Claude e cobrir erro de leitura ou registro inválido com decisão explícita.
   Hoje `gate.py` retorna sucesso em exceções. A opção `onFailure` está disponível no Claude
   Code 2.1.295 ou posterior. Testar também script ausente, timeout e JSON inválido.
2. **Validar no limite da entrega.** Fazer o CI executar os verificadores aplicáveis e produzir
   evidências próprias antes de bloquear ou liberar publicação. O `portao entrega` atual usa
   carimbos locais fora do repositório, portanto não pode ser simplesmente chamado num CI limpo;
   é preciso um adaptador que refaça as validações e assine a execução do CI. A revisão local
   continua rápida, mas a entrega publicada depende de um processo separado do executor.
3. **Não tratar carimbo local como prova contra adulteração.** Para projetos que precisam dessa
   garantia, mover a assinatura e o estado dos portões para um serviço confiável ou para CI,
   fora das credenciais e arquivos acessíveis ao agente. O livro local continua útil para
   retomada e feedback, mesmo sem essa garantia.
4. **Cobrir caminhos de escrita adicionais.** Testar Bash indireto, scripts Python/Node,
   redirecionamentos, symlinks, worktrees, MCP e comandos Docker que montam a pasta do projeto.
   A checagem final deve detectar mudanças no código e invalidar carimbos antigos.
5. **Perfis por projeto.** Manter `fluxo` como padrão sem sandbox nativo, com Docker disponível;
   oferecer `isolado` quando o projeto precisar restringir filesystem e rede. Documentar
   explicitamente quais comandos saem do isolamento. Não mudar o perfil automaticamente
   durante uma demanda aprovada.

Prioridade: 1 e 2 antes de apresentar os hooks como barreira forte; 3 quando houver requisito
de resistência à adulteração; 4 como teste de regressão; 5 como escolha explícita na entrevista.
