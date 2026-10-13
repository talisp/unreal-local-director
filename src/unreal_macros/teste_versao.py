"""Testes da versão numa campanha de laboratório (/director-noite, 13/10): quem diz se um teste foi coberto é este
programa, lendo os registros da campanha. O agente só provoca a situação; a palavra dele não conta como cobertura.

A lista mora com o código (tools/testes_da_versao.json) e vale para a versão que estiver na pasta. Cada item da
lista tem um conferidor aqui; item sem conferidor não entra (o teste da suíte reprova). Sem Unreal, sem rede.
"""
import json
from pathlib import Path

from . import campanha as CP

LISTA = Path(__file__).resolve().parents[2] / "tools" / "testes_da_versao.json"
RECEITA_INVALIDA = ("turn_deg", "não deixa nenhum quadro", "ordem das intenções", "campos não aceitos", "faltam intenções",
                    "tem de ser inteiro", "tem de ser número", "entre 0 e 120")


def ler_lista(arquivo: str | Path = LISTA) -> dict:
    d = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    ids = [i.get("id") for i in d.get("itens", [])]
    if not ids or len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("lista de testes da versão sem itens ou com id repetido/vazio")
    for i in d["itens"]:
        if any(not isinstance(i.get(k), str) or not i[k].strip() for k in ("mudou", "como", "esperado")):
            raise ValueError(f"teste {i['id']}: faltam 'mudou', 'como' ou 'esperado'")
    return d


def _jsonl(arq: Path) -> list:
    """Leitura tolerante (linha cortada é ignorada): aqui só se procura EVIDÊNCIA; quem autoriza operação é a guarda."""
    out = []
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    return out


def _existe(pasta: Path, rel) -> bool:
    if not isinstance(rel, str) or not rel:
        return False
    alvo = Path(rel) if Path(rel).is_absolute() else pasta / rel
    return alvo.resolve().is_relative_to(pasta.resolve()) and alvo.is_file()


def _com_evidencia_em_disco(pasta: Path, t: dict) -> bool:
    fotos = t.get("cena_fotos") or []
    return (t.get("cena_ok") is True and (t.get("cena_alcance") or {}).get("reduzido") is False
            and len(fotos) == 2 and all(_existe(pasta, f) for f in fotos)
            and t.get("amostras_completas") is True and _existe(pasta, t.get("amostras_arquivo")))


def _aprovada_completa(pasta, tent, recusas):
    ns = [t.get("n") for t in tent if t.get("passou") is True and (t.get("medida") or {}).get("passou") is True
          and _com_evidencia_em_disco(pasta, t)]
    return ns[:3], "nenhuma tentativa aprovada com cena conferida no alcance completo, 2 fotos e amostras completas em disco"


def _reprovada_com_amostras(pasta, tent, recusas):
    ns = [t.get("n") for t in tent if type(t.get("nota")) in (int, float) and t["nota"] > 0 and t.get("passou") is False
          and (t.get("medida") or {}).get("passou") is False and _com_evidencia_em_disco(pasta, t)]
    return ns[:3], "nenhuma tentativa reprovada pela régua (nota > 0) com amostras completas e cena conferida"


def _repeticao(pasta, tent, recusas):
    s = CP.sucesso_seguro(tent)  # a mesma apuração da campanha: 3 distintas, aprovadas, mesmas condições e versões
    return ([s] if s else []), "nenhuma receita com 3 tentativas distintas aprovadas nas mesmas condições"


def _recusa_invalida(pasta, tent, recusas):
    ok = [r for r in recusas if r.get("comando") == "tentar" and r.get("proximo_n_antes") == r.get("proximo_n_depois")
          and any(x in m for m in r.get("motivos") or [] for x in RECEITA_INVALIDA)]
    return [r.get("motivos") for r in ok[:2]], "nenhuma receita inválida recusada pelo executor sem gastar número (recusas.jsonl)"


def _segunda_admissao(pasta, tent, recusas):
    ok = [r for r in recusas if r.get("pendente_n") is not None and r.get("proximo_n_antes") == r.get("proximo_n_depois")
          and any("ainda está rodando" in m for m in r.get("motivos") or [])]
    return [{"rodando": r.get("pendente_n")} for r in ok[:2]], "nenhuma segunda admissão recusada com uma tentativa ainda rodando"


def _video(pasta, tent, recusas):
    ns = []
    for t in tent:
        v = t.get("video") or {}
        if v.get("completo") is True and v.get("esperados") and v.get("quadros") == v.get("esperados") and _existe(pasta, v.get("arquivo")):
            ns.append(t.get("n"))
    return ns[:3], "nenhuma tentativa com vídeo completo (todas as capturas esperadas e o mp4 em disco)"


CONFERIDORES = {"tentativa_aprovada_completa": _aprovada_completa, "reprovada_guarda_amostras": _reprovada_com_amostras,
                "repeticao_tres_vezes": _repeticao, "recusa_receita_invalida": _recusa_invalida,
                "segunda_admissao_recusada": _segunda_admissao, "video_completo": _video}


def conferir(pasta: str | Path, ids: list, experimentos: list | None = None) -> dict:
    """{itens: [{id, situacao, evidencia|falta}], faltam: [ids]} para os testes `ids` da campanha em `pasta`.
    situacao: 'coberto' (o programa achou a evidência), 'achado_registrado' (não coberto, mas há experimento
    concluído com classe suspeita/lacuna apontando para o teste: o defeito foi registrado) ou 'falta'."""
    p = Path(pasta)
    tent = [t for t in _jsonl(p / "tentativas.jsonl") if t.get("tipo_linha") == "tentativa"]
    recusas = _jsonl(p / "recusas.jsonl")
    achados = {e.get("teste") for e in experimentos or [] if e.get("classe") in ("suspeita", "lacuna") and e.get("evidencias")}
    itens = []
    for i in ids:
        evidencia, falta = CONFERIDORES[i](p, tent, recusas) if i in CONFERIDORES else ([], "teste sem conferidor nesta versão")
        if evidencia:
            itens.append({"id": i, "situacao": "coberto", "evidencia": evidencia})
        elif i in achados:
            itens.append({"id": i, "situacao": "achado_registrado", "falta": falta})
        else:
            itens.append({"id": i, "situacao": "falta", "falta": falta})
    return {"itens": itens, "faltam": [x["id"] for x in itens if x["situacao"] == "falta"]}
