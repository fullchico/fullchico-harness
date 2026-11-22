#!/usr/bin/env python3
"""Escolha do design de um projeto, antes da implementação.

O agente escreve de duas a quatro direções, cada uma numa pasta com:
  index.html   a mesma tela-chave do produto, com o mesmo conteúdo, só com variáveis CSS
  tokens.css   as variáveis em `:root` (claro) e `.dark` (escuro)
  direcao.md   primeira linha: o nome; segunda: a intenção, numa frase

`gallery` monta a vitrine (index.html na pasta das direções) para o dono comparar, com o selo
de leitura calculado aqui, pelo contraste dos tokens: não é o agente que diz se dá para ler.
`choose` grava a escolhida em DESIGN.md na raiz, e recusa direção que não passa no contraste.
"""
import html
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contrast_check  # noqa: E402

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def _direction(folder: str, name: str) -> dict:
    base = os.path.join(folder, name)
    for needed in ("index.html", "tokens.css", "direcao.md"):
        if not os.path.isfile(os.path.join(base, needed)):
            raise ValueError(f"a direção `{name}` está sem {needed}")
    with open(os.path.join(base, "direcao.md"), encoding="utf-8") as f:
        lines = [l.strip().lstrip("# ").strip() for l in f.read().splitlines() if l.strip()]
    with open(os.path.join(base, "tokens.css"), encoding="utf-8") as f:
        css = f.read()
    failed = [i for i in contrast_check.check(css) if i["level"] == "falha"]
    return {"name": name, "title": lines[0] if lines else name, "intent": lines[1] if len(lines) > 1 else "",
            "css": css, "failed": failed}


def directions(folder: str) -> list:
    if not os.path.isdir(folder):
        raise ValueError(f"{folder} não é uma pasta")
    names = sorted(n for n in os.listdir(folder) if NAME.match(n) and os.path.isdir(os.path.join(folder, n)))
    if not 2 <= len(names) <= 4:
        raise ValueError(f"a vitrine tem de 2 a 4 direções; achei {len(names)}. Uma só não é escolha, "
                         "e mais de quatro ninguém compara.")
    return [_direction(folder, n) for n in names]


def _seal(item: dict) -> str:
    if not item["failed"]:
        return '<span class="seal ok">Legível no claro e no escuro</span>'
    worst = min(item["failed"], key=lambda i: i["ratio"])
    where = "escuro" if worst["theme"] == "escuro" else "claro"
    return (f'<span class="seal bad">Texto difícil de ler no tema {where} '
            f'(<code>{html.escape(worst["text"])}</code> sobre <code>{html.escape(worst["on"])}</code>). '
            'Precisa de ajuste antes de ser escolhida.</span>')


PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Escolha o design</title>
<style>
body{margin:0;font:15px/1.5 system-ui,sans-serif;background:#f4f4f5;color:#18181b}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #d4d4d8;padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0 auto 0 0}
button{font:inherit;padding:8px 14px;border:1px solid #71717a;border-radius:8px;background:#fff;color:#18181b;cursor:pointer}
button[aria-pressed=true]{background:#18181b;color:#fff}
button:focus-visible{outline:3px solid #2563eb;outline-offset:2px}
main{display:flex;gap:20px;padding:20px;overflow-x:auto;align-items:flex-start}
section{flex:0 0 auto;width:calc(var(--w,1100px)*var(--s,.55) + 30px);background:#fff;border:1px solid #d4d4d8;border-radius:12px;padding:14px}
h2{font-size:16px;margin:0}
p{margin:4px 0 10px;color:#3f3f46;max-width:60ch}
.seal{display:inline-block;margin-bottom:10px;padding:3px 10px;border-radius:12px;font-size:13px}
.ok{background:#dcfce7;color:#14532d}.bad{background:#fee2e2;color:#7f1d1d}
/* No tamanho de computador a tela é reduzida, para as direções caberem lado a lado. */
.frame{width:calc(var(--w,1100px)*var(--s,.55));height:calc(760px*var(--s,.55));overflow:hidden;border:1px solid #d4d4d8;border-radius:8px}
iframe{display:block;border:0;width:var(--w,1100px);height:760px;background:#fff;transform:scale(var(--s,.55));transform-origin:0 0}
code{font-size:12px}
</style></head><body>
<header><h1>Escolha o design: __COUNT__ direções para a mesma tela</h1>
<button id="theme" aria-pressed="false">Tema escuro</button>
<button id="width" aria-pressed="false">Tamanho de celular</button></header>
<main>__SECTIONS__</main>
<script>
var dark=false,phone=false,frames=document.querySelectorAll('iframe');
function draw(){frames.forEach(function(f){f.src=f.dataset.src+(dark?'?theme=dark':'');});
document.documentElement.style.setProperty('--w',phone?'390px':'1100px');
document.documentElement.style.setProperty('--s',phone?'1':'.55');
document.getElementById('theme').setAttribute('aria-pressed',dark);
document.getElementById('width').setAttribute('aria-pressed',phone);}
document.getElementById('theme').onclick=function(){dark=!dark;draw()};
document.getElementById('width').onclick=function(){phone=!phone;draw()};
draw();
</script></body></html>
"""


def gallery(folder: str) -> str:
    items = directions(folder)
    sections = "".join(
        f'<section><h2>{html.escape(i["title"])} <code>({html.escape(i["name"])})</code></h2>'
        f'<p>{html.escape(i["intent"])}</p>{_seal(i)}'
        f'<div class="frame"><iframe title="{html.escape(i["title"])}" data-src="{html.escape(i["name"])}/index.html">'
        f'</iframe></div></section>'
        for i in items)
    path = os.path.join(folder, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        # escuro e celular: os dois botões da vitrine
        f.write(PAGE.replace("__COUNT__", str(len(items))).replace("__SECTIONS__", sections))
    return path


def choose(root: str, folder: str, name: str) -> str:
    if not NAME.match(name or ""):
        raise ValueError("o nome da direção usa só minúsculas, dígitos e hífen")
    item = _direction(folder, name)
    if item["failed"]:
        raise ValueError("a direção não passa no contraste: " + "; ".join(
            f"`{i['text']}` sobre `{i['on']}` no tema {i['theme']} dá {i['ratio']}:1 (mínimo {i['minimum']}:1)"
            for i in item["failed"]) + ". Ajuste o tokens.css dela e monte a vitrine de novo.")
    path = os.path.join(root, "DESIGN.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Design: {item['title']}\n\n{item['intent']}\n\n"
                "Escolhido pelo dono entre as direções prototipadas. Toda tela segue estes tokens: eles vão\n"
                "para o arquivo de tokens do front (`TOKENS_CSS` no `harness.conf`) e nenhuma tela escreve cor,\n"
                "raio ou sombra fora deles. Mudar o design é mudar este arquivo, por uma entrega.\n\n"
                "## Tokens\n\n```css\n" + item["css"].strip() + "\n```\n")
    return path


def main(argv) -> int:
    usage = "uso: design gallery <pasta das direções> | design choose <pasta das direções> <direção>\n"
    if len(argv) < 3:
        sys.stderr.write(usage)
        return 2
    root, command, folder = argv[0], argv[1], os.path.join(argv[0], argv[2])
    try:
        if command == "gallery" and len(argv) == 3:
            path = gallery(folder)
            print(f"Vitrine montada. Para o dono comparar, ele abre no navegador:\n{path}")
        elif command == "choose" and len(argv) == 4:
            print(f"Design gravado em {choose(root, folder, argv[3])}. Faça o commit dele antes de executar a spec.")
        else:
            sys.stderr.write(usage)
            return 2
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"design: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
