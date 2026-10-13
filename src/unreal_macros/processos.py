"""Consulta não destrutiva de PID, sem texto localizado ou inferência pela idade.

VIVO/MORTO são evidência do SO neste instante; DESCONHECIDO não autoriza recuperar
reservas. Não comprova identidade do dono (PID reutilizado continua pendência).
"""
import os

VIVO = "VIVO"
MORTO = "MORTO"
DESCONHECIDO = "DESCONHECIDO"


def _kernel32():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.OpenProcess.restype = wintypes.HANDLE
    k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    k.CloseHandle.restype = wintypes.BOOL
    return k


def _ultimo_erro():
    import ctypes
    return ctypes.get_last_error()


def _consultar_windows(pid: int) -> str:
    # Mesmo mecanismo de espera de tools/astra.py, mas falhas NÃO significam morte.
    k = _kernel32()
    h = k.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE; espera com timeout zero
    if not h:
        return MORTO if _ultimo_erro() == 87 else DESCONHECIDO
    try:
        res = k.WaitForSingleObject(h, 0)
        return {0: MORTO, 258: VIVO}.get(res, DESCONHECIDO)
    finally:
        k.CloseHandle(h)


def _consultar_posix(pid: int) -> str:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return MORTO
    except OSError:
        return DESCONHECIDO
    return VIVO


def estado_processo(pid) -> str:
    """PID ausente/inválido ou consulta falha é DESCONHECIDO, nunca booleano."""
    if isinstance(pid, str) and pid.isascii() and pid.isdecimal():
        pid = int(pid)
    if type(pid) is not int or not 0 < pid < 2**32:
        return DESCONHECIDO
    try:
        return _consultar_windows(pid) if os.name == "nt" else _consultar_posix(pid)
    except Exception:  # falha de API/consulta: mantém estado conservador explícito
        return DESCONHECIDO
