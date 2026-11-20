# Pendências para a v6

Anotadas durante a v5 (2026-11-20). Nada aqui foi implementado. A v6 roda do zero, com o mesmo
pedido das anteriores.

## Vistas na v5

1. **Revisor não troca o checkout do worktree da feature.** O caçador de bugs rodou
   `git checkout` do commit do implementador dentro do worktree da feature, que ficou em HEAD
   destacado durante a revisão. Voltou sozinho, mas um commit ou uma integração nessa janela
   cairia fora da branch, e revisores em paralelo trocariam o checkout um do outro. Trilho:
   negar a troca de checkout a revisor; para rodar código de outra branch, um worktree
   descartável.
2. **Confiança da pasta do projeto.** Em pasta nunca aberta em modo interativo, o Claude Code
   ignora as permissões `allow` do projeto. O instalador ou o `setup` deve avisar o dono.

## Já listadas antes, ainda não feitas

4. Reabertura e reprovação de contrato contadas, subindo para Opus na segunda.
5. Versão fixada dos plugins de terceiros (`frontend-design`, `ponytail`, `superpowers`).
6. Aviso quando uma skill fixada mudar na origem.
7. Teste por propriedade exigido por máquina nas regras com borda.
8. A skill `shadcn` executa `npx shadcn@latest info --json` ao ser carregada: decidir entre
   aceitar, trocar ou tirar do perfil.

## Adiadas por decisão do dono

- Achado no contrato que "só muda a implementação" seguir sem bloquear a primeira onda. Recusado
  enquanto o foco for qualidade: quem classifica é um modelo, o formato de erro é copiado por
  todos os módulos, e correção no fim é a menos testada. Só volta com classificação por máquina.
- Custo e tempo da entrega (medição da v4 em tokens por papel já feita).
- Vídeo do teste de ponta a ponta no PR.
- Segunda entrega sobre código existente, perfis `livre` e `existente`, memória e aprendizado.
