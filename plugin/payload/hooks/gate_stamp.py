#!/usr/bin/env python3
"""SubagentStop: grava a aprovação de um portão a partir do veredito do revisor.

Nenhum agente carimba. Este hook lê a resposta final do subagente e só grava
quando o subagente é um revisor do harness, o veredito é APPROVED e o commit
revisado é o topo atual. Nunca bloqueia: na dúvida, não carimba e sai 0.
"""
import datetime
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

AGENT_GATE = {"harness:seguranca": "seguranca", "harness:revisor": "revisao", "harness:qualidade": "qualidade",
              "harness:revisor-bugs": "bugs", "harness:revisor-ambiente": "ambiente",
              "harness:revisor-visual": "visual"}
HANDBACK_TOOL = "SubagentHandback"
_VERDICT = re.compile(r"^VEREDITO: (APPROVED|REJECTED)$")
_COMMIT = re.compile(r"^COMMIT: ([0-9a-f]{40})$")
_RESUMO = re.compile(r"^RESUMO: (\S.*)$")


_PENDING = re.compile(r"^PENDENCIA: (\S.*)$")
_RESOLVED = re.compile(r"^RESOLVIDA: (P[0-9]+)$")
# Pendência é exceção. Um ticket aprovado com mais que isso não está pronto: a aprovação não é
# gravada, e o que foi apontado vira o achado de uma rodada de correção.
MAX_PENDINGS = 2


def _spot(text):
    """O ponto do código a que a pendência se refere (`arquivo:linha`), se ela começa por ele."""
    first = text.split()[0] if text.split() else ""
    return first if re.match(r"^[\w./@-]+:\d+$", first) else None


def new_pendings(message, known):
    """As pendências desta resposta que ainda não estão registradas: mesmo texto ou mesmo ponto não conta de novo."""
    fresh = []
    for raw in message.splitlines():
        m = _PENDING.match(raw.strip())
        if not m:
            continue
        text = m.group(1).strip()
        spots = {_spot(i["text"]) for i in known + fresh if i["status"] == "open"} - {None}
        if any(i["text"] == text for i in known + fresh) or _spot(text) in spots:
            continue
        fresh.append({"text": text, "status": "open"})
    return fresh


def too_many_pendings(cwd, message, ticket) -> bool:
    """O teto é do ticket: soma o que já está aberto nele, de qualquer revisor e de qualquer rodada."""
    known = common.pendings(cwd)
    already = sum(1 for i in known if i["status"] == "open" and ticket and i.get("ticket") == ticket)
    return already + len(new_pendings(message, known)) > MAX_PENDINGS


def track_pendings(cwd, message, verdict, ticket=None):
    """O caçador de bugs, o revisor de ambiente e o revisor visual abrem pendência para achado simples e a fecham
    quando conferem a correção.

    Pendência só nasce de uma revisão aprovada: se ele reprovou, tudo o que apontou vai para a
    rodada de correção. Fechar vale em qualquer veredito.
    """
    folder = common.pendings_dir(cwd)
    if not folder:
        return
    known = common.pendings(cwd)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for raw in message.splitlines():
        line = raw.strip()
        closed = _RESOLVED.match(line)
        if closed:
            for item in known:
                if item["id"] == closed.group(1) and item["status"] == "open":
                    item.update(status="resolved", resolved_at=now, resolved_commit=verdict["commit"])
                    _write(folder, item)
    if verdict["verdict"] != "APPROVED":
        return
    for fresh in new_pendings(message, known):
        item = {"id": _claim_id(folder, len(known) + 1), "text": fresh["text"], "status": "open",
                "commit": verdict["commit"], "ticket": ticket, "opened_at": now}
        known.append(item)
        _write(folder, item)


def _claim_id(folder, start):
    """Reserva o próximo número livre. Dois revisores terminam juntos e contariam o mesmo:
    a criação exclusiva do arquivo decide quem fica com ele."""
    os.makedirs(folder, exist_ok=True)
    number = start
    while True:
        try:
            os.close(os.open(os.path.join(folder, f"P{number}.json"), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return f"P{number}"
        except FileExistsError:
            number += 1


def _write(folder, item):
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, f"{item['id']}.json.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(folder, f"{item['id']}.json"))


def _screens():
    """O que o `.harness/screens check` sabe: o mesmo código confere no despacho, no carimbo e à mão."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import screens
    return screens


def gate_for(agent_type):
    return AGENT_GATE.get(agent_type) if isinstance(agent_type, str) else None


def parse_verdict(message):
    """Só aceita uma linha inteira de cada chave; qualquer ambiguidade vira None."""
    if not isinstance(message, str):
        return None
    found = {"verdict": [], "commit": [], "resumo": []}
    for raw in message.splitlines():
        line = raw.strip()
        for key, pattern in (("verdict", _VERDICT), ("commit", _COMMIT), ("resumo", _RESUMO)):
            m = pattern.match(line)
            if m:
                found[key].append(m.group(1).strip())
    if any(len(values) != 1 for values in found.values()):
        return None
    return {key: values[0] for key, values in found.items()}


_PLATFORM = ("[SYSTEM NOTIFICATION", "<system-reminder", "<task-notification")


def _is_message(entry) -> bool:
    """Entrada de usuário que é texto, e não resultado de ferramenta."""
    content = (entry.get("message") or {}).get("content")
    texts = [content] if isinstance(content, str) else [b.get("text") for b in content if isinstance(b, dict)
                                                         and b.get("type") == "text"] if isinstance(content, list) else []
    # Aviso da própria plataforma (tarefa em segundo plano, lembrete do sistema) não é alguém falando com o revisor.
    return any(isinstance(t, str) and t.strip() and not t.lstrip().startswith(_PLATFORM) for t in texts)


def final_message(payload):
    """Resposta final do subagente.

    A plataforma manda o texto em `last_assistant_message`. Em versões anteriores o campo
    não vinha, e o texto era lido da transcrição do subagente; as duas formas valem. Na
    hora em que o hook roda, a transcrição pode ainda não ter a resposta final: por isso o
    campo, quando existe, é a fonte do texto.

    A transcrição serve sempre para uma conferência: se alguém falou com o revisor depois
    que ele começou, o veredito deixa de ser só sobre os documentos e não vale.
    """
    # O relatório de um subagente sai pela ferramenta SubagentHandback; no SubagentStop o campo
    # `last_assistant_message` traz só o fecho, e a transcrição pode ainda não ter a chamada. Por isso o
    # hook roda também quando a ferramenta é chamada, e ali o relatório é `tool_input.message`.
    message = payload.get("last_assistant_message")
    if payload.get("tool_name") == HANDBACK_TOOL:
        message = (payload.get("tool_input") or {}).get("message")
    message = message if isinstance(message, str) and message.strip() else None
    path = payload.get("agent_transcript_path")
    if not isinstance(path, str) or not os.path.exists(os.path.expanduser(path)):
        return message
    last = None
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or not entry.get("isSidechain"):
                    continue
                if entry.get("type") == "assistant":
                    last = entry
                elif entry.get("type") == "user" and last is not None and _is_message(entry):
                    return None
    except OSError:
        return None
    if message:
        return message
    # Sem o campo: só a última entrada do assistente conta, para um veredito citado no
    # meio do trabalho não valer como resposta.
    content = ((last or {}).get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "tool_use" and block.get("name") == HANDBACK_TOOL:
            text = (block.get("input") or {}).get("message")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts) if parts else None


def _answered(state, gate, commit, answer):
    """Anota no pedido que o revisor respondeu sem aprovar: o `integrate` deixa de mandar esperar."""
    path = common.request_path(state, gate, commit)
    try:
        with open(path, encoding="utf-8") as f:
            request = json.load(f)
        request["answer"] = answer
        with open(path, "w", encoding="utf-8") as f:
            json.dump(request, f)
    except (OSError, ValueError):
        pass


_CANDIDATE = re.compile(r"^NOTA: ([a-z0-9][a-z0-9-]{0,60})$")


def keep_candidates(payload) -> None:
    """O extrator propôs estas notas. Fica no estado do harness, que o agente não grava:
    `memory note add` só aceita nota nova cujo nome esteja aqui."""
    cwd = payload.get("cwd")
    state = common.state_dir(cwd) if isinstance(cwd, str) else None
    message = final_message(payload)
    if not state or not isinstance(message, str):
        return
    folder = os.path.join(state, "candidates")
    for raw in message.splitlines():
        m = _CANDIDATE.match(raw.strip())
        if m:
            os.makedirs(folder, exist_ok=True)
            open(os.path.join(folder, m.group(1)), "w").close()


def main():
    payload = common.read_payload()
    if payload.get("agent_type") == "harness:extrator":
        keep_candidates(payload)
        return
    if payload.get("tool_name") not in (None, HANDBACK_TOOL):
        return
    gate = gate_for(payload.get("agent_type"))
    cwd = payload.get("cwd")
    if not gate or not isinstance(cwd, str):
        return
    skipped = lambda why: common.log(cwd, "gate_stamp", "não carimbou", f"{gate}: {why}")
    verdict = parse_verdict(final_message(payload))
    if not verdict:
        state = common.state_dir(cwd)
        head = common.head_sha(cwd)
        done = bool(state and head) and os.path.exists(common.approval_path(state, gate, head))
        # No SubagentStop o veredito já pode ter sido carimbado na entrega do relatório: aí não é falha.
        if payload.get("tool_name") == HANDBACK_TOOL or (payload.get("hook_event_name") == "SubagentStop" and not done):
            skipped("a resposta não traz um bloco VEREDITO/COMMIT/RESUMO legível, ou alguém falou com o revisor")
        return
    state = common.state_dir(cwd)
    if not state:
        return
    if gate in ("bugs", "ambiente"):
        # A caça a bugs também revisa a ponta da branch de um implementador, antes de integrar:
        # o commit não precisa ser o HEAD, mas precisa existir neste repositório.
        if common._git(cwd, "cat-file", "-t", verdict["commit"]) != "commit":
            return skipped(f"o commit {verdict['commit']} não existe neste repositório")
    elif verdict["commit"] != common.head_sha(cwd):
        return skipped(f"o commit revisado ({verdict['commit']}) não é o HEAD")
    if gate in ("bugs", "ambiente", "visual"):
        message = final_message(payload) or ""
        ticket = None
        try:
            with open(common.request_path(state, gate, verdict["commit"]), encoding="utf-8") as f:
                ticket = json.load(f).get("ticket")
        except (OSError, ValueError):
            pass
        if verdict["verdict"] == "APPROVED" and too_many_pendings(cwd, message, ticket):
            _answered(state, gate, verdict["commit"], "PENDINGS")
            return skipped("aprovou com mais pendências do que o ticket comporta")
        track_pendings(cwd, message, verdict, ticket)
        if verdict["verdict"] == "REJECTED":
            _answered(state, gate, verdict["commit"], "REJECTED")
    path = common.approval_path(state, gate, verdict["commit"])
    if verdict["verdict"] == "REJECTED":
        if os.path.exists(path):
            os.remove(path)
        return
    if gate == "visual":
        # Quem aprova a tela aprova as capturas deste commit: sem elas no lugar, não olhou o que diz ter olhado.
        missing = _screens().problems(common.repo_root(cwd) or cwd)
        if missing:
            return skipped("as capturas de tela não valem para este commit: " + "; ".join(missing))
    base = None
    try:
        with open(common.request_path(state, gate, verdict["commit"]), encoding="utf-8") as f:
            base = json.load(f).get("base")
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "gate": gate,
        "sha": verdict["commit"],
        "base": base,
        "status": "PASS",
        "resumo": verdict["resumo"],
        "by": "hook",
        "agent_type": payload.get("agent_type"),
        "transcript": payload.get("agent_transcript_path"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    common.log(cwd, "gate_stamp", "carimbou", f"{gate} {verdict['commit']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # nunca bloqueia, mas não some: fica no registro
        try:
            common.log(os.getcwd(), "gate_stamp", "erro", repr(exc))
        except Exception:
            pass
    sys.exit(0)
