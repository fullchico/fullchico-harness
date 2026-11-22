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
  - O aplicativo testado é o do compose, o mesmo do desenvolvimento: `.harness/up` o deixa de
    pé e a suíte só confere que ele responde antes de começar. A suíte não compila nem sobe
    servidor na máquina (sem `webServer` do Playwright), e ninguém roda o aplicativo por fora.
  - Do contêiner do navegador, o aplicativo é `http://<serviço do app>:<porta>`, pela rede do
    compose. O navegador só fala com essa origem: as chamadas à API passam pelo servidor do
    front (um proxy).
  - O app do compose roda em modo de desenvolvimento, que não prova o build de produção: o
    `VALIDATE_MERGE` roda `pnpm build` além da suíte.
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
- **Cada parte do sistema é um serviço do compose** (regra do `AGENTS.md`). Nesta stack: um
  serviço para o front, um para a API, um por peça de infra (Postgres, Redis) e o do navegador.
  - Front e API usam a imagem `node`, montam a pasta do projeto e rodam o `dev` normal de cada
    um, com recarga a quente: `next dev` e `nest start --watch`. Não se troca o bundler nem se
    usa `next build && next start` para contornar o sandbox: no contêiner as ferramentas que
    vigiam arquivos funcionam.
  - As dependências são de Linux lá dentro e de macOS na máquina. Cada `node_modules` do
    workspace (a raiz e um por pacote) é um volume nomeado, e um serviço de passagem única roda
    o `pnpm install` e a compilação do contrato; front e API dependem dele com
    `condition: service_completed_successfully`, para não instalarem ao mesmo tempo.
  - Um serviço alcança o outro pelo nome (`postgres:5432`, `http://api:<porta>`), definido no
    `environment` de cada um. O `.env` do worktree continua valendo para o que roda na máquina
    (testes, migration, seed), com as portas publicadas.
  - Front e API têm `healthcheck` que só passa quando respondem: é o que faz o `.harness/up`
    esperar o sistema ficar pronto.
  - O `harness.conf` fica sem `DEV_CMD`. Os trilhos do harness entram nos contêineres só para
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
- **Acessibilidade é portão de máquina, no nível WCAG 2.2 AA.** O que a máquina confere não
  fica para o revisor:
  - **Contraste dos tokens:** o `harness.conf` aponta o arquivo dos tokens em `TOKENS_CSS`
    (o `globals.css`), e todo `.harness/validate` reprova texto abaixo de 4,5:1 e anel de foco
    abaixo de 3:1, no claro e no escuro. O tema padrão do shadcn reprova: ajuste-o no ticket
    de contrato.
  - **Tela:** a suíte de ponta a ponta usa `@axe-core/playwright` (roda no contêiner do
    navegador, sem rede), numa fixture `a11y()` com as etiquetas `wcag2a`, `wcag2aa`,
    `wcag21a`, `wcag21aa` e `wcag22aa`, mais as regras `aria-dialog-name`, `heading-order` e
    `landmark-one-main`. Cada teste chama `a11y()` depois de cada estado que a tela tem:
    carregada, diálogo aberto, formulário enviado inválido. Violação reprova o teste. Exceção
    é `disableRules` com o motivo escrito, nunca lista inteira aceita.
  - **Código:** o ESLint soma as regras de `eslint-plugin-jsx-a11y` em modo `strict` sobre o
    `eslint-config-next` (espalhe só `flatConfigs.strict.rules`: registrar o plugin de novo
    quebra), com `Button`, `Input` e `Label` mapeados em `settings`, e nega campo com
    `aria-invalid` sem `aria-describedby`.
  - **Teclado:** cada tela com formulário e cada diálogo tem teste de que o erro fica ligado ao
    campo (`toHaveAccessibleDescription`), o foco aparece, o diálogo fecha com Esc e devolve
    o foco, e não há rolagem lateral em 320 px.
  - **Formulário usa o `Form`/`FormControl` do shadcn,** que liga a mensagem de erro ao campo
    sozinho. O `Field`/`FieldError` não liga: com ele, o `id` e o `aria-describedby` são seus.
- **Capturas de tela são artefato da entrega.** A suíte de ponta a ponta tira captura de cada
  tela e de cada estado que ela tem (carregada, diálogo aberto, formulário inválido, lista
  vazia), em 390×844 e 1280×800, no tema claro e no escuro, grava em `SCREENS_DIR` (chave do
  `harness.conf`, pasta fora do git) e escreve o `telas.json` com o commit. O
  `harness:revisor-visual` abre cada uma antes do push, e o dono olha a galeria antes do merge.
  O tema segue o sistema (`next-themes` com `defaultTheme="system"`), e os testes que tiram
  captura rodam com um worker só. Cada teste chama `shot(page, tela, estado)` depois de cada
  estado:

  ```ts
  import { execSync } from "node:child_process";
  import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
  import { expect, type Page } from "@playwright/test";

  const git = (args: string) => execSync(`git ${args}`).toString().trim();
  const commit = git("rev-parse HEAD");
  const dir = `${git("rev-parse --show-toplevel")}/.harness-run/telas`; // o SCREENS_DIR do harness.conf
  const slug = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const grava = (arquivo: string, dado: string | Buffer) => {
    writeFileSync(`${dir}/${arquivo}.tmp`, dado); // troca de uma vez: ninguém lê arquivo pela metade
    renameSync(`${dir}/${arquivo}.tmp`, `${dir}/${arquivo}`);
  };

  export async function shot(page: Page, tela: string, estado: string) {
    mkdirSync(dir, { recursive: true });
    const original = page.viewportSize();
    for (const [nome, largura, altura] of [["celular", 390, 844], ["computador", 1280, 800]] as const)
      for (const [tema, esquema] of [["claro", "light"], ["escuro", "dark"]] as const) {
        await page.setViewportSize({ width: largura, height: altura });
        await page.emulateMedia({ colorScheme: esquema });
        await layout(page);
        const arquivo = `${slug(tela)}-${slug(estado)}-${nome}-${tema}.png`;
        grava(arquivo, await page.screenshot({ animations: "disabled" }));
        const caminho = `${dir}/telas.json`;
        const antes = existsSync(caminho) ? JSON.parse(readFileSync(caminho, "utf8")) : {};
        const telas = (antes.commit === commit ? antes.telas : []).filter((t: { arquivo: string }) => t.arquivo !== arquivo);
        grava("telas.json", JSON.stringify({ commit, telas: [...telas, { arquivo, tela, estado, largura, altura, tema }] }, null, 1));
      }
    await page.emulateMedia({ colorScheme: null });
    if (original) await page.setViewportSize(original);
  }
  ```
- **Layout é medido por máquina, junto de cada captura.** "Sem rolagem lateral na página" não
  basta: uma janela com `overflow` escondido corta por dentro, e a página nem percebe; e o clique
  pelo nome funciona mesmo com o botão espremido. `layout(page)` falha quando:
  - um elemento visível tem a borda direita além da largura da tela e não está dentro de um
    ancestral feito para rolar na horizontal (classe `overflow-x-auto` ou `overflow-x-scroll`);
  - um contêiner com `overflow` escondido tem conteúdo mais largo que ele
    (`scrollWidth > clientWidth`), ou seja, está cortando; o mesmo vale para o que rola de lado
    sem ter sido feito para isso;
  - um contêiner feito para rolar na horizontal não rola de fato: cresceu até a largura do
    conteúdo e saiu da tela, ou de quem o corta;
  - um título (`h1` a `h3`) passa das bordas laterais, ou o título de um diálogo aberto não está
    inteiro na área visível.

  Exceção é `data-layout-ok="<motivo>"` no elemento, nunca a checagem desligada.

  ```ts
  export async function layout(page: Page) {
    const falhas = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth, vh = window.innerHeight, out: string[] = [];
      const quem = (e: Element) => `<${e.tagName.toLowerCase()} class="${e.getAttribute("class") ?? ""}"> "${(e.textContent ?? "").trim().slice(0, 40)}"`;
      const rola = (e: Element) => /overflow-x-(auto|scroll)/.test(e.getAttribute("class") ?? "");
      for (const e of document.querySelectorAll("body *")) {
        const r = e.getBoundingClientRect(), s = getComputedStyle(e);
        if (r.width < 2 || r.height < 2 || s.visibility === "hidden" || e.closest("[data-layout-ok]")) continue;
        const pais: Element[] = [];
        for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) pais.push(p);
        if (pais.some(rola)) continue; // dentro de uma faixa que rola, passar da borda é o esperado
        const corte = pais.find((p) => getComputedStyle(p).overflowX !== "visible");
        const limite = Math.min(vw, corte ? corte.getBoundingClientRect().right : vw);
        if (rola(e) && r.right > limite + 1) out.push(`feito para rolar, mas cresceu até o conteúdo e não rola: ${quem(e)}`);
        else if (r.right > vw + 1) out.push(`passa da borda direita da tela: ${quem(e)}`);
        if (s.overflowX !== "visible" && !rola(e) && s.textOverflow !== "ellipsis" && !e.matches("input, textarea, select")
            && e.scrollWidth > e.clientWidth + 1) out.push(`corta o conteúdo, mais largo que ele: ${quem(e)}`);
        if (e.matches("h1, h2, h3") && r.left < 0) out.push(`título cortado na borda esquerda: ${quem(e)}`);
      }
      for (const d of document.querySelectorAll('[role="dialog"]:not([data-layout-ok]), [role="alertdialog"]:not([data-layout-ok])')) {
        const t = document.getElementById(d.getAttribute("aria-labelledby") ?? "") ?? d.querySelector("h1, h2, h3");
        const r = t?.getBoundingClientRect();
        if (!r || r.width < 2 || r.top < 0 || r.left < 0 || r.right > vw + 1 || r.bottom > vh + 1)
          out.push(`diálogo com o título ausente ou fora da área visível: ${quem(d)}`);
      }
      return out;
    });
    expect(falhas, `layout quebrado em ${page.viewportSize()?.width} px`).toEqual([]);
  }
  ```
- **O `DialogContent` do shadcn é um `grid`:** conteúdo largo dentro dele (faixa de botões,
  tabela, linha que rola) precisa de coluna limitada (`grid-cols-[minmax(0,1fr)]`) ou de
  `min-w-0` no filho direto; sem isso a coluna cresce até o conteúdo e a janela corta.
- **Lighthouse e Search Console não rodam no sandbox.** A skill `seo` vale como lista de
  conferência sobre o código.
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
