# Memória do harness entre Claude e Codex

## Viabilidade

É possível manter uma memória de projeto que Claude e Codex consultem e atualizem. O plugin `memoria` já usa `harness-memory` dentro do **diretório Git comum**, fora dos arquivos versionados, e injeta seu índice no início das sessões das duas ferramentas. As skills de mapa, dream e aprendizado também existem nas duas instalações.

Isso não significa que as **memórias nativas** sejam uma só. Claude mantém sua memória automática por projeto em `~/.claude/projects/<projeto>/memory/` e pode escrevê-la durante a sessão. Codex mantém memórias locais sob `CODEX_HOME`, quando o recurso está ativo, e pode gerá-las depois que a sessão ficar ociosa. O Codex documenta esses arquivos como estado gerado e desaconselha a edição direta como mecanismo principal. Logo, uma cópia bidirecional automática entre diretórios nativos seria frágil e poderia criar duplicatas ou conflitos.

## Fonte canônica

O harness deve ter a própria memória, compartilhada por Claude e Codex, **sem versionar os dados de memória**. Cada nota deve conter assunto, conteúdo curto, origem (`claude`, `codex`, usuário ou código), referências a caminhos do projeto, commit de referência e estado de atualização. Regras obrigatórias e estáveis pertencem aos arquivos de instrução do projeto; a memória carrega fatos, decisões e aprendizados revisáveis.

O Git dá identidade e sinal de mudança: `git ls-files` descobre arquivos rastreados, caminhos e commits ancoram as notas, e `git diff` indica quais âncoras mudaram. O commit é uma **referência de validade**, não um pedido para fazer commit da memória. A descrição curta de cada unidade ajuda o agente a localizar o contexto certo antes de abrir arquivos grandes.

## Grafo e busca leve

O grafo liga **unidade de código → arquivo → nota → termo/decisão → commit de referência**. As arestas são índices locais derivados dos registros existentes (`map.json`, `notes.json`, `anchors.json`); podem ser reconstruídas sem alterar o repositório. A consulta começa por caminhos do ticket, arquivos tocados e termos da demanda; percorre apenas os vizinhos relevantes e devolve resumos curtos com referências. O agente abre o detalhe sob demanda.

Na primeira etapa, basta um índice invertido por caminho e termo, com busca lexical e travessia limitada. Não é necessário banco externo nem vetor de embeddings para recuperar relações explícitas entre código e notas. Limites de tamanho e de resultados mantêm o início da sessão rápido. Quando o Git indicar alteração em uma âncora, o item aparece como envelhecido e volta para revisão via `mapear` ou `dream`.

## Fluxo de atualização

1. Claude ou Codex produz um candidato de memória ao terminar uma tarefa, em `dream/aprender`, ou por pedido explícito do usuário.
2. O harness compara com notas existentes, verifica evidência e identifica conflito ou obsolescência.
3. A nota confirmada entra na memória canônica com escrita atômica e registro de origem.
4. No início da próxima sessão, o hook de cada plataforma injeta apenas um índice curto; a busca no grafo recupera detalhes e referências sob demanda.
5. `memoria check` mostra itens envelhecidos; `memoria graph rebuild` e `memoria graph search` atualizam e consultam o grafo local. Comandos próprios para revisar conflitos podem ser adicionados depois.

Pode haver **importação assistida** de memórias nativas relevantes, com revisão e desduplicação, mas a sincronização não depende de acesso direto aos formatos internos. A memória nativa de cada ferramenta continua funcionando para preferências pessoais. O harness nunca presume que uma nota nativa foi salva imediatamente nem que ela será carregada por todos os subagentes.

## Limites atuais

O armazenamento não versionado, as âncoras em Git, a detecção de envelhecimento por `git diff`, a injeção de contexto e a consulta ao Graphify local já existem. A skill do Graphify acompanha o plugin `memoria` em Claude e Codex. Ainda faltam um registro uniforme de proveniência, revisão de conflitos e importação assistida de memórias nativas. A atualização bidirecional das memórias nativas não está implementada.
