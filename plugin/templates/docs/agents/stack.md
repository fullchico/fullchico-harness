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
- **A skill de NestJS usa TypeORM, Jest e `class-transformer`.** Leia como Drizzle num
  adaptador, Vitest e esquema do contrato. `synchronize`, `@InjectRepository` e `jest.fn()`
  não entram. A regra dela "Throw HTTP Exceptions from Services" não vale: `NotFoundException`
  e afins ficam no controller ou num filtro.
- **Entre módulos do back.** De outro módulo só se importa a entrada pública (o `index`), para
  o que é transversal, como o guard de autenticação. Colaboração de negócio é pela porta do
  contrato: `exports` de service, `SharedModule` e evento em memória não a substituem.
- **Sem porta de entrada.** A skill hexagonal cria `ports/inbound` e interface para o use
  case: aqui o use case é a entrada. Log, relógio e gerador de id não viram porta. Arquivo em
  kebab-case, e quem monta as dependências é o módulo Nest da própria pasta.
- **Porta com uma implementação só não é abstração prematura.** O `clean-code-guard` manda
  embutir: para o que sai do processo, a porta fica. E cópia marcada com `shortcut:` no front
  não é duplicação a extrair.
- **O aplicativo de desenvolvimento roda em contêiner, não na máquina.** O compose tem um
  serviço para o app (imagem `node`, a pasta do projeto montada, `pnpm install` e o `dev` do
  projeto), ao lado do banco. Dentro do sandbox do Bash as ferramentas de desenvolvimento que
  vigiam arquivos ou abrem socket local não funcionam (`next dev`, `tsx`, `steiger` em modo
  vigia); no contêiner funcionam, com recarga a quente. Por isso:
  - o `dev` do front é o `next dev` normal. Não se troca o bundler nem se usa
    `next build && next start` para contornar o sandbox;
  - cada `node_modules` do workspace é um volume do contêiner (a raiz e um por pacote), porque
    os binários nativos de lá são de Linux e os da máquina não;
  - dentro do contêiner o banco é alcançado pelo nome do serviço (`postgres:5432`), definido no
    `environment` do serviço; o `.env` do worktree continua valendo para o que roda na máquina
    (testes, migration, seed);
  - o serviço tem `healthcheck` que só passa quando front e API respondem, para o
    `.harness/up` esperar o app ficar pronto;
  - o `harness.conf` fica sem `DEV_CMD`: `.harness/up` sobe tudo, `.harness/down` para tudo e
    `.harness/logs <serviço>` mostra o log. Os trilhos do harness entram no contêiner só para
    leitura, sem nada a declarar no compose.
- **O `INSTALL_CMD` deixa o worktree pronto para testar:** instala e compila o pacote de
  contrato (`pnpm install --frozen-lockfile && pnpm --filter <contrato> build`). Worktree de
  agente nasce sem o `dist` do contrato, e sem ele `typecheck` e teste falham por motivo alheio
  ao ticket.
- **`@InjectQueue` e `@Processor` ficam no adaptador.** O processor só traduz o job e chama
  o use case. A conexão vem do `.env`, nunca de `localhost:6379`.
- **Sem `vi.mock` de módulo nosso.** As skills de teste preferem mock: aqui a porta recebe o
  substituto em memória. `vi.fn` fica para callback.
- **Migration é arquivo gerado e aplicado por `.harness/prepare`.** `drizzle-kit push` não se
  usa, nem em desenvolvimento. Chave primária é `identity` ou UUID, não o `serial` dos exemplos.
- **RLS do Supabase não se aplica.** `auth.uid()` e os papéis `anon`, `authenticated` e
  `service_role` não existem aqui: autorização é no back. Pooler e parâmetros do servidor do
  banco são do ambiente, não do ticket.
- **Camadas do FSD sem prefixo.** A skill manda `src/_app` e `src/_pages` e chama o nosso
  layout de antigo: vale o que está acima. Se o build quebrar por causa do `pages/` vazio,
  relate; não renomeie.
- **Sem `shared/db` nem rota de API no front.** As skills de FSD, Next e React mostram
  consulta a banco em `shared/db`, em ação de servidor, em rota e em `generateStaticParams`:
  nada disso existe aqui. `model/` do front guarda estado e forma de exibição, não a regra
  que decide.
- **Tipos de pedido e resposta vêm do pacote do contrato,** não de DTO escrito à mão. Não
  acrescente `axios`, `swr`, `lru-cache` nem outra dependência por sugestão de skill.
- **CLI do shadcn com versão fixa e só do registro oficial.** Nada de `@latest`, registro de
  comunidade, `owner/repo` ou URL; nada de `add --all`, `init --force`, `apply` de preset nem
  `shadcn mcp init`.
- **Playwright nunca usa servidor de desenvolvimento** nem `reuseExistingServer`; endereço e
  portas vêm do `.env`. O teste prepara dado pela API, não pelo banco. `data-testid` só
  quando papel e texto não alcançam.
- **Auditoria ao vivo (Lighthouse, axe, Search Console) não roda no sandbox.** As skills `seo`
  e `accessibility` valem como lista de conferência sobre o código.
- **Fatia-se por comportamento, na vertical,** nunca por camada. Sem sub-branch nem commit
  direto na principal. O contrato fica no pacote comum, não em `src/types`.
- **Todo revisor fecha com o bloco `VEREDITO`,** não com o formato de achado da skill.
- **Comando de skill se traduz para `pnpm`** (`pnpm exec`, script do pacote): onde ela escreve
  `npx`, `npm` ou `yarn`, leia pnpm. `pnpm add -g`, `pnpm setup`, `self-update`,
  `corepack prepare` e script baixado da rede são do dono. Dependência nova e
  `--no-frozen-lockfile` só no ticket de contrato.
- **Skill não entra por dependência.** O recurso do pnpm de ligar skills de pacotes em
  `.claude/skills` não se usa; `dangerouslyAllowAllBuilds` nunca.
- **Versão da skill não é a do projeto.** As de Vitest e pnpm documentam versões beta ou
  futuras: confira a API contra a versão instalada antes de usar.
- **Nenhuma skill instala ferramenta global nem troca o gerenciador de pacotes.** É `pnpm`.
- **Skill que manda "use sempre"** não manda: quem decide é a tabela acima.
