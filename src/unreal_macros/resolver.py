"""Orientação para a skill `resolver-problemas` (v0.0.2, bloco 3).

O detector (emperramento.py) decide QUANDO houve emperramento e QUAL degrau. Este módulo NÃO refaz a detecção:
recebe o estado do detector e acrescenta (1) o tipo de falha, por tabela fixa, (2) o contorno padrão desse tipo,
(3) as lições RELEVANTES (no máximo 3, nunca o livro inteiro) e (4) as fontes de solução pronta.
Nenhuma função aqui aceita texto do agente como prova de progresso. Votos de lições mudam só por eventos do
detector: progresso depois do uso da lição = +1; novo disparo = −1.
"""
import datetime as dt
import json
import os
import re
import unicodedata

from . import emperramento as E
from .macros import RAIZ_WORK

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs")
LICOES_INICIAIS = os.path.join(DOCS, "licoes_iniciais.json")
FONTES = os.path.join(DOCS, "fontes_solucoes.json")
PASTA_LICOES = os.path.join(RAIZ_WORK, "licoes")

TIPOS_FALHA = ("entendimento", "conhecimento", "capacidade", "ambiente", "verificacao", "dependencia", "estrategia")
CONTORNOS = {
    "entendimento": "reler a ficha do problema; se o pedido for ambíguo, perguntar",
    "conhecimento": "pesquisar: lições -> fontes de solução -> web/GitHub, antes de tentar de novo",
    "capacidade": "não insistir; registrar o pedido de capacidade; procurar solução PRONTA nas fontes antes de construir",
    "ambiente": "usar a ferramenta certa (ex.: liberar_trava_orfa) ou avisar; nunca forçar na mão",
    "verificacao": "melhorar ou desconfiar da medida antes de continuar; não repetir o caso",
    "dependencia": "parar esta linha; registrar o que falta; voltar à dependência (pedir integração)",
    "estrategia": "trocar a abordagem: outra hipótese do arquivo de alternativas ou outro caminho",
}
LACUNAS_POR_TIPO = {"capacidade": ("movimento", "objeto_3d", "codigo"), "conhecimento": ("unreal", "codigo")}


# ---------- classificação (tabela fixa, testada) ----------
def classificar(disparo: dict) -> str:
    erro, tipo, acao = disparo.get("erro") or "", disparo.get("tipo"), disparo.get("acao") or ""
    alvo = " ".join(disparo.get("assinaturas", []))
    if erro.startswith("recusa:"):
        if "integrad" in alvo or "dependência" in alvo or "dependencia" in alvo:
            return "dependencia"
        if "limite" in alvo or "prazo" in alvo:
            return "estrategia"
        return "ambiente"
    if erro.startswith("gate:"):
        return "verificacao"
    if erro in ("UnrealError", "TimeoutError", "RuntimeError", "TravaOcupada", "tempo_esgotado", "UnrealPaused"):
        return "ambiente"
    if erro == "FileNotFoundError":
        return "capacidade"
    if erro in ("ValueError", "KeyError", "TypeError"):
        return "entendimento" if tipo in ("repeticao", "mesmo_erro") else "estrategia"
    if erro.startswith("saida:") or tipo in ("vai_e_volta", "estagnacao"):
        return "estrategia"
    return "estrategia"


# ---------- lições ----------
def _radicais(texto: str) -> set:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p[:5] for p in re.findall(r"[a-z0-9_]+", t) if len(p) > 3}


def _livro(pasta: str) -> list:
    return json.load(open(LICOES_INICIAIS, encoding="utf-8"))


def consultar_licoes(tipo_falha: str, contexto: str, pasta: str = None, k: int = 3) -> list:
    """Só lições do MESMO tipo de falha, ordenadas por sobreposição do gatilho com o contexto e pelos votos."""
    pasta = pasta or PASTA_LICOES
    votos = carregar_votos(pasta)
    alvo = _radicais(contexto)
    cand = []
    for lic in _livro(pasta):
        if lic["tipo_falha"] != tipo_falha:
            continue
        v = votos.get(lic["id"], {"positivos": 0, "negativos": 0})
        sobre = len(_radicais(lic["gatilho"]) & alvo)
        cand.append((sobre, v["positivos"] - v["negativos"], lic["id"], dict(lic, votos=v, relevancia=sobre)))
    cand.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [c[3] for c in cand[:k]]


def registrar_uso_licao(licao_id: str, linha: str, pasta: str = None, agora: float = None) -> dict:
    """Marca que a lição foi aplicada na linha. O VOTO não vem daqui: vem do próximo marco do detector."""
    pasta = pasta or PASTA_LICOES
    if licao_id not in {l["id"] for l in _livro(pasta)}:
        raise ValueError(f"lição inexistente: {licao_id}")
    os.makedirs(pasta, exist_ok=True)
    reg = {"aplicacao": f"{licao_id}@{linha}@{agora or dt.datetime.now().timestamp():.3f}", "licao": licao_id,
           "linha": linha, "quando": agora if agora is not None else dt.datetime.now().timestamp()}
    with open(os.path.join(pasta, "aplicacoes.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return reg


def carregar_votos(pasta: str = None) -> dict:
    arq = os.path.join(pasta or PASTA_LICOES, "votos.json")
    return json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else {}


def atualizar_votos(itens: list, pasta: str = None) -> dict:
    """Resolve aplicações pendentes pelo PRIMEIRO marco do detector depois delas, na mesma linha:
    progresso = +1, disparo = −1, nenhum marco ainda = pendente. Idempotente (cada aplicação vota uma vez)."""
    pasta = pasta or PASTA_LICOES
    arq_ap = os.path.join(pasta, "aplicacoes.jsonl")
    if not os.path.exists(arq_ap):
        return carregar_votos(pasta)
    votos = carregar_votos(pasta)
    resolvidas = set(votos.get("_resolvidas", []))
    for linha in open(arq_ap, encoding="utf-8"):
        ap = json.loads(linha)
        if ap["aplicacao"] in resolvidas:
            continue
        marcos = [m for m in E.avaliar(itens, ap["linha"])["marcos"] if m["quando"] >= ap["quando"]]
        if not marcos:
            continue
        v = votos.setdefault(ap["licao"], {"positivos": 0, "negativos": 0})
        v["positivos" if marcos[0]["tipo"] == "progresso" else "negativos"] += 1
        resolvidas.add(ap["aplicacao"])
    votos["_resolvidas"] = sorted(resolvidas)
    os.makedirs(pasta, exist_ok=True)
    tmp = os.path.join(pasta, "votos.json.tmp")
    json.dump(votos, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(pasta, "votos.json"))
    return votos


# ---------- fontes ----------
def consultar_fontes(lacunas) -> dict:
    """Fontes por lacuna, separando DISPONÍVEIS (instaladas) de RESERVADAS (não instaladas: não usar ainda)."""
    reg = json.load(open(FONTES, encoding="utf-8"))
    disp, resv = [], []
    for lac in lacunas:
        for f in reg.get(lac, []):
            (disp if f["status"] == "instalado" else resv).append(dict(f, lacuna=lac))
    return {"disponiveis": disp, "reservadas": resv}


# ---------- orientação para a skill ----------
def orientar(estado: dict, pasta_licoes: str = None) -> dict:
    """Recebe o estado JÁ calculado pelo detector (não recalcula) e devolve o que a skill precisa."""
    d = estado.get("ultimo_disparo")
    base = {"linha": estado["linha"], "emperrado": estado["emperrado"], "esperando": estado.get("esperando", []),
            "incompletos": len(estado.get("incompletos", []))}
    if not estado["emperrado"] or not d:
        return dict(base, degrau=None, acao_skill="seguir: sem emperramento detectado pelas ferramentas")
    tipo = classificar(d)
    contexto = f"{d.get('acao')} {d.get('erro')} {d.get('tipo')} " + " ".join(d.get("assinaturas", []))
    lacunas = LACUNAS_POR_TIPO.get(tipo, ())
    fontes = consultar_fontes(lacunas)
    return dict(base, degrau=d["degrau"], tipo_emperramento=d["tipo"], tipo_falha=tipo, contorno=CONTORNOS[tipo],
                secao_skill=f"degrau:{d['degrau']}", evidencia=d["evidencia"],
                licoes=consultar_licoes(tipo, contexto, pasta_licoes), fontes=fontes,
                construir_do_zero_permitido=(not fontes["disponiveis"]) if lacunas else None)
