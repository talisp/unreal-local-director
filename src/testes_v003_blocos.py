"""v0.0.3 — testes offline das receitas de movimentos prontos (blocos.py), com os números MEDIDOS no Unreal em 06/10."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
from unreal_macros import blocos as B  # noqa: E402

INFO = {"Start_Walking": {"avanco_cm": 190.54}, "Walking": {"avanco_cm": 150.16}, "Stop_Walking": {"avanco_cm": 152.27},
        "Sit_To_Stand": {"avanco_cm": 46.64}}


@caso("andar escolhe o número de ciclos que chega mais perto e informa o erro")
def t_andar():
    r = B.andar(640, INFO)
    assert r["ciclos"] == 2 and abs(r["avanco_cm"] - 643.1) < 0.2 and r["erro_cm"] == 3.1, r
    assert [p["anim"].split("/")[-1].split("_Anim")[0] for p in r["passos"]] == ["Start_Walking", "Walking", "Walking", "Stop_Walking"]


@caso("andar curto demais não inventa ciclo negativo: começar+parar e erro positivo")
def t_curto():
    r = B.andar(100, INFO)
    assert r["ciclos"] == 0 and r["erro_cm"] > 0 and len(r["passos"]) == 2, r


@caso("compor levantar + andar soma os avanços e mantém a ordem dos passos")
def t_compor():
    c = B.compor(B.levantar(INFO), B.andar(340, INFO))
    assert c["partes"] == ["levantar", "andar"] and c["passos"][0]["anim"].endswith("Sit_To_Stand_Anim")
    assert abs(c["avanco_cm"] - (46.6 + B.andar(340, INFO)["avanco_cm"])) < 0.2, c


@caso("porta: fechada enquanto ninguém passa do plano; abre o necessário para a mão; nunca volta; folha gira certo")
def t_porta():
    # dobradiça em (50, 0); folha fechada vai para -x; abre para +y
    q = [(0, {"RightHand": [0, -20, 100]}), (1, {"RightHand": [0, 10, 100]}), (2, {"Hips": [10, 40, 95]}),
         (3, {"Hips": [10, -50, 95]})]
    r = B.angulos_porta(q, (50, 0), (0, 1), (-1, 0))
    a = dict(r["angulos"])
    assert a[0] == 0 and 0 < a[1] < a[2] and a[3] == a[2], r
    assert r["primeiro_toque"] == {"quadro": 1, "osso": "RightHand"}, r
    (cx, cy), d = B.folha_em((50, 0), (-1, 0), (0, 1), 90)
    assert abs(cx - 50) < 1e-6 and abs(cy - 50) < 1e-6 and abs(d[1] - 1) < 1e-9, (cx, cy, d)


@caso("abrir_porta recusa fora da pré-condição medida (vão estreito, dobradiça trocada) e aceita dentro")
def t_abrir():
    info = dict(INFO, Open_Door_Outwards={"avanco_cm": 212.05})
    assert B.abrir_porta(info, 90, "esquerda")["recusa"] and not B.abrir_porta(info, 90, "esquerda")["passos"]
    assert B.abrir_porta(info, 160, "direita")["recusa"]
    ok = B.abrir_porta(info, 150, "esquerda")
    assert "recusa" not in ok and ok["passos"][0]["anim"].endswith("Open_Door_Outwards_Anim"), ok


if __name__ == "__main__":
    sys.exit(0 if rodar([t_andar, t_curto, t_compor, t_porta, t_abrir], "v003-blocos") else 1)
