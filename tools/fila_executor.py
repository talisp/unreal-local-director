"""Executor ÚNICO da rodada da fila de movimentos (07/10). O Qwen só escreve a receita (JSON); este programa valida,
pega a trava, monta no Sequencer, amostra os ossos, dá a nota pela régua fixa (src/unreal_macros/fila.py), registra
e limpa. Feito pelo Claude depois do parecer do Astra: a LLM não constrói a régua, não limpa a cena e não guarda o
estado de cabeça.

Comandos (na raiz do repositório, Python do venv):
  tentar ARQ_RECEITA [--video]   valida e roda em SEGUNDO PLANO; responde na hora com o número (o terminal do
                                 Hermes corta em 180 s; uma tentativa leva minutos)
  resultado N                    veredito da tentativa N (ou "rodando")
  estado                         campeãs, linhagens, regras, tentativa pendente, sucesso
  fechar-linhagem NOME MOTIVO    fecha uma linhagem (platô, beco)
  rodar-agora ARQ [--video]      o mesmo que tentar, mas no primeiro plano (uso do Claude nos ensaios)

Registro (tudo em work/fila_2026-10-07/, ou FILA_PASTA): tentativas.jsonl (uma linha 'tentativa_inicio' ANTES de
tocar na cena e uma 'tentativa' no fim), encaixes.jsonl (uma linha por troca, com as coordenadas antes/depois de
todos os ossos), estado.json (gravado de forma atômica), videos/. Linha JSON cortada por queda é ignorada na leitura.
Segurança: trava a cada tentativa; atores só TESTE_FILA_* em x=20000; nada salvo; cada passo da limpeza é
protegido sozinho e só vale com confirmação positiva.
Alcance de cena_ok (v0.0.6): o inventário do level (list_actors) é fotografado ANTES de qualquer mutação e depois
da limpeza (evidencias/tNNN-antes.json e -depois.json) e comparado ator por ator em caminho, rótulo, classe,
posição, rotação e escala. NÃO cobre propriedades de componentes, materiais, assets nem o conteúdo do Sequencer:
cena_ok = "o inventário voltou igual e a limpeza foi confirmada", não "o level inteiro é idêntico".
Só se remove o que é comprovadamente desta execução (rótulo exato, criado depois de um baseline sem sobras) ou o
que uma execução que caiu deixou REGISTRADO no estado.json; prefixo sozinho não prova propriedade."""
# pyright: reportMissingImports=false
# (src/ e tools/ entram no sys.path na hora de rodar; o verificador não enxerga)
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import traceback
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from unreal_macros import processos as P  # noqa: E402  # pyright: ignore[reportMissingImports]

PASTA = os.path.abspath(os.environ.get("FILA_PASTA", os.path.join(RAIZ, "work", "fila_2026-10-07")))
PY = os.path.join(RAIZ, "venv", "Scripts", "python.exe")
FPS = 30
ZX, ZY = 20000.0, 0.0
ATOR, PISO = "TESTE_FILA_BONECO", "TESTE_FILA_PISO"
PREFIXO = "TESTE_FILA_"
HORA_FECHAR = (7, 30)
# Condições da medida (Fase 3, D25): TC.boneco cria o SK_YBot sem mudar a escala; o root motion fica como a
# importação (macros.importar_clipe) deixa. Vão em toda tentativa e troca; a biblioteca as compara antes de reaproveitar.
CONDICOES = {"personagem": "/Game/Characters/SK_YBot.SK_YBot", "escala": 1.0, "root_motion": "padrao_importar_clipe"}


# ---------- arquivos (sem Unreal) ----------
def _ler_jsonl(nome: str) -> list:
    arq = os.path.join(PASTA, nome)
    out = []
    if os.path.exists(arq):
        with open(arq, encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass  # linha cortada por queda: ignorada
    return out


def _sem_nao_finitos(x, onde: str, achados: list):
    """Cópia de `x` com NaN e infinito trocados por None; `achados` recebe o caminho de cada um (A12)."""
    if isinstance(x, float) and not math.isfinite(x):
        achados.append(onde)
        return None
    if isinstance(x, dict):
        return {k: _sem_nao_finitos(v, f"{onde}.{k}" if onde else str(k), achados) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sem_nao_finitos(v, f"{onde}[{i}]", achados) for i, v in enumerate(x)]
    return x


def _acrescentar(nome: str, d: dict):
    os.makedirs(PASTA, exist_ok=True)
    try:
        linha = json.dumps(d, ensure_ascii=False, default=str, allow_nan=False)
    except ValueError:  # A12: NaN/Infinity não são JSON e sairiam em silêncio; viram null, com o caminho anotado
        achados: list = []
        limpo = dict(_sem_nao_finitos(d, "", achados) or {}, nao_finitos=achados)
        linha = json.dumps(limpo, ensure_ascii=False, default=str, allow_nan=False)
    with open(os.path.join(PASTA, nome), "a", encoding="utf-8") as f:
        f.write(linha + "\n")
        f.flush()
        os.fsync(f.fileno())


class EstadoIlegivel(RuntimeError):
    """estado.json perdido ou ilegível numa rodada que JÁ tem histórico (A03): não é rodada nova. Nada é escrito
    por cima; quem recebe isto recusa a operação."""


def _reconciliar_estado(linhas: list) -> dict:
    """estado.json AUSENTE com histórico: refaz contador, fechamentos e início da rodada só com o que o histórico
    prova. Um início sem conclusão não tem prova de restauração: bloqueia."""
    finais = {t.get("n") for t in linhas if t.get("tipo_linha") in ("tentativa", "tentativa_interrompida")}
    abertos = sorted(str(t.get("n")) for t in linhas if t.get("tipo_linha") == "tentativa_inicio" and t.get("n") not in finais)
    if abertos:
        raise EstadoIlegivel(f"estado.json sumiu e a tentativa {', '.join(abertos)} começou sem registrar o fim: a rodada "
                             "não é nova nem está comprovadamente limpa. Confira a cena e restaure o estado.json "
                             "(ou abra outra pasta de rodada)")
    ns = [t["n"] for t in linhas if isinstance(t.get("n"), int)]
    quando = sorted(str(t["quando"]) for t in linhas if t.get("quando"))
    e: dict = {"proximo_n": max(ns, default=0) + 1, "pendente": None, "reconciliado_do_historico": True,
               "fechadas": {t["linhagem"]: t.get("motivo", "sem motivo") for t in linhas
                            if t.get("tipo_linha") == "linhagem_fechada" and t.get("linhagem")}}
    if quando:
        e["inicio_rodada"] = quando[0]
    return e


def _estado_lido() -> tuple:
    """(estado, motivo). motivo != None = não dá para confiar no estado: é o que as CONSULTAS mostram, sem escrever."""
    arq = os.path.join(PASTA, "estado.json")
    novo = {"proximo_n": 1, "pendente": None, "fechadas": {}}
    if not os.path.exists(arq):
        linhas = _ler_jsonl("tentativas.jsonl")
        if not linhas:
            return novo, None  # pasta realmente nova
        try:
            return _reconciliar_estado(linhas), None
        except EstadoIlegivel as ex:
            return novo, str(ex)
    try:
        with open(arq, encoding="utf-8") as f:
            e = json.load(f)
        if not isinstance(e, dict):
            raise ValueError("não é um objeto")
        return e, None
    except (OSError, ValueError) as ex:
        return novo, (f"estado.json ilegível ({type(ex).__name__}): o arquivo foi preservado como está; restaure-o "
                      "antes de continuar (nada será escrito por cima)")


def _estado() -> dict:
    e, motivo = _estado_lido()
    if motivo:
        raise EstadoIlegivel(motivo)
    return e


def _gravar_estado(e: dict):
    os.makedirs(PASTA, exist_ok=True)
    if _estado_lido()[1] and os.path.exists(os.path.join(PASTA, "estado.json")):
        raise EstadoIlegivel("estado.json ilegível: não é sobrescrito")  # preserva o arquivo defeituoso (A03)
    e.pop("reconciliado_do_historico", None)
    tmp = os.path.join(PASTA, "estado.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(PASTA, "estado.json"))


def _agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _sha(caminho: str) -> str:
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def versoes() -> dict:
    return {"regua": _sha(os.path.join(RAIZ, "src", "unreal_macros", "fila.py")), "executor": _sha(__file__),
            "toolset": _sha(os.path.join(RAIZ, "editor_python", "director_tools", "toolset.py"))}


def tentativas_validas() -> list:
    return [t for t in _ler_jsonl("tentativas.jsonl") if t.get("tipo_linha") == "tentativa"]


def _pid_estado(pid) -> str:
    return P.estado_processo(pid)


def _cena() -> dict | None:
    """A cena da linha 2 (Fase 8), se FILA_CENA aponta para uma (cenas/<nome>.md). Sem ela: a rodada de 07/10."""
    arq = os.environ.get("FILA_CENA")
    if not arq:
        return None
    from unreal_macros import cena as C
    return C.ler_cena(arq if os.path.isabs(arq) else os.path.join(RAIZ, arq))


def prazo_de(inicio: dt.datetime, fechar: tuple) -> dt.datetime:
    """O primeiro `fechar` (HH, MM) DEPOIS do início da rodada. Astra, 08/10: a regra antiga ('antes do meio-dia e
    depois das 07:30') reabria a rodada à tarde."""
    p = inicio.replace(hour=fechar[0], minute=fechar[1], second=0, microsecond=0)
    return p if p > inicio else p + dt.timedelta(days=1)


def _fechar() -> tuple:
    c = _cena()
    return tuple(int(x) for x in c["prazo_tentativas"].split(":")) if c and c.get("prazo_tentativas") else HORA_FECHAR


def depois_da_hora() -> bool:
    e = _estado()
    if not e.get("inicio_rodada"):  # a 1ª ADMISSÃO da rodada marca o início (vale para a rodada inteira)
        e["inicio_rodada"] = _agora()
        _gravar_estado(e)
    return _passou_do_prazo(e)


def _passou_do_prazo(e: dict) -> bool:
    """Só lê: é o que as CONSULTAS usam (A03). Rodada que ainda não marcou o início não passou do prazo."""
    if not e.get("inicio_rodada"):
        return False
    return dt.datetime.now() >= prazo_de(dt.datetime.fromisoformat(e["inicio_rodada"]), _fechar())


def _prazo_encerrado(e: dict) -> bool | None:
    """Para as consultas. Campanha: o prazo absoluto do manifesto (A26). Rodada legada: o horário da rodada."""
    if not eh_campanha():
        return _passou_do_prazo(e)
    import time
    from unreal_macros import campanha as CP
    try:
        return time.time() >= CP.ler(PASTA)["prazo_tentativas_ts"]
    except (ValueError, OSError, KeyError, TypeError):
        return None  # identidade da campanha não confere: a guarda já recusa; aqui não se inventa prazo


def _relatorio_final_se_encerrada():
    """A29: se a campanha foi encerrada (PARAR) enquanto uma tentativa já autorizada ainda rodava, o relatório do
    encerramento saiu PROVISÓRIO. Quando essa tentativa termina, o relatório é refeito com o resultado dela.
    Campanha aberta não ganha relatório aqui; falha ao refazer nunca derruba a tentativa."""
    if not eh_campanha() or not os.path.exists(os.path.join(PASTA, "PARAR")):
        return None
    try:
        import director_noite as N
        from pathlib import Path
        return N.relatorio(Path(PASTA))
    except Exception as ex:  # noqa: BLE001
        _acrescentar("biblioteca.jsonl", {"ok": False, "erro": f"relatório final não refeito: {type(ex).__name__}: {str(ex)[:200]}",
                                          "quando": _agora()})
        return None


@contextlib.contextmanager
def _admissao():
    """A01: validar, reservar o número, gravar a receita e autorizar o filho é UMA operação por rodada. Duas
    chamadas ao mesmo tempo entram uma de cada vez (entre processos e entre threads)."""
    from unreal_macros import trava
    with trava.exclusiva(os.path.join(PASTA, "admissao.trava"), "admissao da fila"):
        yield


def _reservar(n: int) -> dict:
    """Dentro de _admissao(): reserva o número e o dono ANTES de anunciar 'rodando' ou tocar na cena."""
    e = _estado()
    e["pendente"] = {"n": n, "pid": os.getpid(), "desde": _agora(), "seq": None, "execucao": uuid.uuid4().hex,
                     "fase": "reservada"}
    e["proximo_n"] = n + 1
    _gravar_estado(e)
    return dict(e["pendente"])


def _liberar_reserva(execucao: str | None) -> bool:
    """Retira SÓ a reserva desta execução, e só se ela ainda não começou (nenhuma linha de início foi gravada)."""
    e = _estado()
    p = e.get("pendente") or {}
    if not execucao or p.get("execucao") != execucao or p.get("fase") != "reservada":
        return False
    e["pendente"] = None
    e.pop("autorizado", None)
    _gravar_estado(e)
    return True


def reconciliar_pendente() -> dict | None:
    """A04: a tentativa gravou o resultado final SEGURO e o processo caiu antes de retirar a reserva. Com dono
    comprovadamente morto e UMA conclusão segura da MESMA execução, retira só a pendência administrativa: não
    toca na cena e não apaga histórico. Qualquer ambiguidade mantém o bloqueio. Chamar dentro de _admissao()."""
    from unreal_macros import campanha as CP
    e, motivo = _estado_lido()
    p = e.get("pendente")
    if motivo or not p or _pid_estado(p.get("pid")) != P.MORTO or not CP.conclusao_segura(_ler_jsonl("tentativas.jsonl"), p):
        return None
    e["pendente"] = None
    _gravar_estado(e)
    _acrescentar("tentativas.jsonl", {"tipo_linha": "pendencia_reconciliada", "n": p.get("n"), "execucao": p.get("execucao"),
                                      "motivo": "resultado final seguro já registrado; dono da reserva morto",
                                      "quando": _agora()})
    return p


# ---------- preparação da receita (sem Unreal) ----------
def eh_campanha() -> bool:
    return os.path.basename(PASTA).startswith("dn-") or any(
        os.path.exists(os.path.join(PASTA, nome)) for nome in ("campanha.json", "OBJETIVO.txt", "PLANO.json"))


def guarda_campanha() -> list:
    """Barreira opt-in compartilhada com a vigia; nenhuma recuperação automática de cena."""
    if not eh_campanha():
        return []
    from unreal_macros import campanha as CP
    motivos = CP.guarda(PASTA)
    if os.path.abspath(os.environ.get("FILA_CENA", "")) != os.path.join(PASTA, "CENA.md"):
        motivos.append("identidade da campanha: FILA_CENA não aponta para sua cena imutável")
    return motivos


def laboratorio() -> bool:
    if not eh_campanha():
        return False
    from unreal_macros import campanha as CP
    return CP.ler(PASTA).get('modo') == 'experimental'


def guarda_personagem(receita: dict | None = None) -> list:
    c = _cena() or {}
    pedido = (receita or {}).get('personagem') or c.get('personagem')
    citados = re.findall(r'\b(?:PC_|SK_)[A-Za-z0-9_]+', c.get('fixo', ''))
    if not pedido and any(x != 'SK_YBot' for x in citados):
        return ['personagem citado em fixo não é medido; declare personagem estruturado']
    # Receita não pode esconder uma malha fixa/solicitada pela campanha.
    declarados = [c.get('personagem'), (receita or {}).get('personagem'), *citados]
    for personagem in declarados:
        if personagem and personagem not in ('SK_YBot', CONDICOES['personagem']):
            return [f'personagem não suportado neste experimento: {personagem}; executor mede somente SK_YBot']
    return []


def preparar(receita: dict) -> tuple:
    """(n reservado, motivos de recusa). Recusa ANTES de tocar no Unreal: receita inválida, regras, hora, pendente."""
    from unreal_macros import fila as F
    from unreal_macros import receita as R
    try:
        e = _estado()
    except EstadoIlegivel as ex:  # A03: estado perdido não vira rodada nova
        return 0, [str(ex)]
    motivos_campanha = guarda_campanha()
    if motivos_campanha:
        return e.get("proximo_n", 1), motivos_campanha
    motivos = guarda_personagem(receita) + R.validar(receita, _quadros_conhecidos())  # régua + campos da Fase 4 (início, corte, giro no fim)
    if e.get("pendente"):
        p = e["pendente"]
        processo = _pid_estado(p.get("pid"))
        if processo == P.VIVO:
            motivos.append(f"a tentativa {p['n']} ainda está rodando: espere (resultado {p['n']})")
        elif processo != P.MORTO:
            motivos.append(f"a tentativa {p['n']} tem processo DESCONHECIDO: consulta inconclusiva; reserva preservada, espere")
    tent = tentativas_validas()
    if not motivos:
        motivos += F.checar_regras(receita, tent, e.get("fechadas", {}))
    # A26: campanha tem UM prazo, o absoluto do manifesto (conferido por guarda_campanha, com segundos). O relógio
    # legado por HH:MM do CENA.md arredonda para baixo e fechava a admissão até um minuto antes; fica só no legado.
    if not eh_campanha() and depois_da_hora():
        motivos.append("passou do prazo da rodada: não comece tentativas novas; escreva o FECHAMENTO.md")
    c = _cena()
    if c:  # Astra, 08/10: a cena é validada aqui também, não só no lançador
        from unreal_macros import cena as C
        motivos += [f"cena inválida: {m}" for m in C.validar_cena(c)["motivos"]]
    if c and c.get("variacoes", 0) > 0:  # linha 2 (Fase 8): depois do sucesso, K variações diferentes de verdade
        from unreal_macros import cena as C
        motivos += C.checar_variacao(receita, tent, c["variacoes"])
    elif receita.get("variacao"):
        motivos.append("esta rodada não tem fase de variações (sem FILA_CENA com 'variacoes')")
    elif _sucesso(tent) and not laboratorio():
        motivos.append(f"já conseguiu ({_sucesso(tent)}): use o tempo para medir outras trocas com tipo 'exploracao' "
                       "numa linhagem nova, ou escreva o FECHAMENTO")
    return e.get("proximo_n", 1), motivos


def _sucesso(tent: list) -> dict | None:
    """A09: o executor usa a MESMA política de sucesso que os outros. Em campanha, a da campanha (prova positiva de
    restauração); fora dela, fila.sucesso. As duas são a mesma apuração (distintas, mesmas condições e versões)."""
    from unreal_macros import fila as F
    if eh_campanha():
        from unreal_macros import campanha as CP
        return CP.sucesso_seguro(tent)
    return F.sucesso(tent)


def _quadros_conhecidos() -> dict:
    """{clipe: quadros} das fichas da biblioteca, para recusar corte maior que o clipe antes do Unreal."""
    try:
        from unreal_macros import biblioteca as BIB
        return {c: f["quadros"] for c, f in BIB.carregar()["fichas"].items() if f.get("quadros")}
    except Exception:  # noqa: BLE001 - sem biblioteca, o seq_build ainda confere no Unreal
        return {}


# ---------- Unreal ----------
CAMPOS_CENA = ("rotulo", "classe", "xyz", "rotacao", "escala")  # o alcance de cena_ok (ver o cabeçalho)


class CenaBloqueada(RuntimeError):
    """A cena não está em condição de receber a tentativa (sobra sem dono comprovado, limpeza não confirmada).
    Nada mais é tocado; a tentativa sai como estado_parcial."""


class Unreal:
    dono = False  # só vira True com um baseline aceito: antes disso meus_atores() não devolve nada
    estudios: tuple = ()  # prefixos TESTE_ESTUDIO_<run>_ REGISTRADOS por uma execução que caiu

    def __init__(self):
        import bloco2_v as V  # muda o cwd para src e configura a trava
        from unreal_macros import macros as M
        from unreal_macros.mcp_client import ASSET, SCENE, SEQ
        self.V, self.M, self.ASSET, self.SCENE, self.SEQ = V, M, ASSET, SCENE, SEQ
        self._nome = None

    def dt(self, f, **k):
        if self._nome is None:
            self._nome = max(re.findall(r"[\w.]*DirectorTools\w*", self.M.cliente().list_toolsets()), key=len)
        r = self.M.cliente().call(self._nome, f, **k)
        r = r.get("returnValue", r) if isinstance(r, dict) else r
        return json.loads(r)

    def cena(self) -> dict:
        """Fotografia do inventário: {caminho: {rotulo, classe, xyz, rotacao, escala}}. Sem confirmação positiva do
        toolset (ok e total batendo) não há fotografia: lança, em vez de devolver uma cena pela metade."""
        r = self.dt("list_actors", class_name="", label_prefix="")
        if not isinstance(r, dict) or r.get("ok") is not True or not isinstance(r.get("atores"), list) \
                or r.get("total") != len(r["atores"]):
            raise RuntimeError(f"inventário da cena não confirmado: {str(r)[:200]}")
        # toolset antigo no editor (antes do reload_toolset) não devolve rotacao/escala: o alcance fica declarado
        return {a["caminho"]: {k: a[k] for k in CAMPOS_CENA if k in a} for a in r["atores"]}

    def ossos(self, seq: str, q: int, nomes: str) -> dict:
        self.dt("seq_eval_frame", sequence_path=seq, frame=q)
        self.M.cliente().call(self.SEQ, "set_playhead_frame", frame=q)
        self.M.cliente().call(self.SEQ, "force_evaluate")
        r = self.dt("bone_world_positions", actor_label=ATOR, bones=nomes)  # leitura em OUTRA chamada
        return {"ossos": r.get("ossos", {}), "inexistentes": r.get("inexistentes", [])}

    def meus_atores(self) -> list:
        """Atores que esta execução pode remover: rótulo EXATO (ATOR, PISO) e o estúdio registrado de uma execução
        que caiu. Só depois de um baseline aceito (nenhum TESTE_FILA_* sem dono): com isso, todo ator de rótulo exato
        ou foi criado por esta execução sob a trava ou estava registrado. Prefixo sozinho não prova propriedade."""
        if not self.dono:
            return []
        out = []
        for a in self.V.TC.teste_actors():
            rot = str(self.M.cliente().call(self.V.TC.ACTOR, "get_label", actor=a))
            if rot in (ATOR, PISO) or (self.estudios and rot.startswith(self.estudios)):
                out.append(a)
        return out


def _video(u, seq: str, quadros: int, n: int, frente) -> dict:
    """A27: o vídeo só existe COMPLETO. Cada quadro de origem vira q<índice>.png na ordem; se uma captura falha, o
    quadro que faltou fica registrado e NENHUM mp4 é gerado (antes os quadros restantes eram renumerados em
    sequência e o vídeo saía mais curto, escondendo a lacuna)."""
    pasta = os.path.join(PASTA, "videos", f"t{n:03d}_quadros")
    os.makedirs(pasta, exist_ok=True)
    origem = list(range(0, quadros, 2))
    faltaram = []
    for k, q in enumerate(origem):
        u.ossos(seq, q, "Hips")
        u.dt("capture_isolated_setup", actor_label=ATOR, yaw_deg=180.0 if frente[1] else 270.0, pitch_deg=6.0,
             distance_cm=420.0, width=640, height=360, also_show=PISO, center_bone="Hips")
        r = u.dt("capture_isolated_shot", directory=pasta, filename=f"q{k:04d}.png")
        if not (isinstance(r, dict) and r.get("ok") is True):
            faltaram.append(q)
    info = {"arquivo": None, "quadros": len(origem) - len(faltaram), "esperados": len(origem), "faltaram": faltaram,
            "completo": not faltaram, "fps": FPS // 2, "quadros_pasta": pasta}
    if faltaram:
        return info
    import imageio_ffmpeg
    mp4 = os.path.join(PASTA, "videos", f"t{n:03d}.mp4")  # nome único por tentativa: nada é sobrescrito
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-n", "-loglevel", "error", "-framerate", str(FPS // 2), "-i",
                    os.path.join(pasta, "q%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4], check=True)
    return dict(info, arquivo=mp4)


def _apagar_seq(u, seq: str) -> dict:
    r = u.dt("seq_close_delete", sequence_path=seq)
    sobrou = [p for p in (u.M.cliente().call(u.ASSET, "find_assets", folder_path="/Game/_AnimLab/Experimentos",
                                             name=seq.split("/")[-1].split(".")[0]) or [])]
    if not isinstance(r, dict) or not r.get("apagou") or sobrou:
        raise RuntimeError(f"sequência não apagada: {r}, ainda existe {sobrou}")
    return r


def _remover_meus_atores(u) -> dict:
    """Remove e CONFERE: o retorno do remove_from_scene (ferramenta da Epic) não é a prova; a prova é o ator não
    aparecer mais."""
    r = [u.M.cliente().call(u.SCENE, "remove_from_scene", actor=a) for a in u.meus_atores()]
    resto = u.meus_atores()
    if resto or any(x is False for x in r):
        raise RuntimeError(f"remoção não confirmada: {len(resto)} ator(es) ainda na cena, retornos {r}")
    return {"removidos": len(r)}


def _limpar(u, seq, passos_limpeza: list):
    """Cada passo protegido sozinho: um erro não impede os seguintes. Um passo só fica ok=True com confirmação
    POSITIVA; retorno negativo, desconhecido ou exceção ficam ok=False (A07)."""
    def tenta(nome, fn):
        try:
            passos_limpeza.append({"passo": nome, "ok": True, "r": fn()})
        except Exception as e:  # noqa: BLE001
            passos_limpeza.append({"passo": nome, "ok": False, "erro": f"{type(e).__name__}: {str(e)[:200]}"})

    def captura():  # contrato do DirectorTools: {ok, restaurado, erros}
        r = u.dt("capture_isolated_restore")
        if not isinstance(r, dict) or r.get("ok") is not True or r.get("erros"):
            raise RuntimeError(f"restauração da captura não confirmada: {str(r)[:200]}")
        return r

    def estudio():  # macros.limpar_estudio não devolve nada e engole erro de remoção: confere pelo inventário
        u.M.limpar_estudio()  # TESTE_ESTUDIO_<pid desta execução>_* (aplicar_clipe cria)
        resto = sorted(v["rotulo"] for v in u.cena().values() if v["rotulo"].startswith(f"TESTE_ESTUDIO_{u.M.RUN}_"))
        if resto:
            raise RuntimeError(f"estúdio desta execução ainda na cena: {resto[:5]}")
        return {"sobras": 0}

    tenta("captura", captura)
    if seq:
        tenta("sequencia", lambda: _apagar_seq(u, seq))
    tenta("atores", lambda: _remover_meus_atores(u))
    tenta("estudio", estudio)


def _foto(n: int, fase: str, cena: dict) -> str:
    """Grava a fotografia da cena (A18) de forma atômica e devolve o caminho relativo à pasta da rodada."""
    pasta = os.path.join(PASTA, "evidencias")
    os.makedirs(pasta, exist_ok=True)
    nome = f"t{n:03d}-{fase}.json"
    tmp = os.path.join(pasta, nome + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cena, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(pasta, nome))
    return f"evidencias/{nome}"


def _alcance(antes: dict, depois: dict) -> dict:
    """Os campos presentes em TODOS os atores das duas fotografias: é o que a comparação de fato cobre."""
    campos = sorted(k for k in CAMPOS_CENA if all(k in v for v in list(antes.values()) + list(depois.values())))
    faltam = [k for k in CAMPOS_CENA if k not in campos]
    d: dict = {"campos": campos, "reduzido": bool(faltam)}
    if faltam:
        d["aviso"] = (f"o toolset carregado no editor não devolveu {faltam}: a restauração foi conferida só em {campos}; "
                      "chame a ferramenta reload_toolset do DirectorTools (ou reabra o editor) para o alcance completo")
    return d


def _diferencas_cena(antes: dict, depois: dict, campos: list) -> dict:
    return {"sumiram": sorted(set(antes) - set(depois)), "sobraram": sorted(set(depois) - set(antes)),
            "alteraram": sorted(c for c in set(antes) & set(depois)
                                if any(antes[c].get(k) != depois[c].get(k) for k in campos))}


def _aceitar_baseline(u, antes: dict, res: dict) -> dict:
    """Decide o que da cena inicial é desta rodada (A05) e devolve a REFERÊNCIA da comparação final.

    - TESTE_FILA_* que NÃO está registrado em estado.json: sem dono comprovado -> CenaBloqueada, nada removido.
    - Sobra REGISTRADA por uma execução que caiu (modo legado: caminhos dos atores, run do estúdio, sequência):
      é removida, a remoção é conferida pelo inventário e só então as listas são zeradas.
    A fotografia inicial gravada em disco é sempre a ORIGINAL; a referência é ela menos o que era nosso e saiu."""
    e = _estado()
    registrados = set(e.get("atores_para_limpar") or [])
    runs = [str(r) for r in e.get("runs_para_limpar") or []]
    seqs = list(e.get("seqs_para_apagar") or [])
    alheios = sorted(v["rotulo"] for c, v in antes.items() if v["rotulo"].startswith(PREFIXO) and c not in registrados)
    if alheios:
        raise CenaBloqueada(f"há ator(es) {alheios[:5]} na cena sem dono comprovado (prefixo não prova propriedade): "
                            "nada foi removido; confira no editor e apague à mão o que for sobra antes de tentar de novo")
    u.dono = True
    if not (registrados or runs or seqs):
        return antes
    u.estudios = tuple(f"TESTE_ESTUDIO_{r}_" for r in runs)
    meus = sorted(c for c, v in antes.items() if c in registrados or (u.estudios and v["rotulo"].startswith(u.estudios)))
    feito: dict = {"atores": meus, "seqs": []}
    try:
        if meus:
            _remover_meus_atores(u)
        for sq in seqs:
            feito["seqs"].append(_apagar_seq(u, sq))
        agora = u.cena()
        resto = sorted(c for c in meus if c in agora)
        if resto:
            raise RuntimeError(f"ainda na cena: {resto[:5]}")
    except Exception as ex:  # noqa: BLE001 - limpeza da sobra não confirmada: bloqueia e mantém o registro
        raise CenaBloqueada(f"sobra registrada de execução anterior não foi limpa com confirmação "
                            f"({type(ex).__name__}: {str(ex)[:200]}); registro mantido em estado.json") from ex
    finally:
        u.estudios = ()
    res["limpou_sobra_propria"] = feito
    e = _estado()
    e["atores_para_limpar"], e["runs_para_limpar"], e["seqs_para_apagar"] = [], [], []
    _gravar_estado(e)
    return {c: v for c, v in antes.items() if c not in meus}


def executar(receita: dict, n: int, video: bool = False, reserva: dict | None = None) -> dict:
    """Uma tentativa completa. Grava 'tentativa_inicio' antes de tocar na cena e 'tentativa' no fim, sempre.
    `reserva` = a reserva feita na admissão (main); sem ela (ensaios, testes) a reserva é feita aqui, e uma
    reserva que já exista e não seja desta execução recusa a tentativa (A01)."""
    from unreal_macros import blocos as B
    from unreal_macros import fila as F
    from unreal_macros import receita as R
    from unreal_macros import trava
    motivos_campanha = guarda_campanha() + guarda_personagem(receita)
    if motivos_campanha:
        return {"recusada": motivos_campanha}
    try:
        e = _estado()
        p = e.get("pendente")
        if reserva is None and p:
            return {"recusada": [f"há uma reserva da tentativa {p.get('n')} que não é desta execução: espere (resultado "
                                 f"{p.get('n')}) ou use 'tentar', que reconcilia o que caiu"]}
        if reserva is not None and (p or {}).get("execucao") != reserva.get("execucao"):
            return {"recusada": ["a reserva desta execução foi alterada por outra: nada foi executado"]}
        if reserva is None:
            _reservar(n)
        e = _estado()
        e["pendente"].update(pid=os.getpid(), fase="executando")
        _gravar_estado(e)
    except EstadoIlegivel as ex:
        return {"recusada": [str(ex)]}
    execucao = e["pendente"]["execucao"]
    base: dict = {"n": n, "execucao": execucao, "linhagem": receita["linhagem"], "tipo": receita["tipo"], "de": receita.get("de"),
            "hipotese": receita.get("hipotese"), "observacao": receita.get("observacao"), "receita": receita["passos"],
            "experimento": receita.get('experimento'), "personagem_solicitado": receita.get('personagem') or (_cena() or {}).get('personagem') or CONDICOES['personagem'],
            "variacao": bool(receita.get("variacao")),
            "assinatura": R.assinatura(receita), "versoes": versoes(), "fps": FPS, "condicoes": dict(CONDICOES)}
    _acrescentar("tentativas.jsonl", dict(base, tipo_linha="tentativa_inicio", quando=_agora()))
    res: dict = dict(base, tipo_linha="tentativa", quando_inicio=e["pendente"]["desde"], passou=False, nota=None,
               classe_erro=None, motivo=None, video=None, cena_ok=None)
    u = seq = antes = None
    limpeza = []
    try:
        u = Unreal()
        os.chdir(RAIZ)
        trava.pegar(u.M.TRAVA, f"fila-t{n}", log=os.path.join(os.path.dirname(u.M.TRAVA), "trava.log"))
        u.M._pilha["n"] += 1
        try:
            inicial = u.cena()  # sem inventário confirmado nada é tocado (cena_ok fica None: desconhecido)
            res["cena_fotos"] = [_foto(n, "antes", inicial)]  # A18: gravada ANTES de qualquer mutação
            try:
                antes = _aceitar_baseline(u, inicial, res)  # A05: a referência nunca é refeita depois de remover
            except CenaBloqueada as ex:
                res["cena_ok"], res["cena_bloqueio"] = False, str(ex)
                res["cena_diferencas"] = _diferencas_cena(inicial, u.cena(), _alcance(inicial, inicial)["campos"])
                raise
            e = _estado()
            e["pendente"]["run"] = u.M.RUN
            _gravar_estado(e)
            try:
                u.V.caixa(PISO, ZX, ZY + 300, -100, 8, 14, 1)
                u.V.TC.boneco(ATOR, ZX, ZY)
                # registra em disco o que ESTA execução criou, antes de seguir: se ela cair, a próxima sabe o que é dela
                e = _estado()
                e["pendente"]["atores"] = sorted(c for c, v in u.cena().items()
                                                 if c not in antes and v["rotulo"] in (ATOR, PISO))
                _gravar_estado(e)
                clipes = sorted({p["clipe"] for p in receita["passos"]} | {"Walking"})
                for c in clipes:
                    r = u.M.importar_clipe(c)  # macro: erro volta no relatório (ok=False), não como exceção
                    if isinstance(r, dict) and not r.get("ok", False):
                        raise LookupError(f"clipe {c}: {r.get('bloqueio') or r.get('erro') or r}")
                u.M.aplicar_clipe(ATOR, "Walking", loop=True, manter_se_falhar=True, checar_movimento=False)  # roll
                u.dt("set_pose_eval", actor_label=ATOR, on=True)
                o = u.dt("bone_world_positions", actor_label=ATOR, bones="LeftFoot,RightFoot,LeftToeBase,RightToeBase")["ossos"]
                fx = sum(o[f"{lado}ToeBase"][0] - o[f"{lado}Foot"][0] for lado in ("Left", "Right"))
                fy = sum(o[f"{lado}ToeBase"][1] - o[f"{lado}Foot"][1] for lado in ("Left", "Right"))
                frente = (0.0, math.copysign(1.0, fy)) if abs(fy) >= abs(fx) else (math.copysign(1.0, fx), 0.0)
                passos = R.passos_para_seq_build(receita, B.caminho)
                s = u.dt("seq_build", actor_label=ATOR, steps_json=json.dumps(passos), dir_x=frente[0], dir_y=frente[1], fps=FPS)
                if not s.get("ok"):
                    raise LookupError(f"seq_build: {s}")
                seq = s["sequencia"]
                e = _estado()
                e["pendente"]["seq"] = seq
                _gravar_estado(e)
                faixas = s["faixas"]
                res["montagem"] = {"faixas": faixas, "quadros": s["quadros"], "frente": frente,
                                   "assets": [p["anim"] for p in passos]}
                amostras, faltas = [], set()
                esperados = F.quadros_a_amostrar(faixas)
                try:
                    for q in esperados:
                        r = u.ossos(seq, q, ",".join(F.OSSOS))
                        faltas |= set(r["inexistentes"])
                        amostras.append((q, r["ossos"]))
                finally:
                    # A17: as amostras de TODA tentativa ficam em disco antes de avaliar (reprovada, inválida ou com
                    # queda no meio); conjunto incompleto vai para um arquivo "-parcial" e nunca passa por completo
                    if amostras:
                        res["amostras_completas"] = len(amostras) == len(esperados)
                        res["amostras_arquivo"] = _gravar_amostras(n, amostras, res["amostras_completas"])
                        res["amostras"] = len(amostras)
                av = F.avaliar(amostras, faixas, [p["papel"] for p in receita["passos"]], FPS)
                if faltas:
                    av = {"valida": False, "nota": None, "motivo": f"ossos inexistentes: {sorted(faltas)}"}
                res.update(nota=av.get("nota"), avaliacao={k: v for k, v in av.items() if k != "trocas"},
                           amostras=len(amostras))
                # A08: a MEDIDA fica guardada à parte; "passou" (aprovação da tentativa) só é decidido no fim
                res["medida"] = {"valida": bool(av.get("valida")), "nota": av.get("nota"),
                                 "passou": bool(av.get("valida")) and av.get("nota") == 0}
                for t in av.get("trocas", []):
                    a, b = receita["passos"][t["troca"]], receita["passos"][t["troca"] + 1]
                    _acrescentar("encaixes.jsonl", dict(t, n=n, clipe_a=a["clipe"], clipe_b=b["clipe"],
                                                        asset_a=passos[t["troca"]]["anim"], asset_b=passos[t["troca"] + 1]["anim"],
                                                        turn_deg_b=b.get("turn_deg", 0), fps=FPS, versoes=base["versoes"],
                                                        condicoes=base["condicoes"], frente=frente, chao_z=0.0,
                                                        quando=_agora(), **_ajustes_da_troca(a, b)))
                res["trocas"] = [{k: t[k] for k in ("troca", "quadril_cm", "pior_osso", "pior_osso_cm", "virada_deg", "nota")}
                                 for t in av.get("trocas", [])]
                if not av.get("valida"):
                    res["classe_erro"], res["motivo"] = "medida_instavel", av.get("motivo")
                else:
                    res["passou"] = av["nota"] == 0
                    falhas = [k for k, v in av["intencoes"].items() if not v["passou"]] + \
                             [f"troca {t['troca']} ({t['pior_osso']} {t['pior_osso_cm']} cm, quadril {t['quadril_cm']}, "
                              f"virada {t['virada_deg']}°)" for t in av["trocas"] if t["nota"] > 0]
                    res["classe_erro"] = None if res["passou"] else "encaixe"
                    res["falhas"] = sorted([k for k, v in av["intencoes"].items() if not v["passou"]] +
                                           [f"troca{t['troca']}" for t in av["trocas"] if t["nota"] > 0])
                    res["motivo"] = "passou" if res["passou"] else "; ".join(falhas)
                if video:
                    res["video"] = _video(u, seq, s["quadros"], n, frente)
                    if not res["video"]["completo"]:  # A27 + A08: sem a entrega completa não há aprovação
                        raise RuntimeError(f"vídeo incompleto: faltaram os quadros {res['video']['faltaram'][:10]} "
                                           f"({res['video']['quadros']} de {res['video']['esperados']} capturas)")
            except LookupError as ex:
                res["classe_erro"], res["motivo"] = "dependencia", str(ex)[:400]
            finally:
                _limpar(u, seq, limpeza)
                depois = u.cena()
                res["cena_fotos"].append(_foto(n, "depois", depois))
                res["cena_alcance"] = _alcance(antes, depois)
                dif = _diferencas_cena(antes, depois, res["cena_alcance"]["campos"])
                res["cena_ok"] = not any(dif.values()) and all(p["ok"] for p in limpeza)
                res["cena_diferencas"] = dif
        finally:
            u.M._pilha["n"] -= 1
            trava.soltar(u.M.TRAVA)
    except Exception as ex:  # noqa: BLE001
        falha = f"{type(ex).__name__}: {str(ex)[:300]}"
        if res["classe_erro"] is None:  # inclui a medida que já tinha passado: a falha posterior não some (A08)
            res["classe_erro"] = "infraestrutura"
            res["motivo"] = (f"a medida passou (nota 0), mas a tentativa falhou depois: {falha}"
                             if res["motivo"] == "passou" else res["motivo"] or falha)
        elif res["motivo"]:  # a medida já tinha reprovado; a falha posterior (vídeo, limpeza) também fica à vista
            res["motivo"] = f"{res['motivo']}; e depois da medida: {falha}"
        res["motivo"] = res["motivo"] or falha
        res["erro_original"] = traceback.format_exc()[-1500:]
    res["limpeza"] = limpeza
    res["quando"] = _agora()
    if res["cena_ok"] is False:
        res["classe_erro"] = "estado_parcial"
        res["motivo"] = res.get("cena_bloqueio") or f"CENA DIFERENTE DO INÍCIO: {res.get('cena_diferencas')} / limpeza {limpeza}"
    # A08: aprovação operacional = a medida passou E nada falhou depois E a cena voltou comprovadamente ao início.
    # A nota continua sendo a medida; ela sozinha não aprova a tentativa nem a manda para a biblioteca.
    res["passou"] = bool((res.get("medida") or {}).get("passou") and res["classe_erro"] is None and res["cena_ok"] is True)
    _acrescentar("tentativas.jsonl", res)
    e = _estado()
    if (e.get("pendente") or {}).get("execucao") == execucao:  # só a PRÓPRIA reserva sai (A01)
        e["pendente"] = None
        _gravar_estado(e)
    if res["passou"]:  # só tentativa APROVADA é encaminhada (antes: qualquer nota 0)
        registrar_na_biblioteca()
    _relatorio_final_se_encerrada()
    return res


def _ajustes_da_troca(a: dict, b: dict) -> dict:
    """Campos da Fase 4 que mudam a troca A -> B (só os que não são zero: as trocas antigas ficam iguais)."""
    d = {"corte_fim_a": a.get("corte_fim_q", 0), "turn_fim_a": a.get("turn_fim_deg", 0), "inicio_b": b.get("inicio_q", 0)}
    return {k: v for k, v in d.items() if v}


def _gravar_amostras(n: int, amostras: list, completo: bool = True) -> str:
    """Grava [[quadro, ossos], ...] e devolve o caminho relativo à rodada. Completo: amostras/tNNN.json (o formato
    que a biblioteca copia para os blocos). Incompleto: amostras/tNNN-parcial.json, que a biblioteca não lê."""
    pasta = os.path.join(PASTA, "amostras")
    os.makedirs(pasta, exist_ok=True)
    nome = f"t{n:03d}.json" if completo else f"t{n:03d}-parcial.json"
    tmp = os.path.join(pasta, nome + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([[q, o] for q, o in amostras], f)
    os.replace(tmp, os.path.join(pasta, nome))
    return f"amostras/{nome}"


def registrar_na_biblioteca(pasta_bib: str | None = None) -> dict:
    """Depois de uma nota 0: reimporta a rodada para a biblioteca (idempotente). O bloco só nasce com 3 notas 0 da
    mesma assinatura nas mesmas condições (biblioteca._blocos). Falha aqui NUNCA derruba a tentativa: fica registrada
    em biblioteca.jsonl da rodada. A pasta da biblioteca pode vir de BIBLIOTECA_PASTA (testes)."""
    from unreal_macros import biblioteca as BIB
    destino = pasta_bib or os.environ.get("BIBLIOTECA_PASTA") or BIB.PASTA
    try:
        r = BIB.importar_rodada(PASTA, os.path.basename(PASTA))
        total = BIB.mesclar(destino, r)
        linha = {"ok": True, "blocos": [b["id"] for b in r["blocos"]], "na_biblioteca": total}
    except Exception as ex:  # noqa: BLE001
        linha = {"ok": False, "erro": f"{type(ex).__name__}: {str(ex)[:300]}"}
    linha["quando"] = _agora()
    _acrescentar("biblioteca.jsonl", linha)
    return linha


def curto(res: dict) -> dict:
    """O que o Qwen precisa ler (resposta curta)."""
    return {k: res.get(k) for k in ("n", "linhagem", "tipo", "passou", "nota", "medida", "classe_erro", "motivo", "trocas",
                                    "cena_ok", "video", "experimento", "personagem_solicitado", "condicoes")} | {"intencoes": {k: v.get("passou") for k, v in
                                                                          (res.get("avaliacao") or {}).get("intencoes", {}).items()}}


def recuperar_pendente() -> dict | None:
    """Tentativa que caiu (dono morto), modo legado: registra como interrompida e passa adiante o que ELA registrou
    como seu (atores criados, run do estúdio, sequência). A próxima tentativa limpa só isso, com conferência
    (_aceitar_baseline); TESTE_FILA_* que não esteja registrado bloqueia. Em campanha nada é recuperado sozinho."""
    if eh_campanha():
        return None  # restauração desconhecida bloqueia; não limpar na próxima tentativa
    e = _estado()
    p = e.get("pendente")
    if not p:
        return None
    processo = _pid_estado(p.get("pid"))
    if processo == P.VIVO:
        return None
    if processo != P.MORTO:  # DESCONHECIDO não autoriza recuperar/apagar a reserva
        return None
    _acrescentar("tentativas.jsonl", {"tipo_linha": "tentativa_interrompida", "n": p["n"], "pendente": p, "quando": _agora()})
    e["pendente"] = None
    e.setdefault("runs_para_limpar", []).append(p.get("run") or str(p.get("pid")))  # o estúdio dela tem o pid no nome
    e.setdefault("atores_para_limpar", []).extend(p.get("atores") or [])  # só o que ela registrou como criado por ela
    if p.get("seq"):
        e.setdefault("seqs_para_apagar", []).append(p["seq"])
    _gravar_estado(e)
    return p


def estado_resumo() -> dict:
    """CONSULTA: não escreve nada (A03). Com o estado perdido ou ilegível, mostra o histórico e diz o motivo."""
    from unreal_macros import fila as F
    e, ilegivel = _estado_lido()
    tent = tentativas_validas()
    lin = F.estado_linhagens(tent, e.get("fechadas", {}))
    return {"tentativas": len(tent), "pendente": e.get("pendente"),
            "pendente_processo": _pid_estado(e["pendente"].get("pid")) if e.get("pendente") else None,
            "proximo_n": e.get("proximo_n", 1),
            "linhagens": lin, "fechadas": e.get("fechadas", {}), "sucesso": _sucesso(tent),
            "ultimas": [curto(t) | {"receita": [p["clipe"] for p in t["receita"]]} for t in tent[-5:]],
            "exploracoes_nas_ultimas_10": sum(t.get("tipo") == "exploracao" for t in tent[-10:]),
            "depois_do_prazo": None if ilegivel else _prazo_encerrado(e), "versoes": versoes(),
            **({"estado_ilegivel": ilegivel} if ilegivel else {}), **_resumo_variacoes(tent)}


def _resumo_variacoes(tent: list) -> dict:
    c = _cena()
    if not c or c.get("variacoes", 0) <= 0:
        return {}
    from unreal_macros import cena as C
    ev = C.estado_variacoes(tent, c["variacoes"])
    return {"cena": c.get("nome"), "variacoes": {k: v for k, v in ev.items() if k != "referencias"}}


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 2
    from unreal_macros import trava
    try:
        return _comando(argv[0], argv)
    except EstadoIlegivel as ex:  # A03: estado perdido/ilegível recusa, sem escrever por cima
        print(json.dumps({"recusada": [str(ex)]}, ensure_ascii=False))
        return 1
    except trava.TravaOcupada as ex:  # A01: outra admissão nesta rodada, agora
        print(json.dumps({"recusada": [f"outra admissão desta rodada está em curso: {ex}"]}, ensure_ascii=False))
        return 1


def _recuperar_sob_admissao():
    """Só nos comandos que ESCREVEM (as consultas não mudam nada, A03): primeiro a reconciliação da A04, depois a
    recuperação do modo legado."""
    rec = reconciliar_pendente()
    if rec:
        print(json.dumps({"aviso": f"a tentativa {rec['n']} já tinha o resultado final seguro; pendência retirada"},
                         ensure_ascii=False))
    rec = recuperar_pendente()
    if rec:
        print(json.dumps({"aviso": f"a tentativa {rec['n']} tinha caído; registrada como interrompida"}, ensure_ascii=False))


def _admitir(cmd: str, argv: list) -> tuple:
    """A parte EXCLUSIVA de tentar / rodar-agora / _filho. Devolve (código, None) para sair, ou
    (None, (receita, n, video, reserva)) para executar fora da exclusão (a tentativa leva minutos)."""
    def recusa(motivos: list, execucao: str | None = None) -> tuple:
        _liberar_reserva(execucao)  # só a reserva DESTA autorização, e só se nada começou
        depois = _estado_lido()[0]
        # Evidência da recusa (13/10): o que foi recusado, por quê, e que nenhum número foi gasto. É o que o teste
        # da versão confere (unreal_macros/teste_versao.py); antes a recusa só existia na resposta ao agente.
        _acrescentar("recusas.jsonl", {"tipo_linha": "recusa", "comando": cmd, "motivos": motivos, "quando": _agora(),
                                       "proximo_n_antes": antes.get("proximo_n", 1), "proximo_n_depois": depois.get("proximo_n", 1),
                                       "pendente_n": (depois.get("pendente") or {}).get("n")})
        print(json.dumps({"recusada": motivos}, ensure_ascii=False))
        return 1, None

    antes = _estado_lido()[0]
    _recuperar_sob_admissao()
    aut = (_estado().get("autorizado") or {}) if cmd == "_filho" else {}
    meu = len(argv) > 3 and aut.get("n") == int(argv[2]) and aut.get("nonce") == argv[3]
    motivos_campanha = guarda_campanha()
    if motivos_campanha:
        return recusa(motivos_campanha, aut.get("execucao") if meu else None)
    try:
        with open(argv[1], "rb") as f:
            bruto = f.read()
        receita = json.loads(bruto.decode("utf-8"))
        if not isinstance(receita, dict):
            raise ValueError("a receita tem de ser um objeto JSON")
    except (OSError, ValueError) as ex:
        return recusa([f"receita ilegível: {ex}"], aut.get("execucao") if meu else None)
    video = '--video' in argv or (bool(receita.get('variacao')) and not laboratorio())  # toda variação sai com vídeo (Fase 8)
    if cmd == "_filho":  # só com a autorização de uso único que o 'tentar' grava depois do preparar (Astra, 08/10)
        if not meu:
            print(json.dumps({"recusada": ["_filho é interno: use 'tentar' (passa pelas regras antes do Unreal)"]},
                             ensure_ascii=False))
            return 1, None
        e = _estado()
        e.pop("autorizado", None)  # uso único: consumida aqui, aceite ou não
        p = e.get("pendente") or {}
        if aut.get("receita_sha") != hashlib.sha256(bruto).hexdigest():  # A02: o conteúdo é o que foi validado?
            if p.get("execucao") == aut.get("execucao") and p.get("fase") == "reservada":
                e["pendente"] = None
            _gravar_estado(e)
            print(json.dumps({"recusada": ["a receita deste arquivo não é a que foi validada (o conteúdo mudou depois "
                                           "do 'tentar'): nada foi executado; envie a receita de novo com 'tentar'"]},
                             ensure_ascii=False))
            return 1, None
        if not aut.get("execucao") or p.get("execucao") != aut["execucao"]:
            _gravar_estado(e)
            print(json.dumps({"recusada": ["a reserva desta autorização não existe mais: use 'tentar' de novo"]},
                             ensure_ascii=False))
            return 1, None
        p["pid"] = os.getpid()
        _gravar_estado(e)
        return None, (receita, int(argv[2]), video, dict(p))
    n, motivos = preparar(receita)
    if motivos:
        return recusa(motivos)
    if cmd == "rodar-agora":
        return None, (receita, n, video, _reservar(n))
    os.makedirs(os.path.join(PASTA, "receitas"), exist_ok=True)
    copia = os.path.join(PASTA, "receitas", f"t{n:03d}.json")
    texto = json.dumps(receita, ensure_ascii=False, indent=1).encode("utf-8")
    with open(copia, "wb") as f:
        f.write(texto)
    reserva = _reservar(n)  # número e dono reservados ANTES de criar o filho e de anunciar "rodando"
    e = _estado()
    e["autorizado"] = {"n": n, "nonce": uuid.uuid4().hex, "execucao": reserva["execucao"],
                       "receita_sha": hashlib.sha256(texto).hexdigest()}  # A02: vale só para ESTE conteúdo
    _gravar_estado(e)
    try:
        with open(os.path.join(PASTA, "receitas", f"t{n:03d}_saida.txt"), "w", encoding="utf-8") as saida:
            filho = subprocess.Popen([PY, os.path.abspath(__file__), "_filho", copia, str(n), e["autorizado"]["nonce"]]
                                     + (["--video"] if video else []),
                                     cwd=RAIZ, stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     creationflags=0x00000008 | 0x00000200)
    except OSError as ex:
        return recusa([f"não consegui lançar a tentativa {n}: {ex}"], reserva["execucao"])
    e = _estado()
    if (e.get("pendente") or {}).get("execucao") == reserva["execucao"]:
        e["pendente"]["pid"] = filho.pid  # o dono da reserva passa a ser o filho; ele confirma ao entrar
        _gravar_estado(e)
    print(json.dumps({"n": n, "status": "rodando", "dica": f"em 3 a 15 min: resultado {n}"}, ensure_ascii=False))
    return 0, None


def _comando(cmd: str, argv: list) -> int:
    if cmd in ("tentar", "rodar-agora", "_filho"):
        with _admissao():
            codigo, admitida = _admitir(cmd, argv)
        if admitida is None:
            return codigo
        receita, n, video, reserva = admitida
        resultado = executar(receita, n, video, reserva)
        if cmd == "rodar-agora":
            print(json.dumps(resultado if resultado.get("recusada") else curto(resultado), ensure_ascii=False, default=str))
        return 1 if resultado.get("recusada") else 0
    if cmd == "resultado":
        n = int(argv[1])
        fim = [t for t in _ler_jsonl("tentativas.jsonl") if t.get("n") == n and t.get("tipo_linha") in
               ("tentativa", "tentativa_interrompida")]
        if fim:
            print(json.dumps(curto(fim[-1]) if fim[-1]["tipo_linha"] == "tentativa" else fim[-1], ensure_ascii=False, default=str))
        else:
            p = _estado_lido()[0].get("pendente") or {}
            processo = _pid_estado(p.get("pid")) if p.get("n") == n else None
            status = ("rodando" if processo == P.VIVO else
                      "processo MORTO; recuperação pendente" if processo == P.MORTO else
                      "processo DESCONHECIDO; espere" if processo is not None else "não encontrada")
            print(json.dumps({"n": n, "status": status, "processo": processo}, ensure_ascii=False))
        return 0
    if cmd == "estado":
        print(json.dumps(estado_resumo(), ensure_ascii=False, default=str, indent=1))
        return 0
    if cmd == "fechar-linhagem":
        with _admissao():
            _recuperar_sob_admissao()
            e = _estado()
            e.setdefault("fechadas", {})[argv[1]] = " ".join(argv[2:]) or "sem motivo"
            _gravar_estado(e)
            _acrescentar("tentativas.jsonl", {"tipo_linha": "linhagem_fechada", "linhagem": argv[1],
                                              "motivo": e["fechadas"][argv[1]], "quando": _agora()})
        print(json.dumps({"fechada": argv[1]}, ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
