# Documentos de domínio

Contexto único: um glossário e um conjunto de ADRs para o repositório inteiro.

- `GLOSSARY.md`, na raiz: vocabulário do domínio. Use esses termos em código,
  specs, tickets e interface. É um glossário e nada mais: sem detalhe de
  implementação.
- `docs/adr/NNNN-slug.md`: decisões de arquitetura difíceis de reverter,
  numeradas em sequência.

Cada termo do glossário traz também o nome em inglês usado no código: o código é em inglês,
e é pelo glossário que se sabe qual palavra usar.

Antes de trabalhar numa área, leia o glossário e os ADRs que a tocam. Termo novo
de domínio entra no glossário na mesma mudança que o introduz.
