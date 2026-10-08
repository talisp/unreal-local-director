"""Testes do bloqueio offline do cliente da 8001 (UNREAL_MACROS_OFFLINE; Fase 2a, S1). Não usa o Unreal.

O socket é trocado por um falso que conta as conexões e recusa todas: nada sai da máquina, com ou sem a variável.
O controle (sem a variável) prova que o falso enxerga as tentativas; sem ele, o "0 conexões" passaria por construção.
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unreal_macros import mcp_client  # noqa: E402
from unreal_macros.mcp_client import ACTOR, Client, UnrealError, UnrealOffline  # noqa: E402


class SocketFalso:
    """Troca create_connection e socket.connect por versões que contam e recusam."""

    def __enter__(self):
        self.conexoes = []
        self._cc, self._con, self._conex = socket.create_connection, socket.socket.connect, socket.socket.connect_ex

        def cc(endereco, *a, **k):
            self.conexoes.append(endereco)
            raise ConnectionRefusedError("socket falso do teste: recusado")

        def con(s, endereco):
            self.conexoes.append(endereco)
            raise ConnectionRefusedError("socket falso do teste: recusado")

        def conex(s, endereco):
            self.conexoes.append(endereco)
            return 10061

        socket.create_connection, socket.socket.connect, socket.socket.connect_ex = cc, con, conex
        return self

    def __exit__(self, *exc):
        socket.create_connection, socket.socket.connect, socket.socket.connect_ex = self._cc, self._con, self._conex


class Variavel:
    def __init__(self, valor):
        self.valor = valor

    def __enter__(self):
        self.antes = os.environ.get(mcp_client.OFFLINE_VAR)
        if self.valor is None:
            os.environ.pop(mcp_client.OFFLINE_VAR, None)
        else:
            os.environ[mcp_client.OFFLINE_VAR] = self.valor

    def __exit__(self, *exc):
        if self.antes is None:
            os.environ.pop(mcp_client.OFFLINE_VAR, None)
        else:
            os.environ[mcp_client.OFFLINE_VAR] = self.antes


def _erro(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return e
    return None


def testa_bloqueia_sem_abrir_conexao():
    with Variavel("1"), SocketFalso() as falso:
        c = Client()
        for chamada in (c.connect, c.list_toolsets, lambda: c.call(ACTOR, "get_label", actor={}),
                        lambda: c.script("def run(): return {}")):
            e = _erro(chamada)
            assert isinstance(e, UnrealOffline), f"esperava UnrealOffline, veio {type(e).__name__}: {e}"
            assert isinstance(e, UnrealError)  # o envelope @macro o transforma em bloqueio, como os outros erros
            assert e.codigo == "offline_bloqueado" and str(e).startswith("offline_bloqueado")
        assert falso.conexoes == [], f"abriu conexão com a variável ligada: {falso.conexoes}"
        assert c.sid is None


def testa_controle_sem_variavel():
    # Controle positivo: sem a variável, o cliente TENTA conectar e o falso registra a tentativa.
    with Variavel(None), SocketFalso() as falso:
        e = _erro(Client(timeout=2).connect)
        assert e is not None and not isinstance(e, UnrealOffline), f"sem a variável não pode bloquear: {e!r}"
        assert len(falso.conexoes) >= 1, "o socket falso não viu a tentativa: o teste de 0 conexões não provaria nada"
        assert any("8001" in str(x) for x in falso.conexoes), falso.conexoes


def testa_valores_da_variavel():
    for valor, esperado in ((None, False), ("", False), ("0", False), (" 0 ", False),
                            ("1", True), ("true", True), ("sim", True)):
        with Variavel(valor):
            assert mcp_client.offline() is esperado, f"{valor!r}: esperava {esperado}"


def testa_lida_a_cada_chamada():
    # A variável vale na hora da chamada, não na importação: ligar depois de criar o cliente já bloqueia.
    with SocketFalso() as falso:
        with Variavel(None):
            c = Client(timeout=2)
        with Variavel("1"):
            assert isinstance(_erro(c.connect), UnrealOffline)
        assert falso.conexoes == []


if __name__ == "__main__":
    testes = (testa_bloqueia_sem_abrir_conexao, testa_controle_sem_variavel, testa_valores_da_variavel,
              testa_lida_a_cada_chamada)
    passou = 0
    for fn in testes:
        try:
            fn()
            passou += 1
            print("OK", fn.__name__)
        except AssertionError as e:
            print("FALHOU", fn.__name__, "-", e)
    print(f"offline: {passou}/{len(testes)}")
    sys.exit(0 if testes and passou == len(testes) else 1)
