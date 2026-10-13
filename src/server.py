"""Entrada compatível do servidor público; implementação em servidor_macros."""
import servidor_macros as _servidor

mcp = _servidor.mcp


def __getattr__(nome: str):
    return getattr(_servidor, nome)


if __name__ == "__main__":
    mcp.run()
