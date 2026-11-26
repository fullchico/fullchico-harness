"""Reprovações dos portões finais da demanda: contadas no apêndice de certificados, que viaja com ela."""
import certs


def status(root, name, gate=None):
    if gate is None:
        import registry
        gate = (registry.load(root) or {}).get("gates", {}).get(name) or {}
    count = len(certs.rejections(root, name))
    return {"rejections": count, "intervention": count > gate.get("attempts", 3)}


def reject(root, name, gate, evidence=None):
    """Registra uma reprovação no apêndice (a mesma evidência não conta duas vezes). Devolve o estado."""
    import registry
    key = registry.stamp_key(root, gate)
    if key:
        summary = evidence or f"reprovação {len(certs.rejections(root, name)) + 1}"
        certs.certify(root, name, key, "REJECTED", registry.responsible(gate) or "tr:main-session", summary)
    return status(root, name, gate)
