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

3. **Bloqueio do caçador de bugs por gravidade** (decisão do dono, 2026-11-20). A v5 parou no
   ticket de contrato: quatro reprovações seguidas, cada uma com um achado diferente, e o teto de
   três rodadas encerrou a entrega com zero tickets integrados.
   - Achado **severo** (resultado errado, perda de dado, falha de segurança, quebra o que os
     outros tickets consomem) reprova e bloqueia, como hoje.
   - Achado **simples** não bloqueia: o ticket é integrado e o achado fica aberto como pendência
     registrada, com o teste que o pegaria.
   - **Na ponta, antes do push,** cada pendência aberta é conferida: foi corrigida e tem o teste?
     Pendência sem conferência barra o envio. É o que garante que "deixar passar" não vira "esquecer".
   - O caçador precisa de **critério escrito** para severo e simples, e o registro precisa ser de
     máquina (arquivo por achado, com estado), não opinião solta no relato.
4. **Uma conferência forte no início, em vez de várias repetidas** (validado pelo dono). A v5
   mostrou que uma leitura só não acha tudo (as rodadas 2, 3 e 4 acharam defeito real que a 1
   não viu), mas reler o ticket inteiro a cada rodada não converge, e deixar para o passe final
   é o pior lugar: atenção diluída e correção cara.
   - No ticket de contrato, **dois caçadores em paralelo**, com focos diferentes: comportamento
     (bordas, erros, regras) e "funciona fora da máquina de quem escreveu" (ambiente limpo,
     build, ferramentas). Achados somados, uma rodada de correção.
   - **Depois da correção, o caçador confere só o que foi corrigido** e o que a correção tocou.
     Achado novo e severo ainda barra; achado novo e simples vira pendência (item 3).
   - **O que a máquina checa, a máquina checa:** antes de integrar, a checagem roda numa cópia
     limpa do commit. Dois dos quatro achados da v5 eram desse tipo (contrato não compilado
     antes dos testes; pasta temporária quebrando o lint).
   - **A conferência na ponta é mecânica:** a pendência nasce com o teste que a pegaria; no fim
     pergunta-se só se o teste existe e passa. O passe final não é a rede de segurança principal.
   - Ticket comum: uma leitura completa e depois só a correção. O reforço é do contrato.
5. **Conferência no início se mantém.** O dono gostou de o contrato ser conferido antes de
   qualquer ticket ser construído sobre ele: fica, com os critérios do item 3.
6. **Ticket de contrato menor.** O da v5 carregava contrato, banco, proxy, lint, estrutura de
   testes e ligação dos módulos: sempre sobra uma borda para o revisor. Avaliar dividir em
   contrato (tipos e portas) e fundação (ambiente, ferramentas).
7. **Teto de rodadas não derruba a entrega por achado simples.** Com o item 3 o teto volta a
   contar só reprovação por achado severo.
8. **Loop independente e conferência 360 no fim** (conceito do dono). Depois da entrevista a
   entrega corre sozinha, e só é dada como validada quando tudo estiver pronto: todos os
   tickets, todas as pendências conferidas e os portões da branch inteira.
9. **Versão de teste isolada das anteriores.** A sessão de desenho da v5 leu a spec da
   `teste-v4`, no worktree ao lado, e reaproveitou regras e critérios. Para medir um loop do
   zero, a versão nova não pode enxergar as antigas.

10. **A entrega termina com o app de pé e o link na última mensagem.** A visão do dono
    (2026-11-20): "quero um app de barbearia", a entrevista pergunta, e sai pronto, lembrando
    Replit e Lovable, mas com o código no repositório dele, na arquitetura dele. Hoje a entrega
    termina numa branch enviada. O ambiente (`.harness/up`) já existe: falta o fechamento subir
    o app e informar o endereço.
11. **Entrevista de verdade.** Em todas as versões o pedido foi "não me pergunte nada", então o
    grill-me nunca rodou com o dono respondendo. Testar uma versão em sessão interativa.
12. **Linha de base sem harness.** O mesmo pedido, em worktree limpo, só com as 20 skills e um
    prompt bom, auditado pela régua da v4 e da v5. Sem isso, "o harness entrega mais qualidade"
    é suposição.

Ainda fora do alcance, para a experiência de "pronto": ver a tela (imagem ou preview),
iterar conversando sobre o que já existe, e publicar.

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
