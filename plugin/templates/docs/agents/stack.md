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
| ticket de contrato | `zod`, `pnpm`, `seo`, `vitest` |
| módulo do back | `hexagonal-architecture`, `drizzle-orm-patterns`, `zod`, `vitest`; `supabase-postgres-best-practices` ao mexer em tabela ou consulta; `bullmq` ao mexer em fila |
| fatia do front | `feature-sliced-design`, `vercel-react-best-practices`, `shadcn`, `frontend-design`, `zod`, `vitest`; `seo` em página pública |
| ticket de ponta a ponta | `playwright-best-practices` |
| revisor de código | `clean-code-guard`, `ponytail-review`, `accessibility` |
| revisor de segurança | `owasp-security` |
| quem fatia | `parallel-feature-development` |

Para Next.js e NestJS não há skill: valem a seção Arquitetura do `AGENTS.md` e a documentação
que vem com o próprio pacote instalado.

## Onde a skill diverge, vale isto

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
- **Teste de ponta a ponta** fica na pasta do ticket que o possui, usa localizador por papel
  e texto, e roda com o navegador do contêiner do ambiente: o serviço `playwright` do compose,
  com a mesma versão do pacote instalado, alcançado por `PW_TEST_CONNECT_WS_ENDPOINT`. Dentro
  do sandbox o navegador não abre, e não se instala navegador na máquina. A página testada é
  o build do aplicativo, alcançado do contêiner por `host.docker.internal`. Sem page object
  até haver repetição.
- **Nenhuma skill instala ferramenta global nem troca o gerenciador de pacotes.** É `pnpm`.
- **Skill que manda "use sempre"** não manda: quem decide é a tabela acima.
