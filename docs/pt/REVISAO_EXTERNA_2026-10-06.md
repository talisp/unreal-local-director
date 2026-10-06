# Revisão do Astra — correções de 06/10 (pacote autocontido)

**Leia SÓ este arquivo.** Não abra o histórico do Hermes, `state.db`, logs, diário, FALHAS, nem rode comandos. Tudo de que você precisa está aqui. Dados de ontem estão desatualizados e já foram analisados.

## Contexto (o mínimo)
- **Projeto:** camada de macros em Python (servidor MCP `florentia-macros`) sobre o MCP oficial do Unreal 5.8 (HTTP JSON-RPC, porta 8001). Um agente local (Hermes + Qwen) só vê as macros.
- **Medida de pose:** silhueta. Uma cópia do personagem vai para um "estúdio" longe da cena; captura com e sem a cópia; a diferença dá a máscara; uma régua projetada converte pixel em cm. A caixa envolvente do Unreal não acompanha a pose dos clipes, por isso não vale.
- **Estúdio v2** (novo, ainda não revisado por você): sala fechada com paredes e teto cinza escuro unlit, piso cinza fosco iluminado, RectLight própria e PostProcessVolume com exposição manual (sem bloom, DOF, vinheta, motion blur). Liga pelo arquivo `work/estudio_v2.on`. Substituiu a v1 (só piso, céu azul ao fundo), que estourava de branco após mudanças no editor.
- **Bancada noturna:** o Hermes fez 78 `aplicar_clipe` e expôs os problemas abaixo. O diário dele é honesto: 222 de 224 números conferem com os relatórios reais.

## Problemas encontrados → correção aplicada
| # | Problema (evidência) | Correção |
|---|---|---|
| 1 | `aplicar_clipe` preso **30 min** duas vezes (prazo interno de 1500 s nunca disparou). No log do Unreal, a última chamada foi processada, o editor seguiu vivo respondendo pings MCP, mas a resposta não chegou. | `mcp_client._post`: leitura numa thread com `join(timeout)` de relógio. Para no primeiro evento SSE com `result`/`error`. O timeout do urllib vale por leitura, e os pings no mesmo fluxo SSE o renovavam. |
| 2 | Silhueta incompleta: a máscara variou de 1.300 a 13.000 px no mesmo boneco ao longo da noite. Com ~1.300 px (sem pernas) a macro "achava" os pés 20–30 cm acima e **afundava o ator ~25 cm, e aprovava**. Hipótese: Lumen/exposição não convergem com o editor em segundo plano, e o boneco escurece até o nível do piso. | A cópia de medição recebe material **branco unlit** (`M_Estudio_Silhueta`). Gate de qualidade: área < 2.500 cm² ou < 1,0 px/cm → `medido=False` com `motivo`, sem medir nem ajustar. |
| 3 | Ajuste de Z sem limite: "conserta" poses sem chão (queda −28/−63 cm, aterrissagem −37, sentado +16/+19) e aprova. | `AJUSTE_MAX_CM = 10`: acima disso não ajusta, emite aviso e o gate reprova. |
| 4 | "Roleta de quadro": a pose era julgada num único instante. Caminhada, giro e transição para sentar passavam conforme o quadro. | `aplicar_clipe(checar_movimento=True)`: 4 instantes congelados da cópia (vista lateral). Gates `pose_em_todo_clipe` (altura 160–210 em todos) + `pes_plantados` (IoU das pernas ≥ 0,55). O workflow `plateia_em_loop` passa `False` porque já mede deriva própria. |
| 5 | Janela de altura 150–200 aceitava ajoelhado ereto (156,9 cm). | `silhueta_de_pe` 160–210 (210 por braços erguidos: Cheering mede 197,9). |
| 6 | Agente (Qwen) encerrou cedo ("objetivo cumprido") e insistiu depois de "estado parcial". | Skill: regras 10–13 (estado parcial = parar a sessão; timeout = não repetir o clipe; duração manda; gates novos). |
| 7 | Já antes: Play-In-Editor ativo quebrava as macros no meio; `_checar_suportado` recusava atores de teste já girados pela própria macro. | Guarda de PIE no envelope; ignora o roll 0/90 escrito pela macro quando o componente é a raiz. |

**Medida de controle depois das correções:** PC_18 e PC_21 (mezanino, clipe idle do site) medem 178,3 e 177,7 cm, gap −2,1 e +0,2 cm, área ~6.400 cm², 1,47 px/cm. O Hermes tinha medido o PC_18 "+22,6 cm" com a silhueta incompleta.

## Resultados dos testes (06/10, 06:38–06:55, com todas as correções)
- **Contrato: 22/22 OK** (`rodada_v4_1`). Inclui:
  - os 3 positivos de `aplicar_clipe`;
  - "estúdio: silhueta completa";
  - os controles que precisam reprovar e restaurar: Walking, Falling_Idle, Rifle_Crouch_Walk_To_Kneel, clipe sem roll 90, vizinho colado, escotilha (2), família desconhecida, cartão inválido, restauração após reprovação.
  - Observação: Walking reprovou por `pes_no_chao` (no instante medido um pé está no ar), não por `pes_plantados`. O veredito está certo, mas o motivo foi outro, e os gates de 4 instantes nem chegaram a rodar.
- **Workflow:** plateia com 3 bonecos OK (3/3, um precisou de 3 clipes). O controle Walking parou o workflow, como deve.
- **ABERTO:** `executar_cartao` (medir + capturar) **falhou**: `pes_no_chao` no medir.
  - Reproduzi: boneco de teste com Thoughtful_Head_Nod aplicado (aplicar OK, gap +0,9; as 4 amostras deram 1,7). Depois, 3× `medir_personagem` seguidas, sem mudar nada: **−18,1 / +0,2 / +0,2 cm** (altura 178,3 nas três).
  - A primeira medida após aplicar é instável. Suspeita: a primeira captura da cópia nova acontece antes de o editor atualizar pose, material ou iluminação.
  - Pergunta: qual é a correção certa (captura de aquecimento descartada? 2 medidas concordantes? mediana de 3?) sem dobrar o custo de toda macro?
- **Custo:** o contrato fez 1.738 chamadas ao Unreal (era ~860 antes dos 4 instantes e dos controles novos).

## O que eu quero de você (Astra)
Duas partes, com o mesmo peso. **Responda em no máximo ~900 palavras.**

### A. Auditoria das correções (só o diff e o código abaixo)
Para cada correção 1–7: **OK / RISCO / ERRO**, com 1–2 frases. Aponte bug concreto (linha/condição) só se tiver certeza. Atenção especial a:
- **(1)** A thread de leitura pode vazar ou deixar a sessão MCP num estado ruim depois de `r.close()`? Há caso em que a primeira linha `data:` com `result` NÃO é a resposta desta requisição?
- **(2)** Material unlit na cópia invalida a calibração `CALIB_PES_CM = 9` (medida na v1)? O limite de área 2.500 cm² e 1,0 px/cm é razoável?
- **(3)/(4)** Combinação: o ajuste de Z é decidido num instante e `pose_em_todo_clipe` mede 4 instantes **depois** do ajuste. Há buraco?
- **Estúdio v2:** algo frágil (fog, skylight vazando, a luz de 80 lm, a PPV com escala, materiais criados e salvos em `/Game/_AnimLab/Estudio`)?

### B. Propostas de engenharia (o mais importante)
Proponha **até 5 melhorias** concretas, em ordem de valor/custo, cada uma com: o que é, por que, como medir que funcionou. Ideias que já temos (comente, priorize ou substitua):
- ferramenta `registrar_tentativa` (o diário do agente sai do relatório real, sem digitar números; a rodada 1 gastou 14 M tokens de entrada, boa parte reescrevendo números);
- medir a pose por **osso** (ferramenta Python dentro do editor, que exige reiniciar) em vez de silhueta;
- **estabilidade de captura**: esperar o Lumen convergir (N capturas até a diferença cair) ou viewport em modo Unlit só para a medida;
- macros que faltam: andar por trajetória (com gate de colisão), sentar e levantar;
- vigia do agente: sessão nova em vez de retomar (o app bloqueia com `SESSION_NOT_OWNED`);
- projeto aberto no GitHub com essas macros.

### Formato da resposta
1. Tabela A (correção → veredito → 1 frase).
2. Lista B (até 5 itens).
3. "Se fosse só uma coisa a fazer hoje": 1 parágrafo.

Não peça mais dados. Se algo não puder ser decidido com este pacote, diga "indecidível com o pacote" e siga.

## Anexo 1 — diff das correções (antes = checkpoint 00:20 de 06/10)
```diff
--- antes/mcp_client.py
+++ depois/mcp_client.py
@@ -3,6 +3,7 @@
 Camada atômica: só este módulo conversa com o Unreal. As macros chamam `call` e `script`.
 """
 import json
+import threading
 import time
 import urllib.error
 import urllib.request
@@ -48,13 +49,47 @@
                 raise UnrealError(f"o editor não respondeu em {self.timeout:.0f} s: há um diálogo aberto no Unreal "
                                   "(salvar, importar, erro) ou ele está ocupado. Feche o diálogo e repita UMA vez.") from e
             raise
-        try:
-            with r:
-                self.sid = r.headers.get("Mcp-Session-Id") or self.sid
-                txt = r.read().decode("utf-8", "replace")
-        except (TimeoutError, OSError) as e:
-            raise UnrealError(f"o editor parou de responder no meio da resposta ({e}); ESTADO DESCONHECIDO: "
-                              "feche diálogos, rode inspecionar_cena e só então repita") from e
+        self.sid = r.headers.get("Mcp-Session-Id") or self.sid
+        # O timeout do urllib vale POR LEITURA: os "pings" do MCP chegam pelo mesmo fluxo SSE e o renovam, então uma
+        # resposta que nunca vem travava a macro para sempre (06/10: aplicar_clipe preso 30 min). Lê numa thread,
+        # para no primeiro evento que seja a resposta e impõe um prazo de RELÓGIO.
+        caixa = {}
+
+        def ler():
+            linhas = []
+            try:
+                for bruta in r:
+                    linha = bruta.decode("utf-8", "replace")
+                    linhas.append(linha)
+                    if linha.startswith("data:"):
+                        try:
+                            msg = json.loads(linha[5:].strip())
+                        except ValueError:
+                            continue
+                        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
+                            caixa["msg"] = msg
+                            return
+                caixa["txt"] = "".join(linhas)
+            except Exception as e:  # noqa: BLE001 - repassado abaixo
+                caixa["erro"] = e
+
+        t = threading.Thread(target=ler, daemon=True)
+        t.start()
+        t.join(self.timeout)
+        if t.is_alive():
+            try:
+                r.close()
+            except Exception:  # noqa: BLE001
+                pass
+            raise UnrealError(f"o editor não devolveu a resposta em {self.timeout:.0f} s (o servidor segue vivo, mas esta "
+                              "chamada se perdeu); ESTADO DESCONHECIDO: rode inspecionar_cena e só então repita")
+        r.close()
+        if "erro" in caixa:
+            raise UnrealError(f"o editor parou de responder no meio da resposta ({caixa['erro']}); ESTADO DESCONHECIDO: "
+                              "feche diálogos, rode inspecionar_cena e só então repita") from caixa["erro"]
+        if "msg" in caixa:
+            return caixa["msg"]
+        txt = caixa.get("txt", "")
         return _parse(txt) if txt.strip() else {}
 
     def connect(self):
--- antes/macros.py
+++ depois/macros.py
@@ -365,6 +365,12 @@
     ordem = np.argsort(ry)                                     # interpolar altura a partir do pixel y
     altura_de = lambda py: float(np.interp(py, ry[ordem], zs[ordem]))
     # Calibração (05/10, work/calibracao_silhueta.json): com esta câmera, pés no piso medem -9 cm (perspectiva).
+    area = float(mask.sum()) / (px_por_cm ** 2)
+    out.update({"px_por_cm": round(float(px_por_cm), 2), "area_cm2": round(area)})
+    if area < AREA_MIN_CM2 or px_por_cm < 1.0:  # máscara incompleta ou imagem pequena demais: não mede (06/10)
+        out["medido"] = False
+        out["motivo"] = f"silhueta incompleta (área {area:.0f} cm2, {px_por_cm:.2f} px/cm)"
+        return out
     out.update({"medido": True, "altura_cm": round(altura_de(top), 1), "gap_pes_cm": round(altura_de(bot) + CALIB_PES_CM, 1),
                 "largura_cm": round(float((dir_ - esq) / px_por_cm), 1),
                 "centro_desvio_cm": round(float(((esq + dir_) / 2 - rx.mean()) / px_por_cm), 1)})
@@ -444,6 +450,22 @@
     return a
 
 
+COR_SILHUETA = 1.0      # emissivo da cópia de medição: branco SEM iluminação (contraste não depende do Lumen)
+AREA_MIN_CM2 = 2500.0   # silhueta de um corpo inteiro tem ~4000-7000 cm2; abaixo disso a máscara está incompleta
+AJUSTE_MAX_CM = 10.0    # ajuste de Z maior que isto = pose sem chão / sentada / medida ruim: reprova, não "conserta"
+
+
+def _pintar_copia(copia: dict):
+    """Na v2, a cópia de medição recebe material branco sem iluminação (06/10: com o Unreal em segundo plano o Lumen
+    não convergia, o boneco escurecia, a silhueta perdia as pernas e a macro afundava o ator ~25 cm)."""
+    v2 = ESTUDIO_V2 if ESTUDIO_V2 is not None else os.path.exists(os.path.join(RAIZ_WORK, "estudio_v2.on"))
+    if not v2:
+        return
+    m = _material_estudio("M_Estudio_Silhueta", COR_SILHUETA, sem_luz=True)
+    cliente().call(OBJECT, "set_properties", instance={"refPath": copia["refPath"] + COMP},
+                   values=json.dumps({"overrideMaterials": [{"refPath": m}, {"refPath": m}]}))
+
+
 def _estudio_piso():
     """Monta a sala técnica do estúdio (uma vez por processo) e devolve o piso (topo em z=0)."""
     if _estudio["piso"]:
@@ -518,6 +540,7 @@
             "animationMode": "AnimationSingleNode", "bUseRefPoseOnInitAnim": False,
             "relativeRotation": {"pitch": rot["pitch"], "yaw": rot["yaw"] + xf["rotation"]["yaw"], "roll": rot["roll"]},
             "animationData": dados}))
+        _pintar_copia(copia)
         # O editor não toca o loop em tempo real de forma confiável: congela a cópia em instantes do clipe.
         anim_ref = _ref(dados.get("animToPlay"))
         duracao = duracao_clipe(anim_ref)
@@ -565,6 +588,7 @@
             "animationMode": p.get("animationMode") or "AnimationSingleNode", "bUseRefPoseOnInitAnim": False,
             "relativeRotation": {"pitch": rot["pitch"], "yaw": rot["yaw"] + xf["rotation"]["yaw"], "roll": rot["roll"]},
             "animationData": p["animationData"]}))
+        _pintar_copia(copia)
         time.sleep(0.6)
         s = _silhueta(copia)
     finally:
@@ -681,10 +705,13 @@
 
 @macro
 def aplicar_clipe(rel, ator: str, clipe: str, loop: bool = True, tempo: float = 0.0,
-                  corrigir_altura: bool = True, tolerancia_cm: float = 4.0, manter_se_falhar: bool = False):
+                  corrigir_altura: bool = True, tolerancia_cm: float = 4.0, manter_se_falhar: bool = False,
+                  checar_movimento: bool = True):
     """Aplica um clipe num personagem DE PÉ sem mover o ator. Corrige a orientação dos clipes da biblioteca (roll 90,
     FALHA-20), mede a pose pela silhueta de uma cópia no estúdio e, se os pés não estiverem no piso, ajusta só o Z do
-    componente e MEDE DE NOVO. Se qualquer gate reprovar ou der erro, restaura o estado anterior e confere."""
+    componente e MEDE DE NOVO. checar_movimento: mede também 4 instantes do clipe (de lado) e exige pose de pé em
+    todos e pernas plantadas (06/10: um instante só deixava passar caminhada, queda e transição para sentar).
+    Se qualquer gate reprovar ou der erro, restaura o estado anterior e confere."""
     a = resolver_ator(ator)
     _checar_suportado(a)
     anim = clipe if clipe.startswith("/Game/") else _achar_anim(clipe)
@@ -699,6 +726,11 @@
     rel["medidas"]["familia"] = fam
     try:
         _aplicar_e_medir(rel, a, anim, antes, xf_antes, rot, loop, tempo, corrigir_altura, tolerancia_cm)
+        if checar_movimento and all(g["resultado"] == "PASS" for g in rel["medidas"]["gates"]):
+            amostras = _amostrar_estudio(a, vista="lateral", n=4)
+            rel["medidas"]["amostras"] = [{k: s.get(k) for k in ("t", "medido", "altura_cm", "gap_pes_cm", "motivo")}
+                                          for s in amostras]
+            rel["medidas"]["gates"] += [gates.pose_em_todo_clipe(amostras), gates.pes_plantados(amostras)]
     except Exception:
         rel["medidas"]["restaurado"] = _restaurar(a, antes)
         raise
@@ -749,8 +781,13 @@
     # biblioteca; no estúdio ninguém fica na frente e o original não é tocado). Pés no piso real = conta.
     s = _silhueta_estudio(a)
     ajuste = 0.0
-    if corrigir_altura and s.get("medido") and s.get("gap_local_cm") is not None \
-            and abs(s["gap_local_cm"]) > tolerancia_cm and not s["deitado"]:
+    precisa = corrigir_altura and s.get("medido") and s.get("gap_local_cm") is not None \
+        and abs(s["gap_local_cm"]) > tolerancia_cm and not s["deitado"]
+    if precisa and abs(s["gap_local_cm"]) > AJUSTE_MAX_CM:  # FALHA-25: não "conserta" pose sem chão afundando o ator
+        rel["avisos"].append(f"pés a {s['gap_local_cm']:+.1f} cm do piso: acima do ajuste permitido ({AJUSTE_MAX_CM:.0f} cm); "
+                             "pose sem chão, sentada ou medida ruim")
+        precisa = False
+    if precisa:
         loc = dict(antes["relativeLocation"])
         ajuste = -s["gap_local_cm"]
         loc["z"] = round(loc["z"] + ajuste, 2)
--- antes/gates.py
+++ depois/gates.py
@@ -42,7 +42,7 @@
     return g("deriva_xy", d <= tol, round(d, 1), f"<= {tol} cm")
 
 
-def silhueta_de_pe(s: dict, altura=(150, 200)) -> dict:
+def silhueta_de_pe(s: dict, altura=(160, 210)) -> dict:  # 06/10: 150 aceitava ajoelhado ereto (156,9)
     """Pose de pé medida pela silhueta na imagem (altura estimada em cm e não deitado)."""
     if not s.get("medido"):
         return g("silhueta_de_pe", None, s.get("pixels"), "silhueta mensurável")
@@ -67,3 +67,13 @@
         ious.append(float(np.logical_and(base, m).sum() / uni) if uni else 1.0)
     v = round(min(ious), 3)
     return g("pes_plantados", v >= iou_min, v, f"IoU pernas >= {iou_min}")
+
+
+def pose_em_todo_clipe(amostras: list, altura=(160, 210)) -> dict:
+    """A pose de pé vale no clipe INTEIRO (4 instantes), não num quadro sorteado: queda, ajoelhar ou sentar no meio
+    do clipe reprovam (06/10, bancada do Hermes: 'roleta de quadro')."""
+    if any(not s.get("medido") for s in amostras):
+        return g("pose_em_todo_clipe", None, [s.get("motivo") for s in amostras], "todos os instantes mensuráveis")
+    alt = [s["altura_cm"] for s in amostras]
+    ok = all(altura[0] <= h <= altura[1] for h in alt) and not any(s["deitado"] for s in amostras)
+    return g("pose_em_todo_clipe", ok, alt, f"altura {altura[0]}-{altura[1]} cm em todos os instantes")
--- antes/workflows.py
+++ depois/workflows.py
@@ -42,7 +42,7 @@
             if not ri["ok"]:
                 tentativas.append({"clipe": clipe, "falha": ri["bloqueio"]})
                 continue
-            ra = M.aplicar_clipe(ator, clipe, loop=True)  # se reprovar, ela mesma restaura e confere
+            ra = M.aplicar_clipe(ator, clipe, loop=True, checar_movimento=False)  # o workflow mede deriva abaixo
             gs = list(ra["medidas"].get("gates", []))
             try:
                 if ra["ok"]:
--- antes/testes_contrato.py
+++ depois/testes_contrato.py
@@ -103,6 +103,19 @@
     time.sleep(0.3)
     rm = M.medir_personagem("TESTE_BONECO_A")
     registra("medir_personagem: de pé, pés no chão, sem vizinho colado", "PASS", rm, rm["ok"])
+    # Estúdio v2 (06/10): a silhueta tem de sair COMPLETA (corpo inteiro ~4000-7000 cm2), com resolução suficiente.
+    sv = rm["medidas"].get("silhueta", {})
+    registra("estúdio: silhueta completa (área >= 4000 cm2, >= 1.5 px/cm)", "PASS", rm,
+             (sv.get("area_cm2") or 0) >= 4000 and (sv.get("px_por_cm") or 0) >= 1.0)
+
+    # Controles negativos dos gates de 06/10 (bancada do Hermes): cada um tem de REPROVAR e restaurar.
+    for clipe, porque in (("Walking", "anda no lugar (pes_plantados)"),
+                          ("Falling_Idle", "pose sem chão (ajuste > 10 cm)"),
+                          ("Rifle_Crouch_Walk_To_Kneel", "termina ajoelhado (pose_em_todo_clipe)")):
+        M.importar_clipe(clipe)
+        rx = M.aplicar_clipe("TESTE_BONECO_A", clipe, loop=True)
+        registra(f"CONTROLE: {clipe} reprova: {porque}", "FAIL", rx,
+                 rx["ok"] is False and rx["medidas"].get("restaurado") is True)
 
     rc = M.capturar_evidencia("TESTE_BONECO_A", vista="frontal", nome="TESTE contrato")
     registra("capturar_evidencia gera PNG enquadrado", "PASS", rc, rc["ok"] and rc["evidencias"] and os.path.exists(rc["evidencias"][0]))
```

## Anexo 2 — código do estúdio v2 (macros.py, já existia antes do diff)
```python
# Estúdio v2 (06/10): sala técnica fechada. O céu azul e as nuvens tinham a cor do mannequin (ciano) e atrapalhavam
# a silhueta e a visão. Paredes e teto: cinza escuro SEM iluminação (emitem a própria cor: tom fixo em qualquer
# vista, sem ficar preto). Piso: cinza médio fosco e iluminado (mostra a sombra de contato). Luz branca própria e
# exposição manual num volume de pós-processo (sem bloom, DOF, vinheta, motion blur, lens flare).
ESTUDIO_V2 = None  # None = decide pelo arquivo work/estudio_v2.on (liga sem reiniciar o Hermes); True/False força
PASTA_ESTUDIO = "/Game/_AnimLab/Estudio"
MAT = "editor_toolset.toolsets.material.MaterialTools"
COR_FUNDO = 0.035   # emissivo linear das paredes/teto (cinza escuro na imagem)
COR_PISO = 0.18     # albedo linear do piso (cinza médio)
MEIO, ALTO = 600.0, 700.0  # meia largura interna e altura da sala (cm)
EXPOSICAO = {"bOverride_AutoExposureMethod": True, "autoExposureMethod": "AEM_Manual",
             "bOverride_AutoExposureBias": True, "autoExposureBias": 0.0,
             "bOverride_AutoExposureApplyPhysicalCameraExposure": True, "autoExposureApplyPhysicalCameraExposure": False,
             "bOverride_BloomIntensity": True, "bloomIntensity": 0.0,
             "bOverride_DepthOfFieldEnabled": True, "depthOfFieldEnabled": False,
             "bOverride_MotionBlurAmount": True, "motionBlurAmount": 0.0,
             "bOverride_VignetteIntensity": True, "vignetteIntensity": 0.0,
             "bOverride_LensFlareIntensity": True, "lensFlareIntensity": 0.0,
             "bOverride_SceneFringeIntensity": True, "sceneFringeIntensity": 0.0}
LUZ_LUMENS = 80.0  # medido 06/10: 100 lm -> piso 153/255; 0 lm -> 62 (vazamento)


def _material_estudio(nome: str, cor: float, sem_luz: bool) -> str:
    """Cria (uma vez) um material cinza constante em /Game/_AnimLab/Estudio e o salva. Devolve o refPath."""
    ref = f"{PASTA_ESTUDIO}/{nome}.{nome}"
    if any(_ref(x).startswith(f"{PASTA_ESTUDIO}/{nome}") for x in cliente().call(ASSET, "find_assets", folder_path=PASTA_ESTUDIO, name=nome) or []):
        return ref
    cliente().call(MAT, "create_material", folder_path=PASTA_ESTUDIO, asset_name=nome)
    m = {"refPath": ref}

    def const(classe, valor, saida, y):
        e = cliente().call(MAT, "add_expression", material_or_function=m, expression_class={"refPath": f"/Script/Engine.{classe}"}, x=-300, y=y)
        e = e if isinstance(e, dict) else {"refPath": e}
        cliente().call(OBJECT, "set_properties", instance=e, values=json.dumps({"R": valor} if classe.endswith("Constant") else
                                                                              {"Constant": {"R": valor, "G": valor, "B": valor, "A": 1}}))
        cliente().call(MAT, "connect_to_output", expression=e, output_name="", material_property=saida)

    if sem_luz:
        cliente().call(OBJECT, "set_properties", instance=m, values=json.dumps({"ShadingModel": "MSM_Unlit"}))
        const("MaterialExpressionConstant3Vector", cor, "MP_EmissiveColor", 0)
    else:
        const("MaterialExpressionConstant3Vector", cor, "MP_BaseColor", 0)
        const("MaterialExpressionConstant", 1.0, "MP_Roughness", 150)
        const("MaterialExpressionConstant", 0.0, "MP_Specular", 300)
    cliente().call(MAT, "recompile", material_or_function=m)
    cliente().call(ASSET, "save_assets", asset_paths=[f"{PASTA_ESTUDIO}/{nome}"])
    return ref


def _spawn_estudio(nome: str, xform: dict, asset: str = "", classe: str = "") -> dict:
    if asset:
        a = cliente().call(SCENE, "add_to_scene_from_asset", asset_path=asset, name=f"TESTE_ESTUDIO_{RUN}_{nome}", xform=xform)
    else:
        a = cliente().call(SCENE, "add_to_scene_from_class", actor_type={"refPath": classe}, name=f"TESTE_ESTUDIO_{RUN}_{nome}", xform=xform)
    a = a if isinstance(a, dict) else {"refPath": a}
    cliente().call(ACTOR, "set_label", actor=a, label=f"TESTE_ESTUDIO_{RUN}_{nome}")
    _estudio.setdefault("atores", []).append(a)
    return a


COR_SILHUETA = 1.0      # emissivo da cópia de medição: branco SEM iluminação (contraste não depende do Lumen)
AREA_MIN_CM2 = 2500.0   # silhueta de um corpo inteiro tem ~4000-7000 cm2; abaixo disso a máscara está incompleta
AJUSTE_MAX_CM = 10.0    # ajuste de Z maior que isto = pose sem chão / sentada / medida ruim: reprova, não "conserta"


def _pintar_copia(copia: dict):
    """Na v2, a cópia de medição recebe material branco sem iluminação (06/10: com o Unreal em segundo plano o Lumen
    não convergia, o boneco escurecia, a silhueta perdia as pernas e a macro afundava o ator ~25 cm)."""
    v2 = ESTUDIO_V2 if ESTUDIO_V2 is not None else os.path.exists(os.path.join(RAIZ_WORK, "estudio_v2.on"))
    if not v2:
        return
    m = _material_estudio("M_Estudio_Silhueta", COR_SILHUETA, sem_luz=True)
    cliente().call(OBJECT, "set_properties", instance={"refPath": copia["refPath"] + COMP},
                   values=json.dumps({"overrideMaterials": [{"refPath": m}, {"refPath": m}]}))


def _estudio_piso():
    """Monta a sala técnica do estúdio (uma vez por processo) e devolve o piso (topo em z=0)."""
    if _estudio["piso"]:
        return _estudio["piso"]
    v2 = ESTUDIO_V2 if ESTUDIO_V2 is not None else os.path.exists(os.path.join(RAIZ_WORK, "estudio_v2.on"))
    if not v2:  # v1: só o piso (céu ao fundo)
        p = cliente().call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube",
                           name=f"TESTE_ESTUDIO_{RUN}_PISO", xform=_xf(ESTUDIO[0], ESTUDIO[1], -50, s=(12, 12, 1)))
        p = p if isinstance(p, dict) else {"refPath": p}
        cliente().call(ACTOR, "set_label", actor=p, label=f"TESTE_ESTUDIO_{RUN}_PISO")
        _estudio["piso"] = p
        return p
    fundo = _material_estudio("M_Estudio_Fundo", COR_FUNDO, sem_luz=True)
    chao = _material_estudio("M_Estudio_Piso", COR_PISO, sem_luz=False)
    X, Y = ESTUDIO
    L = 2 * MEIO / 100 + 2  # escala do cubo de 1 m que cobre a sala com sobra
    cubo = "/Engine/BasicShapes/Cube.Cube"
    pecas = {"PISO": (_xf(X, Y, -50, s=(L, L, 1)), chao),
             "TETO": (_xf(X, Y, ALTO + 50, s=(L, L, 1)), fundo),
             "PAREDE_XP": (_xf(X + MEIO + 50, Y, ALTO / 2, s=(1, L, ALTO / 100 + 2)), fundo),
             "PAREDE_XN": (_xf(X - MEIO - 50, Y, ALTO / 2, s=(1, L, ALTO / 100 + 2)), fundo),
             "PAREDE_YP": (_xf(X, Y + MEIO + 50, ALTO / 2, s=(L, 1, ALTO / 100 + 2)), fundo),
             "PAREDE_YN": (_xf(X, Y - MEIO - 50, ALTO / 2, s=(L, 1, ALTO / 100 + 2)), fundo)}
    for nome, (xf, mat) in pecas.items():
        a = _spawn_estudio(nome, xf, asset=cubo)
        comp = cliente().call(ACTOR, "get_root_component", actor=a)
        comp = comp if isinstance(comp, dict) else {"refPath": comp}
        cliente().call(OBJECT, "set_properties", instance=comp, values=json.dumps({"overrideMaterials": [{"refPath": mat}]}))
        if nome == "PISO":
            _estudio["piso"] = a
    luz = _spawn_estudio("LUZ", _xf(X, Y, ALTO - 20, pitch=-90), classe="/Script/Engine.RectLight")
    lc = cliente().call(ACTOR, "get_root_component", actor=luz)
    cliente().call(OBJECT, "set_properties", instance=lc if isinstance(lc, dict) else {"refPath": lc}, values=json.dumps({
        "intensityUnits": "Lumens", "Intensity": LUZ_LUMENS, "SourceWidth": 500, "sourceHeight": 500,
        "AttenuationRadius": 2500, "barnDoorAngle": 88, "lightColor": {"r": 1, "g": 1, "b": 1, "a": 1}, "castShadows": True}))
    ppv = _spawn_estudio("POS", _xf(X, Y, ALTO / 2, s=(MEIO / 100, MEIO / 100, ALTO / 200)), classe="/Script/Engine.PostProcessVolume")
    cliente().call(OBJECT, "set_properties", instance=ppv, values=json.dumps({"bUnbound": False, "priority": 100, "settings": EXPOSICAO}))
    cliente().call(APP, "SelectActors", actors=[])  # o contorno de seleção (ciano) sujava as capturas
    time.sleep(1.0)
    return _estudio["piso"]


```
