"""Cliente mínimo do MCP oficial do Unreal (HTTP JSON-RPC, porta 8001).

Camada atômica: só este módulo conversa com o Unreal. As macros chamam `call` e `script`.
"""
import json
import threading
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8001/mcp"
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


class UnrealError(RuntimeError):
    """Erro devolvido pelo Unreal (ferramenta recusou, schema errado, script falhou)."""


class UnrealPaused(UnrealError):
    """O MCP pausou depois de erros seguidos; espere e tente de novo."""


def _parse(body: str):
    # A resposta pode vir como JSON puro ou como evento SSE ("data: {...}").
    body = body.strip()
    if body.startswith("event:") or body.startswith("data:"):
        datas = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = datas[-1] if datas else "{}"
    return json.loads(body)


class Client:
    def __init__(self, url: str = URL, timeout: float = 45):  # editor saudável responde em < 15 s; diálogo modal trava tudo
        self.url, self.timeout, self.sid, self._id = url, timeout, None, 0
        self.log = []  # (toolset.tool, segundos, ok) para medir custo das macros
        self.prazo = None  # epoch: prazo global da macro em andamento (definido pelo envelope da macro)

    def _post(self, payload: dict):
        if self.prazo and time.time() > self.prazo:
            raise UnrealError("prazo total da macro esgotado; ESTADO DESCONHECIDO: rode inspecionar_cena antes de repetir")
        h = dict(_HEADERS)
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), h)
        try:
            r = urllib.request.urlopen(req, timeout=self.timeout)
        except (TimeoutError, OSError) as e:
            if "timed out" in str(e).lower() or isinstance(e, TimeoutError):
                raise UnrealError(f"o editor não respondeu em {self.timeout:.0f} s: há um diálogo aberto no Unreal "
                                  "(salvar, importar, erro) ou ele está ocupado. Feche o diálogo e repita UMA vez.") from e
            raise
        self.sid = r.headers.get("Mcp-Session-Id") or self.sid
        # O timeout do urllib vale POR LEITURA: os "pings" do MCP chegam pelo mesmo fluxo SSE e o renovam, então uma
        # resposta que nunca vem travava a macro para sempre (06/10: aplicar_clipe preso 30 min). Lê numa thread,
        # para no primeiro evento que seja a resposta e impõe um prazo de RELÓGIO.
        caixa = {}
        esperado = payload.get("id")

        def ler():
            linhas = []
            try:
                for bruta in r:
                    linha = bruta.decode("utf-8", "replace")
                    linhas.append(linha)
                    if linha.startswith("data:"):
                        try:
                            msg = json.loads(linha[5:].strip())
                        except ValueError:
                            continue
                        if isinstance(msg, dict) and ("result" in msg or "error" in msg) and \
                                (esperado is None or msg.get("id") == esperado):  # só a resposta DESTA requisição (Astra)
                            caixa["msg"] = msg
                            return
                caixa["txt"] = "".join(linhas)
            except Exception as e:  # noqa: BLE001 - repassado abaixo
                caixa["erro"] = e

        t = threading.Thread(target=ler, daemon=True)
        t.start()
        t.join(self.timeout)
        if t.is_alive():
            # NÃO usar r.close(): ele espera a trava do buffer, presa na leitura da outra thread = deadlock (06/10,
            # 07:30). Derruba o socket por baixo: a leitura bloqueada volta com erro e a thread (daemon) termina.
            try:
                import socket
                r.fp.raw._sock.shutdown(socket.SHUT_RDWR)
            except Exception:  # noqa: BLE001
                pass
            self.sid = None  # a sessão MCP pode ter ficado inconsistente: reconecta na próxima chamada
            raise UnrealError(f"o editor não devolveu a resposta em {self.timeout:.0f} s (o servidor segue vivo, mas esta "
                              "chamada se perdeu); ESTADO DESCONHECIDO: rode inspecionar_cena; não repita a mesma operação sem conferir o estado")
        r.close()
        if "erro" in caixa:
            raise UnrealError(f"o editor parou de responder no meio da resposta ({caixa['erro']}); ESTADO DESCONHECIDO: "
                              "feche diálogos e rode inspecionar_cena; não repita a mesma operação sem conferir o estado") from caixa["erro"]
        if "msg" in caixa:
            return caixa["msg"]
        txt = caixa.get("txt", "")
        return _parse(txt) if txt.strip() else {}

    def connect(self):
        self._id += 1
        self._post({"jsonrpc": "2.0", "id": self._id, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "unreal-local-director", "version": "0.1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def _meta(self, name: str, arguments: dict):
        if not self.sid:
            self.connect()
        self._id += 1
        resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments}})
        if "error" in resp:
            raise UnrealError(str(resp["error"]))
        res = resp.get("result", {})
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        text = "\n".join(texts)
        if res.get("isError"):
            if "Paused" in text or "rejected the last" in text:
                raise UnrealPaused(text)
            raise UnrealError(text)
        return res.get("structuredContent"), text

    def list_toolsets(self) -> str:
        return self._meta("list_toolsets", {})[1]

    def describe(self, toolset: str) -> str:
        return self._meta("describe_toolset", {"toolset_name": toolset})[1]

    def call(self, toolset: str, tool: str, **arguments):
        """Chama uma ferramenta e devolve o `returnValue` já decodificado."""
        t0 = time.time()
        ok = False
        try:
            structured, text = self._meta("call_tool", {"toolset_name": toolset, "tool_name": tool,
                                                         "arguments": arguments})
            data = structured if structured is not None else (json.loads(text) if text.strip().startswith(("{", "[")) else text)
            if isinstance(data, dict) and "result" in data and isinstance(data["result"], str):
                try:
                    data = json.loads(data["result"])
                except ValueError:
                    pass
            if isinstance(data, dict) and "error" in data:
                raise UnrealError(str(data["error"]))
            if isinstance(data, dict) and "returnValue" in data:
                data = data["returnValue"]
            ok = True
            return data
        finally:
            self.log.append((f"{toolset.split('.')[-1]}.{tool}", round(time.time() - t0, 2), ok))

    def script(self, code: str):
        """Roda um script `def run(): ... return dict` no editor e devolve o dict."""
        out = self.call("editor_toolset.toolsets.programmatic.ProgrammaticToolset", "execute_tool_script", script=code)
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except ValueError:
                pass
        return out


# Nomes completos dos toolsets usados pelas macros (conferidos em 2026-10-05 no UE 5.8.3).
ACTOR = "editor_toolset.toolsets.actor.ActorTools"
OBJECT = "editor_toolset.toolsets.object.ObjectTools"
ASSET = "editor_toolset.toolsets.asset.AssetTools"
SCENE = "editor_toolset.toolsets.scene.SceneTools"
SKMESH = "editor_toolset.toolsets.skeletal_mesh.SkeletalMeshTools"
APP = "EditorToolset.EditorAppToolset"
SEQ = "animation_toolset.toolsets.sequencer.SequencerTools"
