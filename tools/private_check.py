#!/usr/bin/env python3
"""Confere uma pasta que vai a público contra padrões genéricos (caminho de pasta pessoal, e-mail pessoal) e contra
a lista de termos privados. Uso: private_check.py <pasta> <arquivo de termos>. Sai com 1 se achar algo."""
import os, re, sys
dest, terms_file = sys.argv[1], sys.argv[2]
terms = [t.strip().lower() for t in open(terms_file, encoding="utf-8") if t.strip() and not t.startswith("#")]
generic = [re.compile(r"/Users/[a-z]|/home/[a-z]"), re.compile(r"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.\w+", re.I)]
found = []
for folder, dirs, files in os.walk(dest):
    dirs[:] = [d for d in dirs if d != ".git"]
    for name in files:
        if name == ".git":
            continue  # num worktree, `.git` é um arquivo que aponta para a pasta do repositório
        path = os.path.join(folder, name)
        rel = os.path.relpath(path, dest)
        text = open(path, encoding="utf-8", errors="ignore").read()
        low = (rel + "\n" + text).lower()
        for term in terms:
            if term in low:
                found.append(f"{rel}: termo privado")
        if rel != os.path.join("tests", "test_package.py"):
            for pattern in generic:
                if pattern.search(text):
                    found.append(f"{rel}: caminho ou e-mail pessoal")
for line in sorted(set(found)):
    print("  " + line, file=sys.stderr)
if found:
    print("export-public: conteúdo pessoal no que iria a público.", file=sys.stderr)
sys.exit(1 if found else 0)
