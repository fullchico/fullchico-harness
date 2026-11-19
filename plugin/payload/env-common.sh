# Trecho comum dos scripts de ambiente. Lido com `.`, não executado.
# Define HERE, ROOT e as funções abaixo. Não grava nada em .harness/.
#
# Todo Python chamado pelos scripts do harness usa `python3 -I` (modo isolado). Vários
# deles rodam fora do sandbox com a raiz do projeto como pasta atual, e sem o -I um
# json.py plantado ali pelo agente seria importado no lugar do módulo de verdade.

HERE="$(cd "$(dirname "$0")" && pwd -P)"
ROOT="$(cd "$HERE/.." && pwd -P)"

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

conf_get() {  # chave do harness.conf, vazio se não houver
  python3 -I - "$HERE/hooks" "$ROOT/harness.conf" "$1" <<'PY'
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import common
print(common.read_conf(sys.argv[2]).get(sys.argv[3], ""))
PY
}

env_get() {  # chave do .env do worktree, vazio se não houver
  [ -f "$ROOT/.env" ] || return 0
  sed -n "s/^$1=//p" "$ROOT/.env" | sed -n 1p
}

load_env() {  # exporta o .env do worktree para os comandos do projeto
  [ -f "$ROOT/.env" ] || return 0
  local line key
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"
    case "$key" in *[!A-Za-z0-9_]*|'') continue ;; esac
    export "$key=${line#*=}"
  done < "$ROOT/.env"
}

need_compose() {  # confere o que os comandos de Docker precisam e define COMPOSE_FILE
  COMPOSE_FILE="$(conf_get COMPOSE_FILE)"
  [ -n "$COMPOSE_FILE" ] || die "falta COMPOSE_FILE no harness.conf (o arquivo de compose do ambiente de desenvolvimento)."
  [ -f "$ROOT/$COMPOSE_FILE" ] || die "o arquivo de compose $COMPOSE_FILE não existe neste worktree."
  command -v docker >/dev/null 2>&1 || die "docker não encontrado no PATH. Instale ou inicie o Docker."
}

compose() {  # docker compose do projeto desta feature
  docker compose --env-file "$ROOT/.env" -p "$(env_get COMPOSE_PROJECT_NAME)" -f "$ROOT/$COMPOSE_FILE" "$@"
}

env_record() {  # arquivo que registra o dono do ambiente desta feature
  local state
  state="$(cd "$ROOT" && python3 -I "$HERE/hooks/common.py" state-dir)" || die "não achei o estado do harness."
  echo "$state/envs/$(env_get HARNESS_ENV_CONTEXT).json"
}

dev_pid() {  # PID do app em segundo plano, se ainda estiver vivo
  local pid
  [ -f "$ROOT/.harness-run/dev.pid" ] || return 1
  pid="$(cat "$ROOT/.harness-run/dev.pid")"
  # Só número positivo: `kill -1` alcançaria todos os processos do usuário.
  case "$pid" in ""|0|*[!0-9]*) return 1 ;; esac
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || return 1
  echo "$pid"
}
