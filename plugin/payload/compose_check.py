#!/usr/bin/env python3
"""Confere a configuração final do compose antes de o ambiente subir.

O `up` roda fora do sandbox do Bash, e o Docker monta qualquer pasta da máquina
num contêiner. Sem esta checagem, bastaria editar o compose do projeto para um
contêiner escrever fora dele. A entrada é o JSON que o próprio Docker devolve em
`docker compose config --format json`, já com variáveis e caminhos resolvidos.

O app do projeto pode rodar num contêiner que monta a pasta do projeto: lá dentro ele
fica fora do sandbox do Bash. Para o código do projeto não alcançar os trilhos por esse
caminho, `--protect` devolve um compose complementar que monta cada trilho só para leitura.

Uso: compose_check.py <raiz do projeto> [--summary | --protect] < config.json
Sai 0 se pode subir; sai 1 com os motivos em stderr.
"""
import json
import os
import posixpath
import sys

sys.dont_write_bytecode = True

# A checagem parte do que é permitido, não do que é perigoso: o formato do compose
# tem campos demais que dão acesso à máquina para tentar listar todos os ruins.
# Campo fora destas listas é recusado, com o nome dele, para o dono decidir.
PLAIN_FIELDS = {
    "image", "command", "entrypoint", "environment", "ports", "expose", "networks", "depends_on",
    "healthcheck", "restart", "container_name", "hostname", "domainname", "working_dir", "user",
    "labels", "annotations", "init", "tty", "stdin_open", "read_only", "platform", "profiles",
    "pull_policy", "stop_grace_period", "stop_signal", "tmpfs", "ulimits", "shm_size", "mem_limit",
    "mem_reservation", "cpus", "cpu_shares", "logging", "extra_hosts", "dns", "dns_search", "links",
    "attach", "scale", "deploy",
}
CHECKED_FIELDS = {"volumes", "build", "env_file", "secrets", "configs", "privileged", "pid", "ipc",
                  "network_mode", "cap_add", "devices"}
HOST_NAMESPACES = ("pid", "ipc")
BUILD_FIELDS = {"context", "dockerfile", "args", "target", "additional_contexts", "labels", "cache_from",
                "platforms", "tags", "pull", "no_cache", "network", "shm_size", "dockerfile_inline"}
# O que o sandbox do Bash não deixa o agente gravar (templates/settings.json), mais o `.git`.
RAILS = (".harness", "harness.conf", "harness.d", ".claude", "skills-lock.json", "CLAUDE.md",
         "docs/agents", "orca.yaml", ".conductor", ".git")


def _writable_binds(service):
    for volume in service.get("volumes") or [] if isinstance(service, dict) else []:
        if isinstance(volume, dict) and volume.get("type") == "bind" and not volume.get("read_only"):
            yield os.path.realpath(str(volume.get("source", ""))), str(volume.get("target", ""))


def _rails(root: str):
    base = os.path.realpath(root)
    return [os.path.join(base, rail) for rail in RAILS if os.path.lexists(os.path.join(base, rail))]


def protection(config, root: str) -> dict:
    """Compose complementar: cada trilho dentro de uma pasta montada com escrita entra só para leitura."""
    services = {}
    for name, service in (_services(config) or {}).items():
        mounts = [{"type": "bind", "source": rail, "target": posixpath.join(target, os.path.relpath(rail, source)),
                   "read_only": True}
                  for source, target in _writable_binds(service)
                  for rail in _rails(root) if rail.startswith(source + os.sep)]
        if mounts:
            services[name] = {"volumes": mounts}
    return {"services": services} if services else {}


def _inside(path: str, root: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    git_dir = os.path.join(base, ".git")
    if real == git_dir or real.startswith(git_dir + os.sep):
        return False
    return real == base or real.startswith(base + os.sep)


def _services(config):
    services = config.get("services") if isinstance(config, dict) else None
    return services if isinstance(services, dict) and services else None


def _named_volume(config, name: str):
    """Motivo para recusar um volume nomeado, ou None. Só o volume local simples passa."""
    declared = (config.get("volumes") or {}).get(name)
    if declared is None:
        return None
    if not isinstance(declared, dict):
        return "em formato inesperado"
    if declared.get("external"):
        return "é externo ao compose"
    if declared.get("driver") not in (None, "local"):
        return f"usa o driver {declared.get('driver')}"
    if declared.get("driver_opts"):
        return "tem opções de driver, que podem apontar para uma pasta da máquina"
    return None


def _build(name: str, build, root: str) -> list:
    if isinstance(build, str):
        build = {"context": build}
    if not isinstance(build, dict):
        return [f"serviço {name}: build em formato inesperado"]
    found = [f"serviço {name}: build usa {key}, que não é permitido" for key in build if key not in BUILD_FIELDS]
    context = str(build.get("context", ""))
    if not _inside(context, root):
        found.append(f"serviço {name}: o build lê uma pasta de fora do projeto ({context})")
    dockerfile = build.get("dockerfile")
    if dockerfile and not _inside(os.path.join(context, str(dockerfile)), root):
        found.append(f"serviço {name}: o Dockerfile fica fora do projeto ({dockerfile})")
    extra = build.get("additional_contexts") or {}
    for value in (extra.values() if isinstance(extra, dict) else extra):
        if not _inside(str(value), root):
            found.append(f"serviço {name}: o build lê um contexto de fora do projeto ({value})")
    return found


def _service(name: str, service: dict, config: dict, root: str) -> list:
    found = [f"serviço {name}: o campo {key} não está entre os permitidos" for key in service
             if key not in PLAIN_FIELDS and key not in CHECKED_FIELDS]
    volumes = service.get("volumes") or []
    if not isinstance(volumes, list):
        found.append(f"serviço {name}: volumes em formato inesperado")
        volumes = []
    for volume in volumes:
        kind = volume.get("type") if isinstance(volume, dict) else None
        if kind == "bind":
            if not _inside(str(volume.get("source", "")), root):
                found.append(f"serviço {name}: monta uma pasta de fora do projeto ({volume.get('source')})")
        elif kind == "volume":
            reason = _named_volume(config, str(volume.get("source", "")))
            if reason:
                found.append(f"serviço {name}: o volume {volume.get('source')} {reason}")
        elif kind != "tmpfs":
            found.append(f"serviço {name}: volume de tipo não permitido ({kind})")
    for source, _ in _writable_binds(service):
        if _inside(source, root) and any(source == rail or source.startswith(rail + os.sep) for rail in _rails(root)):
            found.append(f"serviço {name}: monta com escrita um trilho do harness ({source})")
    if "build" in service:
        found += _build(name, service["build"], root)
    for entry in service.get("env_file") or []:
        path = entry.get("path") if isinstance(entry, dict) else entry
        if not _inside(str(path), root):
            found.append(f"serviço {name}: lê um arquivo de variáveis de fora do projeto ({path})")
    if service.get("privileged"):
        found.append(f"serviço {name}: contêiner privilegiado")
    for key in HOST_NAMESPACES:
        if service.get(key) not in (None, "", "private", "shareable"):
            found.append(f"serviço {name}: usa {key} de fora do contêiner ({service.get(key)})")
    mode = service.get("network_mode")
    if mode not in (None, "", "bridge", "none") and not str(mode).startswith("service:"):
        found.append(f"serviço {name}: network_mode {mode} não é permitido")
    if service.get("cap_add"):
        found.append(f"serviço {name}: pede capacidades extras ({', '.join(map(str, service['cap_add']))})")
    if service.get("devices"):
        found.append(f"serviço {name}: acessa dispositivos da máquina")
    return found


def violations(config, root: str) -> list:
    services = _services(config)
    if services is None:
        return ["configuração do compose sem serviços, ou em formato inesperado"]
    found = []
    for name, service in services.items():
        if not isinstance(service, dict):
            found.append(f"serviço {name}: definição em formato inesperado")
            continue
        found += _service(name, service, config, root)
    for kind in ("secrets", "configs"):
        declared = config.get(kind) or {}
        for name, item in (declared.items() if isinstance(declared, dict) else []):
            if not isinstance(item, dict) or item.get("external"):
                found.append(f"{kind} {name}: é externo ao compose ou está em formato inesperado")
            elif item.get("file") and not _inside(str(item["file"]), root):
                found.append(f"{kind} {name}: lê um arquivo de fora do projeto ({item['file']})")
    return found


def summary(config, root: str) -> str:
    services = _services(config) or {}
    base = os.path.realpath(root)
    lines = []
    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        parts = [str(service.get("image") or "build local")]
        ports = [str(p.get("published")) for p in service.get("ports") or [] if isinstance(p, dict) and p.get("published")]
        if ports:
            parts.append("portas " + ", ".join(ports))
        mounts = []
        for volume in service.get("volumes") or []:
            if isinstance(volume, dict) and volume.get("type") == "bind":
                real = os.path.realpath(str(volume.get("source", "")))
                mounts.append(os.path.relpath(real, base) if _inside(real, root) else "FORA DO PROJETO")
        if mounts:
            parts.append("monta " + ", ".join(mounts))
        lines.append(f"{name}: " + " · ".join(parts))
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("uso: compose_check.py <raiz> [--summary]\n")
        return 1
    try:
        config = json.load(sys.stdin)
    except ValueError:
        sys.stderr.write("compose_check: a configuração do compose não é um JSON válido.\n")
        return 1
    if "--summary" in sys.argv[2:]:
        print(summary(config, sys.argv[1]))
        return 0
    if "--protect" in sys.argv[2:]:
        print(json.dumps(protection(config, sys.argv[1])))
        return 0
    found = violations(config, sys.argv[1])
    for item in found:
        sys.stderr.write(f"ambiente recusado: {item}\n")
    if found:
        sys.stderr.write("O ambiente só sobe com contêineres que enxergam apenas a pasta do projeto.\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
