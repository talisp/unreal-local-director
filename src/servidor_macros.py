"""Servidor MCP `unreal-local-director`: a superfície pública do Hermes no Unreal (política: macros + workflows + escotilha).

Roda por stdio: <venv>/python.exe server.py
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


def _exp(fn, *a, **k) -> str:
    from unreal_macros import experimentos as X
    try:
        return json.dumps({"ok": True, **{"resultado": fn(*a, **k)}}, ensure_ascii=False, default=str)
    except X.Recusa as e:
        return json.dumps({"ok": False, "recusa": str(e)}, ensure_ascii=False)


@mcp.tool()
def iniciar_experimento(nome: str, tipo: str, objetivo: str, hipoteses_json: str = "", escolhida: int = 0,
                        dependencias: str = "", causa_evidencia: str = "", correcao: str = "", pedido: str = "") -> str:
    """Abre um experimento no sandbox com cópia de trabalho própria (criada do master). tipo=experimento (solução
    incerta): hipoteses_json = lista de 2-3 objetos {descricao, mudanca, previsao[, aposta:{meta:{metrica,comparador,
    valor}, prazo_min, criterio_encerramento}]}, materialmente diferentes; escolhida = índice. tipo=conserto (causa
    comprovada): sem hipóteses, com causa_evidencia (relatorio_id ou arquivo do sandbox) e correcao. dependencias:
    branches separadas por vírgula, que precisam já estar INTEGRADAS no master. pedido: id do banco de pedidos que o
    experimento ajuda (ex.: P08) ou 'infraestrutura/transversal'. Limites: 2 corridas, 60 min."""
    from unreal_macros import experimentos as X
    hips = json.loads(hipoteses_json) if hipoteses_json else None
    deps = [d.strip() for d in dependencias.split(",") if d.strip()]
    return _exp(X.iniciar, nome, tipo, objetivo, hipoteses=hips, escolhida=escolhida, dependencias=deps,
                causa_evidencia=causa_evidencia, correcao=correcao, pedido=pedido)


@mcp.tool()
def rodar_experimento(nome: str, script: str) -> str:
    """Roda UMA corrida do experimento: o script (caminho relativo à cópia do experimento, ex. src/testes_contrato.py)
    executa com o código do sandbox (com guarda). Recusa a 3a corrida, prazo esgotado, guarda alterada ou script que
    aponte para a produção. O resultado (saída, código, testes ok) é gravado pela ferramenta."""
    from unreal_macros import experimentos as X
    return _exp(X.rodar, nome, script)


@mcp.tool()
def fechar_experimento(nome: str, interpretacao: str = "") -> str:
    """Fecha o experimento: o resultado vem das corridas gravadas; sua interpretação fica guardada à parte, marcada
    como declarada. As hipóteses não escolhidas continuam no arquivo de alternativas."""
    from unreal_macros import experimentos as X
    return _exp(X.fechar, nome, interpretacao)


@mcp.tool()
def consultar_emperramento(linha: str) -> str:
    """Diz se a linha de trabalho está EMPERRADA, lendo só os registros das ferramentas (relatórios e eventos). Devolve
    degrau (cutucar/replanejar/outro_caminho/escalar/abortar), tipo_falha, contorno, lições relevantes e fontes de
    solução pronta. linha = nome do experimento, ou contexto.linha da macro (padrão: o nome da macro)."""
    from unreal_macros import emperramento as E, experimentos as X, resolver as RS
    itens = E.carregar_historico(os.path.join(M.RAIZ_WORK, "relatorios"), X.PASTA)
    estado = E.avaliar(itens, linha)
    E.registrar_disparos(estado, os.path.join(M.RAIZ_WORK, "emperramento", "disparos.jsonl"))
    RS.atualizar_votos(itens)
    return json.dumps(RS.orientar(estado), ensure_ascii=False, default=str)


@mcp.tool()
def registrar_uso_licao(licao_id: str, linha: str) -> str:
    """Registra que você aplicou a lição na linha. O voto (ajudou/não) é decidido depois pelo próximo resultado
    medido nessa linha, nunca por texto."""
    from unreal_macros import resolver as RS
    try:
        return json.dumps({"ok": True, "registro": RS.registrar_uso_licao(licao_id, linha)}, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "recusa": str(e)}, ensure_ascii=False)


@mcp.tool()
def passagem_de_sessao() -> str:
    """Chame no INÍCIO de toda sessão: devolve só o necessário para continuar (objetivo, experimentos abertos, último
    progresso útil medido, degraus, pendências, lições relevantes, bloqueios e esperas ativos). Não releia histórico."""
    from unreal_macros import sessao
    return json.dumps(sessao.passagem(), ensure_ascii=False, default=str)


@mcp.tool()
def registrar_escalada(linha: str, motivo: str) -> str:
    """Passa a linha para um humano (degrau 'escalar'), com o diagnóstico em uma frase. Suspende o relógio do
    supervisor até a próxima tentativa; não conta como progresso."""
    from unreal_macros import experimentos as X
    return _exp(X.registrar_escalada, linha, motivo)


@mcp.tool()
def liberar_trava_orfa(corrompida: bool = False) -> str:
    """Libera a trava do Unreal só se o processo dono MORREU (confirmado pelo sistema, não pela idade). Dono vivo:
    recusa (espere). corrompida=True só se o relatório disser que a trava está corrompida e ninguém estiver operando."""
    return _r(M.liberar_trava_orfa(corrompida=corrompida))


@mcp.tool()
def registrar_tentativa(macro: str, relatorio_id: str = "", relatorio_json: str = "", ator: str = "", clipe: str = "",
                        rodada: int = 0, tema: str = "", caso: str = "", previsao: str = "", restaurado: str = "",
                        restauracao: str = "", licao: str = "") -> str:
    """Grava a linha do diário da bancada a partir do relatório REAL da macro. Use relatorio_id (o campo "id" que a
    macro devolveu): os números vêm do disco, nunca redigitados. relatorio_json (colado) só se não houver id; a linha
    fica marcada fonte="colado". Você informa apenas rodada/tema/caso/previsão/restauração/lição. restaurado: sim|nao."""
    from unreal_macros import diario
    try:
        if relatorio_id:
            rel, fonte = diario.carregar_relatorio(relatorio_id), "relatorio_id"
        elif relatorio_json:
            rel, fonte = json.loads(relatorio_json), "colado"
        else:
            raise ValueError("informe relatorio_id (preferido) ou relatorio_json")
        res = diario.registrar(rel, macro=macro, ator=ator, clipe=clipe, rodada=rodada or None, tema=tema, caso=caso,
                               previsao=previsao, restaurado={"sim": True, "nao": False}.get(restaurado),
                               restauracao=restauracao, licao=licao, fonte=fonte)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "bloqueio": f"{type(e).__name__}: {e}"}
    return json.dumps(res, ensure_ascii=False)


# ---------- biblioteca de blocos (Fase 3): só leitura, sem Unreal ----------
def _biblioteca(fn, *a, condicoes_json: str | None = None) -> str:
    """Erro vira recusa com motivo, nunca exceção. condicoes_json muda condições da medida (ex. {"escala": 1.2});
    vazio = as condições em que o executor da fila mede agora."""
    from unreal_macros import biblioteca as BIB
    try:
        k = {}
        if condicoes_json is not None:
            c = BIB.condicoes_atuais()
            if condicoes_json.strip():
                extra = json.loads(condicoes_json)
                if not isinstance(extra, dict):
                    raise ValueError("condicoes_json tem de ser um objeto JSON")
                c.update(extra)
            k["condicoes"] = c
        res = fn(BIB.carregar(), *a, **k)
    except Exception as e:  # noqa: BLE001
        res = {"status": "recusado", "motivo": f"{type(e).__name__}: {e}"}
    return json.dumps(res, ensure_ascii=False)


@mcp.tool()
def listar_blocos(condicoes_json: str = "") -> str:
    """Blocos prontos da biblioteca: receitas que já deram nota 0 três vezes, com o status nas condições da cena
    ('validado' ou 'medir_de_novo', com o motivo). Sem Unreal."""
    from unreal_macros import biblioteca as BIB
    return _biblioteca(BIB.listar_blocos, condicoes_json=condicoes_json)


@mcp.tool()
def consultar_bloco(bloco: str, condicoes_json: str = "") -> str:
    """Use antes de reaproveitar um bloco: 'validado' devolve a receita pronta para o executor da fila; fora das
    condições em que foi medido, devolve 'medir_de_novo' com o motivo e SEM a receita. Sem Unreal."""
    from unreal_macros import biblioteca as BIB
    return _biblioteca(BIB.consultar_bloco, bloco, condicoes_json=condicoes_json)


@mcp.tool()
def historico_bloco(bloco: str) -> str:
    """Tudo o que foi medido de um bloco: receita, tentativas, notas, intenções, trocas, condições e vídeos."""
    from unreal_macros import biblioteca as BIB
    return _biblioteca(BIB.historico_bloco, bloco)


@mcp.tool()
def consultar_trocas(clipe_de: str, papel_para: str, condicoes_json: str = "") -> str:
    """Trocas já medidas que saem de `clipe_de` para um clipe que fez o papel `papel_para` (levantar, acenar, andar,
    parar, ponte), da melhor para a pior, com o custo por critério. A mesma troca custa o mesmo em qualquer receita
    (medido em 08/10): use isto antes de gastar uma tentativa no Unreal."""
    from unreal_macros import biblioteca as BIB
    return _biblioteca(BIB.consultar_trocas, clipe_de, papel_para, condicoes_json=condicoes_json)


@mcp.tool()
def ficha_clipe(nome: str) -> str:
    """Ficha de um clipe já usado: quadros, avanço, papéis em que passou ou reprovou, trocas em que entrou e o aceno."""
    from unreal_macros import biblioteca as BIB
    return _biblioteca(BIB.ficha_clipe, nome)


if __name__ == "__main__":
    mcp.run()
