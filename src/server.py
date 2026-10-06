"""Servidor MCP `unreal-local-director`: a superfície pública do Hermes no Unreal (política: macros + workflows + escotilha).

Roda por stdio: <venv>/python.exe servidor_macros.py
Cada ferramenta devolve o relatório padrão em JSON: {macro, ok, medidas, evidencias, avisos, bloqueio, chamadas, segundos}.
"""
import json
import os
import sys

# 06/10: carregar o numpy/OpenBLAS DEPOIS das threads do servidor travava o processo para sempre (OpenBLAS
# chama perror dentro do carregamento da DLL e fica preso numa trava do Windows). 1 thread + carga na partida.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy  # noqa: E402,F401
from PIL import Image  # noqa: E402,F401

sys.path.insert(0, os.path.dirname(__file__))
from mcp.server.fastmcp import FastMCP  # noqa: E402

from unreal_macros import cartao, catalogo, macros as M, workflows  # noqa: E402

mcp = FastMCP("unreal-local-director", instructions=(
    "Ferramentas de tarefa inteira para o Unreal . Cada uma executa, lê de volta e MEDE, e devolve "
    "um relatório com ok/bloqueio/gates. Nunca declare sucesso sem ok=true. Pose é medida pela silhueta numa cópia no "
    "estúdio (a caixa envolvente mente). Para uma cena com vários passos, escreva um cartão e use validar_cartao/executar_cartao. "
    "chamada_avancada é só para emergência e exige motivo."))


def _limpo(o):
    """Remove campos internos (máscaras numpy) e garante JSON."""
    if isinstance(o, dict):
        return {k: _limpo(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, list):
        return [_limpo(v) for v in o]
    return o


def _r(rel: dict) -> str:
    return json.dumps(_limpo(rel), ensure_ascii=False, default=str)


@mcp.tool()
def inspecionar_cena(filtro: str = "") -> str:
    """Lista os personagens da cena (rótulo, posição do componente, animação, flags). filtro: parte do nome/rótulo."""
    return _r(M.inspecionar_cena(filtro=filtro))


@mcp.tool()
def medir_personagem(ator: str, com_vizinhos: bool = True) -> str:
    """Mede um personagem de pé pela silhueta (altura, deitado?, pés no piso real) e a distância aos vizinhos.
    ator: rótulo (ex. PC_18_Mezz01)."""
    return _r(M.medir_personagem(ator, com_vizinhos=com_vizinhos))


@mcp.tool()
def buscar_clipe(texto: str, n: int = 10, max_quadros: int = 0) -> str:
    """Procura clipes na biblioteca Mixamo local (2.317) por palavras em INGLÊS. max_quadros>0 descarta clipes longos (30 fps)."""
    return _r(catalogo.buscar_clipe(texto, n=n, max_quadros=max_quadros))


@mcp.tool()
def previa_clipe(nome: str, vista: int = 0) -> str:
    """Gera uma imagem com 3 quadros (início, meio, fim) do clipe para conferir com a visão ANTES de importar.
    vista: 0 frente, 1 costas, 2/3 lados. Devolve o caminho da imagem em `evidencias`."""
    return _r(catalogo.previa_clipe(nome, vista=vista))


@mcp.tool()
def importar_clipe(nome: str) -> str:
    """Importa um clipe da biblioteca para o Unreal (sem duplicar). nome: como em buscar_clipe (ex. Head_Nod_Yes)."""
    return _r(M.importar_clipe(nome))


@mcp.tool()
def aplicar_clipe(ator: str, clipe: str, loop: bool = True, tempo: float = 0.0) -> str:
    """Aplica um clipe num personagem DE PÉ sem mover o ator; corrige orientação e altura medindo. Não serve para sentar.
    Se ok=false, use restaurar_animacao com medidas.antes.props."""
    return _r(M.aplicar_clipe(ator, clipe, loop=loop, tempo=tempo))


@mcp.tool()
def restaurar_animacao(ator: str, estado_json: str) -> str:
    """Volta o personagem ao estado anterior. estado_json: o JSON de medidas.antes.props devolvido por aplicar_clipe."""
    return _r(M.restaurar_animacao(ator, estado=json.loads(estado_json)))


@mcp.tool()
def capturar_evidencia(ator: str, vista: str = "frontal", nome: str = "") -> str:
    """Foto de prova enquadrada no personagem (frontal|lateral|traseira), salva em ULD_EVIDENCE_DIR. Use com vision_analyze."""
    return _r(M.capturar_evidencia(ator, vista=vista, nome=nome))


@mcp.tool()
def plateia_em_loop(atores: list[str], texto: str = "idle talking conversation", candidatos: list[str] | None = None) -> str:
    """Workflow: dá um loop discreto (conversa/idle) a cada personagem, UM POR VEZ, sem mover ninguém; testa clipes
    até um passar (de pé, pés no piso, sem andar, pés plantados, sem vizinho colado); se nenhum passar, desfaz e PARA."""
    return _r(workflows.plateia_em_loop(atores, texto=texto, candidatos=candidatos))


@mcp.tool()
def validar_cartao(cartao_json: str) -> str:
    """Confere um cartão de cena sem executar (formato, ids, ordem, atores e clipes existentes)."""
    return _r(cartao.validar_cartao(json.loads(cartao_json)))


@mcp.tool()
def executar_cartao(cartao_json: str) -> str:
    """Valida e executa um cartão de cena passo a passo; para no primeiro passo que falhar.
    Formato: {"objetivo": str, "deve_evitar": [str], "passos": [{"id", "acao": aplicar_clipe|plateia_em_loop|
    medir_personagem|capturar_evidencia, "ator"|"atores", "clipe"|"candidatos", "depois"}]}"""
    return _r(cartao.executar_cartao(json.loads(cartao_json)))


@mcp.tool()
def chamada_avancada(toolset: str, ferramenta: str, argumentos_json: str, motivo: str) -> str:
    """ESCOTILHA DE EMERGÊNCIA: chama uma ferramenta atômica do MCP do Unreal. Só quando nenhuma macro serve;
    o motivo é registrado e vira pedido de macro nova."""
    return _r(M.chamada_avancada(toolset, ferramenta, json.loads(argumentos_json), motivo=motivo))


@mcp.tool()
def registrar_falha(titulo: str, texto: str, estado: str = "ABERTO") -> str:
    """Registra uma falha nova no FALHAS_UNREAL.md pela VM (numera e faz commit). NUNCA edite .md pelo Y: (zera o arquivo).
    texto: linhas '- Sintoma: ...', '- Causa/hipótese: ...', '- Contorno: ...'."""
    return _r(M.registrar_falha(titulo, texto, estado=estado))


if __name__ == "__main__":
    mcp.run()
