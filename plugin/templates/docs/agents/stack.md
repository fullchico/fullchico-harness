# Stack e skills

A arquitetura do `AGENTS.md` vale em qualquer stack. Este arquivo diz qual é a stack padrão,
que skill cada papel usa, e o que vale quando uma skill diverge das regras do projeto.

## Stack padrão

| Parte | Escolha |
|---|---|
| back | NestJS, Drizzle, Postgres; filas com BullMQ sobre Redis |
| front | Next.js (App Router), shadcn, Tailwind |
| contrato e validação | Zod, num pacote comum importado pelos dois lados |
| testes | Vitest (unidade e integração) e Playwright (ponta a ponta) |
| monorepo | pnpm |

Fixe a versão de cada dependência: não instale "a mais recente". Uma spec pode escolher outra
peça, dizendo o motivo.

## Que skill cada papel usa

Use só as do seu papel. As outras estão instaladas, mas não são para você.

| Papel | Skills |
|---|---|
| ticket de contrato | `zod`, `pnpm`, `seo`, `vitest`; `drizzle-orm-patterns` e `supabase-postgres-best-practices` para o schema do banco, que é dele |
| módulo do back | `hexagonal-architecture`, `nestjs-best-practices`, `drizzle-orm-patterns`, `zod`, `vitest`; `supabase-postgres-best-practices` ao escrever consulta; `bullmq` ao mexer em fila; `property-based-testing` em regra com borda (data, dinheiro, intervalo) |
| fatia do front | `feature-sliced-design`, `nextjs-app-router-patterns`, `vercel-react-best-practices`, `shadcn`, `frontend-design`, `zod`, `vitest`; `seo` em página pública |
| ticket de ponta a ponta | `playwright-best-practices` |
| revisor de código | `clean-code-guard`, `ponytail-review`, `accessibility` |
| revisor de segurança | `owasp-security` |
| caçador de bugs | `property-based-testing` |
| quem fecha a entrega | `write-pr-description` |
| quem fatia | `parallel-feature-development` |

As skills de Next.js e NestJS ensinam o framework; a arquitetura continua sendo a seção
Arquitetura do `AGENTS.md`.

## Onde a skill diverge, vale isto

- **Validação de entrada no Nest.** A skill de NestJS manda `class-validator`: aqui é o
  esquema Zod do contrato, num pipe. E "service" dela é o nosso use case.
- **Arquivo de índice.** A skill de React diz para evitá-los: isso é para biblioteca de
  terceiros. Cada fatia do front tem o seu `index.ts`, e é por ele que se importa.
- **Lógica no servidor do Next.** Nada de regra de negócio nem de acesso a banco em rota,
  ação de servidor ou componente: o front fala com o back pelo contrato.
- **Componentes do shadcn** vão para a camada `shared` do front, configurada no
  `components.json`, e não para uma pasta na raiz.
- **Esquemas Zod do contrato** ficam no pacote comum. O que é só de um lado fica com quem usa.
- **Drizzle só em adaptadores.** O tipo inferido do ORM não atravessa para use case nem domínio.
- **Fila e worker são adaptadores.** O use case conhece uma porta, não o BullMQ.
- **Erro de domínio não é erro HTTP.** O use case devolve ou lança erro do domínio; quem
  traduz para status é o adaptador de entrada.
- **Validação de entrada é pelo esquema do contrato,** não por decoradores numa classe à parte.
- **Teste de ponta a ponta** fica na pasta do ticket que o possui e usa localizador por papel
  e texto. Sem page object até haver repetição.
  - O navegador é o do contêiner do ambiente: o serviço `playwright` do compose, com a mesma
    versão do pacote instalado e `shm_size` (não `ipc: host`, que o `up` recusa), alcançado por
    `PW_TEST_CONNECT_WS_ENDPOINT`. Dentro do sandbox o navegador não abre, e não se instala
    navegador na máquina.
  - O aplicativo é o build do commit atual, compilado e servido pela própria suíte, com o
    `webServer` do Playwright, nas portas do `.env`. Isso não é "subir servidor próprio": é a
    suíte cuidando do que testa. Ninguém deixa o aplicativo rodando por fora.
  - Do contêiner, o aplicativo é `http://host.docker.internal:<porta do web>`. O navegador só
    fala com essa origem: as chamadas à API passam pelo servidor do front (um proxy), porque
    dentro do contêiner `localhost` é o próprio contêiner.
  - A suíte entra só no `VALIDATE_MERGE`. O `VALIDATE_PUSH`, que roda ao fechar e ao integrar
    cada ticket, fica com o que não precisa do sistema inteiro no ar.
- **Next com Feature-Sliced Design.** A pasta `app/` do Next fica na raiz do aplicativo, com um
  `pages/` vazio ao lado, e as camadas do padrão ficam em `src/`. Sem isso o Next trata
  `src/pages` como roteador.
- **Substituto e adaptador passam nos mesmos testes.** Para cada porta, os testes de
  comportamento (filtro, ordenação, limite, erro) são escritos uma vez e rodam contra o
  substituto em memória e contra o adaptador real. Um substituto que se comporta diferente do
  banco esconde defeito.
- **Corrida tem teste de verdade:** onde dois pedidos ao mesmo tempo não podem os dois
  vencer, há um teste que dispara os dois juntos contra o banco real.
- **Os testes leem o `.env` da raiz** do worktree (portas e endereços). A checagem do harness
  já o exporta.
- **Instalação reproduzível:** `pnpm install --frozen-lockfile` na checagem; quem muda o
  lockfile é o ticket de contrato.
- **Nenhuma skill instala ferramenta global nem troca o gerenciador de pacotes.** É `pnpm`.
- **Skill que manda "use sempre"** não manda: quem decide é a tabela acima.
