"""Testes do tools/junior.py (linha 1 num comando), SEM Hermes: temas, pedido montado, auditoria da sessão."""
import importlib.util
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("junior", os.path.join(RAIZ, "tools", "junior.py"))
assert _spec and _spec.loader
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)


@caso("temas: lê a lista, pula o já usado e recusa número inexistente")
def t_temas():
    ts = J.ler_temas()
    assert len(ts) >= 8 and ts[0]["n"] == 1 and ts[0]["usado"], ts[:1]
    assert J.escolher_tema(ts)["n"] == min(t["n"] for t in ts if not t["usado"])
    assert J.escolher_tema(ts, 1)["n"] == 1
    try:
        J.escolher_tema(ts, 99)
        raise AssertionError("aceitou tema inexistente")
    except ValueError:
        pass


@caso("pedido: sai da rotina, com o tema e o arquivo de saída, sem marcador sobrando")
def t_pedido():
    tema = J.escolher_tema(J.ler_temas(), 2)
    texto, saida = J.montar_pedido(tema, "2026-10-09")
    assert saida == "ideias/2026-10-09-medir-fidelidade-movimento.md", saida
    assert tema["tema"] in texto and tema["pergunta"] in texto and saida in texto
    assert "<tema>" not in texto and "<data>" not in texto
    assert "Context7" in texto and "8001" in texto  # as regras da rotina vão junto


@caso("auditoria: escrita fora de ideias/ e comando com a 8001 são apontados; ideias/ e rascunho do Hermes valem")
def t_auditoria():
    base = RAIZ.replace("\\", "/")
    ev = [{"type": "tool_use", "name": "write_file", "input": {"path": f"{base}/ideias/2026-10-09-x.md"}},
          {"type": "tool_use", "name": "write_file",
           "input": {"path": "C:/Users/x/AppData/Local/hermes/profiles/hermes-dev/cache/scratch/a.py"}},
          {"type": "tool_use", "name": "read_file", "input": {"path": f"{base}/docs/ESTADO_ATUAL.md"}},
          {"type": "tool_result", "name": "read_file", "output": "a porta 8001 ..."},
          {"type": "tool_use", "name": "web_extract",
           "input": {"urls": ["https://dev.epicgames.com/documentation/unreal-engine/motion-warping-in-unreal-engine"]}}]
    a = J.auditar(ev)
    # ler texto que cita a 8001, ou abrir documentação com "unreal-engine" no link, não é acesso ao Unreal
    assert a["acoes"] == 4 and a["escritas_fora"] == [] and a["unreal"] == [], a
    ev += [{"type": "tool_use", "name": "write_file", "input": {"path": "C:/Users/x/unreal-macros-sandbox/t.py"}},
           {"type": "tool_use", "name": "terminal", "input": {"command": "curl http://127.0.0.1:8001/mcp"}},
           {"type": "tool_use", "name": "mcp__florentia_macros__inspecionar_cena", "input": {}}]
    a = J.auditar(ev)
    assert a["escritas_fora"] == ["C:/Users/x/unreal-macros-sandbox/t.py"] and len(a["unreal"]) == 2, a


@caso("marcar_tema anota a data e o arquivo sem estragar a tabela")
def t_marcar():
    with tempfile.TemporaryDirectory() as tmp:
        c = os.path.join(tmp, "temas.md")
        shutil.copy(J.TEMAS, c)
        J.marcar_tema(2, "2026-10-09", "ideias/2026-10-09-medir.md", c)
        ts = J.ler_temas(c)
        assert ts[1]["usado"] and len(ts) == len(J.ler_temas()), ts[1]
        assert "09/10" in open(c, encoding="utf-8").read()


if __name__ == "__main__":
    sys.exit(0 if rodar([t_temas, t_pedido, t_auditoria, t_marcar], "junior") else 1)
