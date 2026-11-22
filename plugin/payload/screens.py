#!/usr/bin/env python3
"""Capturas de tela da entrega: o que o revisor visual abre e o que o dono olha antes do merge.

Quem tira as capturas é a suíte de ponta a ponta do projeto. Ela grava em `SCREENS_DIR`
(chave do `harness.conf`, uma pasta fora do git) os PNGs e um `telas.json`:

  {"commit": "<hash completo do HEAD em que foram tiradas>",
   "telas": [{"arquivo": "agenda-carregada-celular-claro.png", "tela": "Agenda", "estado": "carregada",
              "largura": 390, "altura": 844, "tema": "claro"}, ...]}

`check` confere que as capturas existem, são imagens de verdade e são do commit atual: é o que
o despacho do `harness:revisor-visual` e a aprovação dele exigem. `gallery` monta a página que
o dono abre no navegador. Só lê o repositório; só grava dentro de `SCREENS_DIR`.
"""
import html
import json
import os
import struct
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks"))
import common  # noqa: E402

PHONE_MAX = 480
DESKTOP_MIN = 1024
MIN_BYTES = 100  # menos que isso não é captura: é arquivo vazio ou cortado
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"
HOW = ("Quem tira as capturas é a suíte de ponta a ponta: rode a checagem completa "
       "(`.harness/validate --profile merge`) neste commit e confira de novo.")


def folder(root: str) -> str:
    """A pasta das capturas, sempre dentro do repositório."""
    value = common.read_conf(os.path.join(root, "harness.conf")).get("SCREENS_DIR") or ""
    if not value:
        raise ValueError("o harness.conf não define SCREENS_DIR, a pasta das capturas de tela")
    if os.path.isabs(value) or ".." in value.split("/"):
        raise ValueError(f"SCREENS_DIR ({value}) precisa ser um caminho relativo, dentro do repositório")
    return os.path.join(root, value)


def _png_width(path: str):
    """A largura em pixels, se o arquivo é um PNG inteiro; senão None."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if len(data) < MIN_BYTES or data[:8] != _SIGNATURE or data[12:16] != b"IHDR" or not data.endswith(_END):
        return None
    return struct.unpack(">I", data[16:20])[0]


def load(root: str):
    """(pasta, commit, capturas) do `telas.json`. ValueError diz o que falta."""
    base = folder(root)
    shown = os.path.relpath(base, root)
    if not os.path.isdir(base):
        raise ValueError(f"a pasta das capturas ({shown}) não existe")
    try:
        with open(os.path.join(base, "telas.json"), encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        raise ValueError(f"falta o {shown}/telas.json")
    except ValueError:
        raise ValueError(f"o {shown}/telas.json não é JSON válido")
    shots = data.get("telas") if isinstance(data, dict) else None
    if not isinstance(shots, list) or not shots:
        raise ValueError(f"o {shown}/telas.json não lista nenhuma captura em `telas`")
    for shot in shots:
        name = shot.get("arquivo") if isinstance(shot, dict) else None
        if not isinstance(name, str) or os.path.basename(name) != name or not name.endswith(".png"):
            raise ValueError(f"`arquivo` precisa ser o nome de um PNG dentro de {shown}, sem pasta: {name!r}")
        if not isinstance(shot.get("tela"), str) or not shot["tela"].strip():
            raise ValueError(f"a captura {name} está sem `tela`")
        if not isinstance(shot.get("largura"), int) or isinstance(shot["largura"], bool) or shot["largura"] <= 0:
            raise ValueError(f"a captura {name} está sem `largura` (um inteiro, em pixels)")
    return base, data.get("commit"), shots


def problems(root: str) -> list:
    """O que impede as capturas de valerem para o commit atual. Lista vazia: valem."""
    try:
        base, commit, shots = load(root)
    except ValueError as exc:
        return [str(exc)]
    found = []
    head = common.head_sha(root)
    if commit != head:
        found.append(f"as capturas são de outro commit ({str(commit)[:12]}), e o atual é {str(head)[:12]}")
    for shot in shots:
        path = os.path.join(base, shot["arquivo"])
        if os.path.islink(path) or not os.path.isfile(path):
            found.append(f"o arquivo {shot['arquivo']} está no telas.json e não existe")
            continue
        width = _png_width(path)
        if width is None:
            found.append(f"o arquivo {shot['arquivo']} não é um PNG inteiro")
        elif width < shot["largura"]:
            found.append(f"o arquivo {shot['arquivo']} tem {width} px de largura, menos que os {shot['largura']} declarados")
    if not any(s["largura"] <= PHONE_MAX for s in shots):
        found.append(f"não há captura em largura de celular (até {PHONE_MAX} px)")
    if not any(s["largura"] >= DESKTOP_MIN for s in shots):
        found.append(f"não há captura em largura de computador (a partir de {DESKTOP_MIN} px)")
    return found


PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Telas da entrega</title>
<style>
body{margin:0;font:15px/1.5 system-ui,sans-serif;background:#f4f4f5;color:#18181b}
header{position:sticky;top:0;z-index:1;background:#fff;border-bottom:1px solid #d4d4d8;padding:12px 20px}
h1{font-size:17px;margin:0}
header p{margin:2px 0 0;color:#3f3f46}
main{padding:20px;display:grid;gap:20px}
section{background:#fff;border:1px solid #d4d4d8;border-radius:12px;padding:14px;min-width:0}
h2{font-size:16px;margin:0 0 6px}
h3{font-size:14px;margin:14px 0 8px;color:#3f3f46}
.row{display:flex;gap:16px;overflow-x:auto;align-items:flex-start;padding-bottom:8px}
figure{margin:0;flex:0 0 auto}
figure.phone{width:240px}figure.desktop{width:560px}
img{display:block;width:100%;height:auto;border:1px solid #d4d4d8;border-radius:8px;background:#fff}
a:focus-visible{outline:3px solid #2563eb;outline-offset:2px}
figcaption{margin-top:6px;font-size:13px;color:#3f3f46}
code{font-size:12px}
</style></head><body>
<header><h1>Telas da entrega: __COUNT__ capturas</h1>
<p>Tiradas pela suíte de ponta a ponta no commit <code>__COMMIT__</code>. Olhe cada uma, no celular e no
computador, no claro e no escuro, antes de fazer o merge. Clique para ver no tamanho real.</p></header>
<main>__SECTIONS__</main>
</body></html>
"""


def _figure(shot: dict) -> str:
    esc = lambda v: html.escape(str(v), quote=True)
    phone = shot["largura"] <= PHONE_MAX
    size = f"{shot['largura']}×{shot['altura']}" if shot.get("altura") else f"{shot['largura']} px"
    caption = " · ".join(str(p) for p in (shot["tela"], shot.get("estado"), "celular" if phone else "computador",
                                          size, shot.get("tema")) if p)
    return (f'<figure class="{"phone" if phone else "desktop"}"><a href="{esc(shot["arquivo"])}">'
            f'<img src="{esc(shot["arquivo"])}" alt="{esc(caption)}" loading="lazy"></a>'
            f'<figcaption>{esc(caption)}</figcaption></figure>')


def gallery(root: str) -> str:
    base, commit, shots = load(root)
    screens = {}
    for shot in shots:  # na ordem em que a suíte tirou
        screens.setdefault(shot["tela"], {}).setdefault(shot.get("estado") or "", []).append(shot)
    order = lambda s: (s["largura"], s.get("tema") != "claro", str(s.get("tema")))  # celular antes; claro antes
    sections = "".join(
        f"<section><h2>{html.escape(name)}</h2>" + "".join(
            (f"<h3>{html.escape(state)}</h3>" if state else "")
            + '<div class="row">' + "".join(_figure(s) for s in sorted(group, key=order)) + "</div>"
            for state, group in states.items()) + "</section>"
        for name, states in screens.items())
    path = os.path.join(base, "index.html")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__COUNT__", str(len(shots))).replace("__COMMIT__", html.escape(str(commit)[:10]))
                .replace("__SECTIONS__", sections))
    os.replace(tmp, path)
    return path


def main(argv) -> int:
    usage = "uso: screens check | screens gallery\n"
    if len(argv) != 2 or argv[1] not in ("check", "gallery"):
        sys.stderr.write(usage)
        return 2
    root = argv[0]
    found = problems(root)
    if argv[1] == "check":
        if found:
            sys.stderr.write("screens: as capturas de tela não valem para este commit:\n"
                             + "".join(f"  - {item}\n" for item in found) + HOW + "\n")
            return 1
        print("screens: as capturas são do commit atual, em celular e computador.")
        return 0
    try:
        path = gallery(root)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"screens: {exc}\n{HOW}\n")
        return 1
    if found:  # a galeria sai mesmo assim: o dono vê o que há, sabendo de que commit é
        sys.stderr.write("screens: atenção, estas capturas não valem para o commit atual:\n"
                         + "".join(f"  - {item}\n" for item in found))
    print(f"Galeria montada. Para o dono olhar as telas, ele abre no navegador:\n{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
