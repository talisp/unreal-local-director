"""Trava de operador único no Unreal com dono VERIFICÁVEL (v0.0.2, bloco 2).

A trava guarda pid + horário de criação do processo dono (+ host e nonce). O estado é decidido por fatos do
sistema operacional, nunca pela idade da trava:
  livre       — não há arquivo;
  propria     — o dono é este processo;
  viva        — o processo dono existe e é o MESMO (mesmo horário de criação);
  morta       — o pid não existe, já terminou, ou foi reaproveitado por outro processo (horário diferente);
  corrompida  — arquivo ilegível ou sem pid: NUNCA é tratada como órfã em silêncio.
Travas antigas (sem horário de criação, escritas pela v0.0.1) são conservadoras: pid existente = viva.
"""
import datetime as dt
import json
import os
import socket
import sys
import time
import uuid

_CRIACAO_TOLERANCIA_S = 2.0


class TravaOcupada(RuntimeError):
    """O Unreal está com outro operador VIVO: é uma ESPERA legítima, não um erro da tentativa."""
    def __init__(self, msg: str, estado: dict):
        super().__init__(msg)
        self.estado = estado


def _criacao_processo(pid: int) -> float | None:
    """Epoch de criação do processo `pid`, ou None se ele não existe/terminou. Lança PermissionError se existe mas
    não dá para consultar (tratado como vivo pelo chamador)."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        except PermissionError:
            raise
        try:
            return os.stat(f"/proc/{pid}").st_ctime
        except OSError:
            return 0.0
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        err = ctypes.get_last_error()
        if err == 5:  # acesso negado: existe
            raise PermissionError(pid)
        return None  # 87 = parâmetro inválido: não existe
    try:
        codigo = wintypes.DWORD()
        if k32.GetExitCodeProcess(h, ctypes.byref(codigo)) and codigo.value != 259:  # 259 = STILL_ACTIVE
            return None
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return 0.0
        ft = (c.dwHighDateTime << 32) | c.dwLowDateTime
        return ft / 1e7 - 11644473600.0  # FILETIME (100 ns desde 1601) -> epoch
    finally:
        k32.CloseHandle(h)


def _info_propria(nome: str) -> dict:
    return {"pid": os.getpid(), "inicio": _criacao_processo(os.getpid()), "host": socket.gethostname(),
            "nonce": uuid.uuid4().hex[:12], "macro": nome, "desde": time.time()}


def estado(caminho: str) -> dict:
    """Diagnóstico da trava: {'estado': livre|propria|viva|morta|corrompida, 'info': ..., 'motivo': ...}."""
    if not os.path.exists(caminho):
        return {"estado": "livre", "info": None, "motivo": "sem arquivo de trava"}
    try:
        info = json.load(open(caminho, encoding="utf-8"))
        pid = int(info["pid"])
    except Exception as e:  # noqa: BLE001
        return {"estado": "corrompida", "info": None, "motivo": f"trava ilegível ou sem pid ({type(e).__name__})"}
    if info.get("host") and info["host"] != socket.gethostname():
        return {"estado": "viva", "info": info, "motivo": f"dono em outra máquina ({info['host']}): não dá para verificar"}
    if pid == os.getpid():
        return {"estado": "propria", "info": info, "motivo": "dono é este processo"}
    try:
        criacao = _criacao_processo(pid)
    except PermissionError:
        return {"estado": "viva", "info": info, "motivo": f"processo {pid} existe (sem permissão de consulta)"}
    if criacao is None:
        return {"estado": "morta", "info": info, "motivo": f"processo {pid} não existe ou já terminou"}
    if info.get("inicio") is None:
        return {"estado": "viva", "info": info, "motivo": f"processo {pid} existe (trava antiga sem horário de criação)"}
    if criacao and abs(criacao - float(info["inicio"])) > _CRIACAO_TOLERANCIA_S:
        return {"estado": "morta", "info": info,
                "motivo": f"pid {pid} foi reaproveitado por outro processo (criado em outro horário): dono original morreu"}
    return {"estado": "viva", "info": info, "motivo": f"processo dono {pid} está vivo"}


def _registrar(log: str, evento: dict):
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(evento, quando=dt.datetime.now().isoformat(timespec="seconds")), ensure_ascii=False) + "\n")
    except OSError:
        pass


def pegar(caminho: str, nome: str, log: str | None = None):
    """Toma a trava. Se o dono está comprovadamente MORTO, assume a trava e registra. Viva ou corrompida: recusa."""
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps(_info_propria(nome)).encode())
            os.close(fd)
            return
        except FileExistsError:
            st = estado(caminho)
            if st["estado"] in ("propria", "morta"):
                os.remove(caminho)
                if st["estado"] == "morta" and log:
                    _registrar(log, {"evento": "trava_assumida", "motivo": st["motivo"], "dono_anterior": st["info"]})
                continue
            if st["estado"] == "corrompida":
                raise RuntimeError(f"trava do Unreal corrompida ({st['motivo']}): use liberar_trava_orfa(corrompida=True) "
                                   "depois de confirmar que ninguém está operando")
            raise TravaOcupada(f"Unreal ocupado por outro operador: {st['motivo']} ({st['info']}); espere", st)
    raise RuntimeError("não consegui a trava do Unreal")


def soltar(caminho: str):
    try:
        if json.load(open(caminho, encoding="utf-8")).get("pid") == os.getpid():
            os.remove(caminho)
    except Exception:  # noqa: BLE001
        pass


def liberar_orfa(caminho: str, log: str, corrompida: bool = False) -> dict:
    """Libera a trava SOMENTE se o dono está comprovadamente morto (ou, com corrompida=True, se o arquivo está
    corrompido). Idade nunca é prova. Toda decisão é registrada."""
    st = estado(caminho)
    liberar = st["estado"] == "morta" or (st["estado"] == "corrompida" and corrompida)
    if liberar:
        try:
            os.remove(caminho)
        except FileNotFoundError:
            pass
    decisao = {"evento": "liberar_trava_orfa", "liberada": liberar, "estado": st["estado"], "motivo": st["motivo"],
               "dono": st["info"], "corrompida_confirmada": corrompida}
    _registrar(log, decisao)
    if not liberar:
        decisao["recusa"] = {"livre": "não há trava", "propria": "a trava é deste processo",
                             "viva": "o dono está vivo: espere", "corrompida": "trava corrompida: confirme com corrompida=True",
                             "morta": ""}[st["estado"]]
    return decisao
