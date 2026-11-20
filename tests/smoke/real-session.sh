#!/usr/bin/env bash
# Teste de fumaça com uma sessão real do Claude Code. Gasta tokens (pouco): dois revisores
# em Sonnet sobre um diff de uma linha. Roda fora da suíte; é o portão antes de uma versão.
#
# Confere o que nenhum teste simulado confere: que o hook de fim de subagente grava as
# três aprovações a partir do veredito de revisores de verdade, que o push passa pelo
# portão, e que um commit novo, sem revisão, é barrado.
# Uso: tests/smoke/real-session.sh
set -euo pipefail

HARNESS="$(cd "$(dirname "$0")/../.." && pwd -P)"
WORK="$(cd "$HARNESS/.." && pwd -P)/_smoke-$$"
trap 'rm -rf "$WORK" "$WORK-remote.git"; [ -n "${STATE:-}" ] && rm -rf "$STATE"' EXIT

git init -q --bare "$WORK-remote.git"
mkdir "$WORK" && cd "$WORK"
git init -q -b main
git config user.name Teste && git config user.email teste@example.com
git remote add origin "$WORK-remote.git"
printf '# Projeto\n\nUm projeto de teste.\n' > README.md
python3 -I "$HARNESS/plugin/bin/sync" . --version v0.0.0 >/dev/null
STATE="$(python3 -I .harness/hooks/common.py state-dir)"
git add -A && git -c core.hooksPath=/dev/null commit -qm "chore: adopt harness"
git -c core.hooksPath=/dev/null push -q origin main
git checkout -q -b fix/typo
printf '# Projeto\n\nUm projeto de teste do harness.\n' > README.md
git commit -qam "docs: say what the project tests"
SHA="$(git rev-parse HEAD)" BASE="$(git rev-parse main)"

claude -p "Faça exatamente isto e nada mais: (1) dispare, na mesma mensagem, três subagentes: harness:seguranca e harness:revisor, cada um com o pedido de duas linhas, sem mais nada: 'diff: $BASE...$SHA' e 'commit: $SHA'; e harness:qualidade, com o pedido de uma linha só: 'commit: $SHA'. (2) Espere os três terminarem. (3) Rode o comando .harness/push sozinho, sem encadear. (4) Responda com o veredito de cada revisor e a saída do push." \
  --plugin-dir "$HARNESS/plugin" --model sonnet --permission-mode bypassPermissions > "$WORK/session.log" 2>&1 || true

fail() { echo "FALHOU: $1" >&2; tail -20 "$WORK/session.log" >&2; exit 1; }
for GATE in seguranca revisao qualidade; do
  [ -f "$STATE/approvals/$GATE/$SHA.json" ] || fail "a aprovação de $GATE não foi gravada"
done
git ls-remote origin refs/heads/fix/typo | grep -q "$SHA" || fail "o push não chegou ao remoto"
echo "mais" >> README.md && git commit -qam "docs: add a line"
if .harness/push >/dev/null 2>&1; then fail "um commit sem revisão passou pelo portão"; fi
echo "OK: aprovações gravadas por revisores reais, push aceito, commit sem revisão barrado."
