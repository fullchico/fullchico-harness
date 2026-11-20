# Fatiar a spec em tickets

Um ticket é uma fatia vertical: atravessa as camadas necessárias e entrega algo que
funciona e se testa sozinho. "Criar a tabela", "fazer a API" e "fazer a tela" são camadas,
não fatias. "Usuário troca a foto e vê a nova no perfil" é uma fatia.

- Cada ticket cabe numa sessão de um implementador.
- Um ticket que só prepara o terreno para os outros é legítimo, e bloqueia os que dependem dele.
- Dois tickets que não se bloqueiam serão feitos ao mesmo tempo, por pessoas diferentes.
  Se eles mexem no mesmo arquivo, um deve bloquear o outro.

## Formato

Um arquivo por ticket, em `docs/specs/<slug>/issues/<NN>-<nome>.md`, numerados a partir
de `01`. Nas primeiras linhas, `Status:`, `Blocked by:` e `Owns:`. Os valores de `Status` são
`open`, `claimed` e `done`. `Blocked by:` traz os números dos tickets que precisam estar
concluídos antes, separados por vírgula, ou fica vazio. `Owns:` traz as pastas ou arquivos
que são só deste ticket, separados por vírgula.

## Um dono por arquivo, contrato primeiro

Use a skill `parallel-feature-development` para decidir a posse. Nela, "team-lead" é você, e
os implementadores não trocam mensagens: quem precisa de algo que não é seu relata a lacuna.

- **Posse.** A unidade é o módulo no back e a fatia no front: uma pasta. Dois tickets que
  podem rodar ao mesmo tempo nunca possuem o mesmo caminho. O validador recusa, e na
  integração a branch que mexer fora da posse é recusada.
- **O que é comum tem um ticket só.** O contrato entre front e back, os tipos e regras usados
  por mais de um módulo, as peças de interface de uso geral, os manifestos de dependência e o
  schema do banco pertencem ao ticket de contrato (ou de fundação). É ele que adiciona
  dependência nova. Com `CONTRACT_PATHS` no `harness.conf`, o validador exige que todos os
  outros tickets esperem por ele.
- **Com o contrato fechado, back e front do mesmo recurso rodam juntos:** cada lado testa
  contra o contrato, sem esperar o outro existir.
- **Nada de arquivo central editado por vários.** Registro de módulos, índice geral e schema
  único são do ticket de contrato, ou então são montados por convenção.

```ticket 01-guardar-foto.md
# Guardar a foto enviada

Status: open
Blocked by:
Owns: src/arquivos

## O que entregar

O envio de uma imagem válida grava o arquivo e devolve o endereço dele. Imagem maior que
o limite ou de tipo não aceito é recusada com o erro definido na spec.

## Como validar

Pelo ponto de costura do serviço de arquivos: enviar uma imagem válida, uma grande demais
e uma de tipo errado.

## Arquivos prováveis

O serviço de arquivos e os testes dele.
```

```ticket 02-mostrar-foto-no-perfil.md
# Mostrar a foto nova no perfil

Status: open
Blocked by: 01
Owns: src/perfil

## O que entregar

Depois de trocar a foto, o perfil mostra a nova, sem recarregar a página.

## Como validar

Pelo ponto de costura da tela de perfil, com o serviço de arquivos simulado.

## Arquivos prováveis

A tela de perfil e os testes dela.
```

## Antes de seguir

```bash
python3 -I .harness/tickets_check.py docs/specs/<slug>
```

Tem de responder `ok: N tickets`. Ciclo, referência a ticket que não existe, cabeçalho
faltando, posse sobreposta entre tickets paralelos e ticket que não espera o contrato são
recusados, com o ticket apontado. Corrija e rode de novo.

Faça o commit: `docs(spec): slice <slug> into tickets`.
