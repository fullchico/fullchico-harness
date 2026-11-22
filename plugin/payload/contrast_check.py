#!/usr/bin/env python3
"""Contraste dos tokens de cor, pela razão da WCAG 2.x, no tema claro e no escuro.

A direção visual de um projeto é um conjunto de tokens, e o que reprova em acessibilidade
depois já está decidido neles. Esta checagem roda antes de existir tela (na escolha do
design) e de novo a cada `validate`. É Python puro: não usa pacote do projeto nem rede.

Lê as variáveis CSS de `:root` (claro) e `.dark` (escuro). Texto precisa de 4,5:1 sobre o
fundo dele; o anel de foco, de 3:1 sobre o fundo da página. Borda fraca é só aviso.

Uso: contrast_check.py <arquivo.css>
Sai 0 se passa, 1 se algum par reprova, 2 se o arquivo não existe ou não tem tokens de cor.
"""
import math
import re
import sys

sys.dont_write_bytecode = True

TEXT, FOCUS = 4.5, 3.0
_NUM = r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?"


def _part(token: str, scale: float = 1.0) -> float:
    token = token.strip()
    if token.endswith("%"):
        return float(token[:-1]) / 100.0 * scale
    return float(re.sub(r"(deg|rad|turn)$", "", token))


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _encoded(channel: float) -> float:
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _oklch(l, c, h):
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_, m_, s_ = l + 0.3963377774 * a + 0.2158037573 * b, l - 0.1055613458 * a - 0.0638541728 * b, \
        l - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
           -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
           -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3)
    return tuple(_encoded(min(1.0, max(0.0, v))) for v in rgb)


def _hsl(h, s, l):
    def channel(n):
        k = (n + h / 30.0) % 12
        return l - s * min(l, 1 - l) * max(-1, min(k - 3, 9 - k, 1))
    return tuple(channel(n) for n in (0, 8, 4))


def color(text):
    """A cor como (r, g, b, alfa), em sRGB como o navegador a guarda, ou None se o valor não é uma cor."""
    text = text.strip().lower()
    try:
        m = re.fullmatch(r"#([0-9a-f]{3,8})", text)
        if m and len(m.group(1)) in (3, 4, 6, 8):
            digits = m.group(1)
            if len(digits) < 6:
                digits = "".join(d * 2 for d in digits)
            values = [int(digits[i:i + 2], 16) / 255.0 for i in range(0, len(digits), 2)]
            return (*values[:3], values[3] if len(values) == 4 else 1.0)
        m = re.fullmatch(r"(oklch|rgba?|hsla?)\((.*)\)", text)
        if m:
            kind, body = m.group(1), m.group(2)
            body, _, alpha = body.partition("/")
            parts = [p for p in re.split(r"[\s,]+", body.strip()) if p]
            if not alpha and len(parts) == 4:
                alpha = parts.pop()
            a = _part(alpha) if alpha.strip() else 1.0
            if len(parts) != 3:
                return None
            if kind == "oklch":
                return (*_oklch(_part(parts[0]), _part(parts[1], 0.4), _part(parts[2])), a)
            if kind.startswith("rgb"):
                return (*(_part(p, 255.0) / 255.0 for p in parts), a)
            return (*_hsl(_part(parts[0]), _part(parts[1]), _part(parts[2])), a)
        m = re.fullmatch(rf"({_NUM})(?:deg)?\s+({_NUM})%\s+({_NUM})%", text)  # HSL solto, do shadcn antigo
        if m:
            return (*_hsl(float(m.group(1)), float(m.group(2)) / 100, float(m.group(3)) / 100), 1.0)
    except ValueError:
        return None
    return None


def _over(top, bottom):
    """A cor de cima composta sobre a de baixo, quando tem transparência. Em sRGB, como o navegador mistura."""
    alpha = top[3]
    return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3)) + (1.0,)


def ratio(a, b) -> float:
    def luminance(c):
        return 0.2126 * _linear(c[0]) + 0.7152 * _linear(c[1]) + 0.0722 * _linear(c[2])
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _block(css: str, selector: str) -> dict:
    found = {}
    for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", css):
        for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1)):
            found[name] = value.strip()
    return found


def _resolve(tokens: dict, name: str, depth: int = 0):
    value = tokens.get(name)
    if value is None or depth > 8:
        return None
    ref = re.fullmatch(r"var\(--([\w-]+)\)", value)
    return _resolve(tokens, ref.group(1), depth + 1) if ref else color(value)


def check(css: str) -> list:
    """Os pares de tokens que não chegam ao mínimo. `level` é `falha` ou `aviso`."""
    light = _block(css, ":root")
    themes = [("claro", light)]
    dark = _block(css, ".dark")
    if dark:
        themes.append(("escuro", {**light, **dark}))
    found, measured = [], 0
    for theme, tokens in themes:
        page = _resolve(tokens, "background")
        if page is None:
            continue
        page = _over(page, (1.0, 1.0, 1.0, 1.0))
        pairs = [(name, name[:-len("-foreground")], TEXT, "falha") for name in tokens if name.endswith("-foreground")]
        pairs += [("foreground", "background", TEXT, "falha"), ("muted-foreground", "background", TEXT, "falha"),
                  ("ring", "background", FOCUS, "falha"), ("border", "background", FOCUS, "aviso"),
                  ("input", "background", FOCUS, "aviso")]
        for text, on, minimum, level in pairs:
            front, back = _resolve(tokens, text), _resolve(tokens, on)
            if front is None or back is None:
                continue
            back = _over(back, page)
            value = ratio(_over(front, back), back)
            measured += 1
            if value < minimum:
                found.append({"theme": theme, "text": text, "on": on, "ratio": round(value, 2),
                              "minimum": minimum, "level": level})
    if not measured:
        raise ValueError("nenhum par de tokens de cor encontrado em `:root`")
    return found


def _br(number: float) -> str:
    return f"{number:.2f}".replace(".", ",").rstrip("0").rstrip(",")


def main(argv) -> int:
    if len(argv) != 1:
        sys.stderr.write("uso: contrast_check.py <arquivo.css>\n")
        return 2
    try:
        with open(argv[0], encoding="utf-8") as f:
            css = f.read()
        found = check(css)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"contraste: {exc}\n")
        return 2
    for item in found:
        out = sys.stderr if item["level"] == "falha" else sys.stdout
        out.write(f"contraste ({item['level']}, tema {item['theme']}): `{item['text']}` sobre `{item['on']}` dá "
                  f"{_br(item['ratio'])}:1; o mínimo é {_br(item['minimum'])}:1\n")
    failed = [i for i in found if i["level"] == "falha"]
    if failed:
        sys.stderr.write("contraste: escureça ou clareie o token até passar. Texto ilegível não se resolve na tela.\n")
        return 1
    print("contraste: os tokens passam no claro e no escuro" if _block(css, ".dark")
          else "contraste: os tokens passam (só há tema claro)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
