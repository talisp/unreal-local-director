"""Bloco 5: cria o SANDBOX DE TESTE da v0.0.2 (clone do sandbox real; o sandbox do Hermes não é tocado).

Sobreposição por script (sem merge na mão): copia o pacote da v0.0.2 e PRESERVA o que é próprio do sandbox —
guarda.py, zona do estúdio (x=20000), pasta de assets do Sandbox e o gancho da guarda no cliente. A trava aponta para a
trava única de teste da v0.0.2 (um operador só entre v0.0.2 e sandbox de teste). Registra SHAs dos dois lados."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

V002 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX_REAL = os.path.join(os.path.expanduser("~"), "unreal-macros-sandbox")
TESTE = r"<sandbox>-v002"
TRAVA_TESTE = os.path.join(V002, "work", "unreal.trava")


def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


if os.path.exists(TESTE):
    sys.exit(f"{TESTE} já existe: não sobrescrevo (apague à mão se quiser recriar)")
git(os.path.dirname(TESTE), "clone", "-q", "--branch", "master", SANDBOX_REAL, TESTE)
guarda = os.path.join(TESTE, "src", "unreal_macros", "guarda.py")
sha_guarda_antes = sha(guarda)

src_v, src_t = os.path.join(V002, "src", "unreal_macros"), os.path.join(TESTE, "src", "unreal_macros")
for nome in os.listdir(src_v):
    if nome.endswith(".py") and nome != "guarda.py":
        shutil.copy(os.path.join(src_v, nome), os.path.join(src_t, nome))
for nome in ("server.py", "testes_contrato.py", "testes_workflow.py", "paridade.py", "_repro_instavel.py"):
    if os.path.exists(os.path.join(V002, "src", nome)):
        shutil.copy(os.path.join(V002, "src", nome), os.path.join(TESTE, "src", nome))
shutil.copytree(os.path.join(V002, "docs"), os.path.join(TESTE, "docs"), dirs_exist_ok=True)

m = os.path.join(src_t, "macros.py")
t = open(m, encoding="utf-8").read()
t = t.replace("ESTUDIO = (10000.0, -3000.0)", "ESTUDIO = (20000.0, -3000.0)")
t = t.replace('PASTA_ESTUDIO = "/Game/_AnimLab/Estudio"', 'PASTA_ESTUDIO = "/Game/_AnimLab/Sandbox/Estudio"')
t = re.sub(r"^TRAVA = .*$", lambda _m: "TRAVA = " + repr(TRAVA_TESTE) + "  # trava ÚNICA de teste do bloco 5 (= a da v0.0.2)", t,
           count=1, flags=re.M)
assert "ESTUDIO = (20000.0" in t and "Sandbox/Estudio" in t and repr(TRAVA_TESTE) in t
open(m, "w", encoding="utf-8").write(t)
c = os.path.join(src_t, "mcp_client.py")
t = open(c, encoding="utf-8").read()
old = '''    def call(self, toolset: str, tool: str, **arguments):
        """Chama uma ferramenta e devolve o `returnValue` já decodificado."""'''
new = '''    def call(self, toolset: str, tool: str, **arguments):
        """SANDBOX: toda chamada passa pela guarda (guarda.py, não editar) antes de ir ao Unreal."""
        from . import guarda
        guarda.checar(self, toolset, tool, arguments)
        return self._call_cru(toolset, tool, **arguments)

    def _call_cru(self, toolset: str, tool: str, **arguments):
        """Chama uma ferramenta e devolve o `returnValue` já decodificado."""'''
assert t.count(old) == 1
open(c, "w", encoding="utf-8").write(t.replace(old, new))
t = open(os.path.join(TESTE, "src", "testes_contrato.py"), encoding="utf-8").read()
open(os.path.join(TESTE, "src", "testes_contrato.py"), "w", encoding="utf-8").write(t.replace("ZX = 10000.0", "ZX = 20000.0"))
os.makedirs(os.path.join(TESTE, "work"), exist_ok=True)

assert sha(guarda) == sha_guarda_antes, "guarda.py mudou durante a sobreposição!"
git(TESTE, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "add", "-A")
git(TESTE, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm",
    f"sandbox de TESTE da v0.0.2 (base v0.0.2 {git(V002, 'rev-parse', '--short', 'HEAD')}; sandbox real "
    f"{git(SANDBOX_REAL, 'rev-parse', '--short', 'master')})")
reg = {"sandbox_teste": TESTE, "sha_sandbox_teste": git(TESTE, "rev-parse", "--short", "HEAD"),
       "sha_sandbox_real_master": git(SANDBOX_REAL, "rev-parse", "--short", "master"),
       "sha_v002": git(V002, "rev-parse", "--short", "HEAD"), "sha_guarda": sha_guarda_antes, "trava_teste": TRAVA_TESTE}
json.dump(reg, open(os.path.join(V002, "work", "bloco5_ambientes.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps(reg, indent=1))
