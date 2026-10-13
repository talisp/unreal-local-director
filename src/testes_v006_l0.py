"""Regressões L0: processo local falso, sem inferência ou Unreal."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pipeline_test", ROOT / "docs/skills/test_astra_pipeline.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
A = module.A


class L0(module.Base):
    def execute_fake(self, relative=False, code=0, invalid=False):
        pasta = Path(self.prep())
        answer = self.resposta_boa(extra={"prioridades": [{}]} if invalid else None)
        fake = Path(self.tmp) / "fake.py"
        fake.write_text("import sys\nfrom pathlib import Path\n"
                        "sys.stdin.buffer.read()\n"
                        f"Path(sys.argv[sys.argv.index('-o')+1]).write_text({answer!r}, encoding='utf-8')\n"
                        "print('model: gpt-6-astra', flush=True)\n"
                        f"sys.exit({code})\n", encoding="utf-8")
        arg = os.path.relpath(pasta) if relative else str(pasta)
        result = A.enviar(arg, confirmo_cota=True, login_ok=lambda: True,
                          comando=[sys.executable, str(fake)])
        return pasta, result, answer

    def test_relative(self):
        pasta, result, answer = self.execute_fake(relative=True)
        self.assertEqual(result["codigo"], 0, result)
        self.assertEqual((pasta / "parecer-A.md").read_text(encoding="utf-8"), answer)

    def test_absolute(self):
        _, result, _ = self.execute_fake()
        self.assertEqual(result["codigo"], 0, result)

    def test_failure_preserves_and_resume_never_resends(self):
        pasta, result, answer = self.execute_fake(code=7)
        self.assertEqual(result["estado"], "FALHOU")
        self.assertEqual((pasta / "resposta.md").read_text(encoding="utf-8"), answer)
        before = {p.name: p.read_bytes() for p in pasta.glob("*.md")}
        self.assertFalse(A.retomar(pasta)["reenviar"])
        def forbidden(*a, **kw):
            self.fail("reenvio")
        self.assertEqual(A.enviar(pasta, confirmo_cota=True, popen=forbidden)["codigo"], 3)
        self.assertEqual(before, {p.name: p.read_bytes() for p in pasta.glob("*.md")})
        self.assertTrue((pasta / "log.txt").stat().st_size)

    def test_invalid_priorities_remain_rejected(self):
        pasta, result, _ = self.execute_fake(invalid=True)
        self.assertEqual(result["estado"], "FALHOU")
        self.assertIn("prioridades inválidas", (pasta / "conferencia-A.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
