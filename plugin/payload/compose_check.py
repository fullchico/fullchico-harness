#!/usr/bin/env python3
"""Confere a configuração final do compose antes de o ambiente subir.

O `up` roda fora do sandbox do Bash, e o Docker monta qualquer pasta da máquina
num contêiner. Sem esta checagem, bastaria editar o compose do projeto para um
contêiner escrever fora dele. A entrada é o JSON que o próprio Docker devolve em
`docker compose config --format json`, já com variáveis e caminhos resolvidos.

Uso: compose_check.py <raiz do projeto> [--summary] < config.json
Sai 0 se pode subir; sai 1 com os motivos em stderr.
"""
import json
import os
import sys

sys.dont_write_bytecode = True

HOST_NAMESPACES = ("pid", "ipc", "network_mode")


def _inside(path: str, root: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    git_dir = os.path.join(base, ".git")
    if real == git_dir or real.startswith(git_dir + os.sep):
        return False
    return real == base or real.startswith(base + os.sep)


def _services(config):
    services = config.get("services") if isinstance(config, dict) else None
    return services if isinstance(services, dict) and services else None


def violations(config, root: str) -> list:
    services = _services(config)
    if services is None:
        return ["configuração do compose sem serviços, ou em formato inesperado"]
    found = []
    for name, service in services.items():
        if not isinstance(service, dict):
            found.append(f"serviço {name}: definição em formato inesperado")
            continue
        volumes = service.get("volumes") or []
        if not isinstance(volumes, list):
            found.append(f"serviço {name}: volumes em formato inesperado")
            volumes = []
        for volume in volumes:
            if not isinstance(volume, dict):
                found.append(f"serviço {name}: volume em formato inesperado")
            elif volume.get("type") == "bind" and not _inside(str(volume.get("source", "")), root):
                found.append(f"serviço {name}: monta uma pasta de fora do projeto ({volume.get('source')})")
        if service.get("privileged"):
            found.append(f"serviço {name}: contêiner privilegiado")
        for key in HOST_NAMESPACES:
            if service.get(key) == "host":
                found.append(f"serviço {name}: usa {key} da máquina")
        if service.get("cap_add"):
            found.append(f"serviço {name}: pede capacidades extras ({', '.join(map(str, service['cap_add']))})")
        if service.get("devices"):
            found.append(f"serviço {name}: acessa dispositivos da máquina")
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
    found = violations(config, sys.argv[1])
    for item in found:
        sys.stderr.write(f"ambiente recusado: {item}\n")
    if found:
        sys.stderr.write("O ambiente só sobe com contêineres que enxergam apenas a pasta do projeto.\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
