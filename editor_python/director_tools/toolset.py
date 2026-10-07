"""DirectorTools: toolset Python DENTRO do editor (API `unreal` completa), exposto pelo MCP oficial na porta 8001.

Existe porque o `execute_tool_script` da Epic roda num sandbox sem `unreal` (field notes do UE 5.8), e as peças do
VERA precisam da API completa. Formato oficial da Epic: `unreal.ToolsetDefinition` + `toolset_registry.tool_call`
(ver Engine/Plugins/Experimental/ToolsetRegistry/.../tests/demo_toolset.py).

Toda ferramenta devolve uma string JSON compacta: {"ok": bool, ...} ou {"ok": false, "erro": "<codigo>", ...}.
Nenhuma salva asset nem level. Atores criados aqui se chamam TESTE_DIRECTOR_* (a limpeza do Director os acha).

Captura isolada e avaliação de pose fora do viewport adaptadas de VERA (c) 2026 EazyLabs / maVERAick, licença MIT,
commit 8eeb1e7, arquivo vera/agent/tools/_capture_scripts.py. Ver THIRD_PARTY_NOTICES.md.
"""
import json
import math
import os
import sys
import time
import types

import toolset_registry
import unreal

ESTADO = "director_tools_estado"  # estado de sessão em sys.modules: a restauração é idempotente (padrão do VERA)
ROTULO_RIG = "TESTE_DIRECTOR_CaptureRig"
FLAGS_FUNDO = ("Atmosphere", "Cloud", "Fog", "VolumetricFog")


def _j(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _atores():
    return list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())


def _achar(rotulo: str):
    """Só casamento EXATO de rótulo (o VERA aceita parcial; aqui isso poderia mexer no ator errado)."""
    todos = _atores()
    for a in todos:
        if a.get_actor_label() == rotulo:
            return a, []
    baixo = rotulo.lower()
    parecidos = sorted({a.get_actor_label() for a in todos if baixo[:4] in a.get_actor_label().lower()})[:8]
    return None, parecidos


def _skel(ator):
    comps = ator.get_components_by_class(unreal.SkeletalMeshComponent)
    return comps[0] if comps else None


def _estado():
    st = sys.modules.get(ESTADO)
    if st is None:
        st = types.ModuleType(ESTADO)
        st.rig = None
        st.rt = None
        st.alvo = None
        st.tick_anterior = {}  # caminho do componente -> opção anterior
        sys.modules[ESTADO] = st
    return st


def _osso_no_quadro(anim, osso: str, quadro: int):
    """Posição do osso no espaço do componente no quadro (AnimPose; WORLD aqui = espaço do componente da pose)."""
    pose = unreal.AnimPoseExtensions.get_anim_pose_at_frame(anim, quadro, unreal.AnimPoseEvaluationOptions())
    return unreal.AnimPoseExtensions.get_bone_pose(pose, osso, unreal.AnimPoseSpaces.WORLD).translation


def _v(vec) -> list:
    return [round(vec.x, 2), round(vec.y, 2), round(vec.z, 2)]


@unreal.uclass()
class DirectorTools(unreal.ToolsetDefinition):
    """Ferramentas do Director que precisam da API Python completa do editor: inventário sem limite, posição de
    ossos no mundo e captura isolada de um ator (só ele aparece na imagem), sempre com restauração."""

    @toolset_registry.tool_call
    @staticmethod
    def ping() -> str:
        """Prova que o Python completo do editor está acessível.

        Returns:
            JSON com versão do motor, mundo do editor e número de atores.
        """
        mundo = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        return _j(ok=True, motor=unreal.SystemLibrary.get_engine_version(), python=sys.version.split()[0],
                  mundo=mundo.get_name() if mundo else None, atores=len(_atores()))

    @toolset_registry.tool_call
    @staticmethod
    def reload_toolset() -> str:
        """Recarrega o DirectorTools do disco (só este pacote) e registra de novo. Para aplicar correções sem
        reiniciar o editor. O nome no catálogo pode mudar (sufixo _0x...): consultar list_toolsets depois.

        Returns:
            JSON com o resultado do novo registro.
        """
        # desregistrar ANTES: a classe recarregada ganha o mesmo nome e o registro recusaria, deixando a velha inválida
        atual = sys.modules.get("director_tools")
        if atual is not None and hasattr(atual, "_registration"):
            atual._registration.unregister()
        for m in [m for m in sys.modules if m.startswith("director_tools")]:
            del sys.modules[m]
        import director_tools  # noqa: PLC0415 — reimporta do UE_PYTHONPATH
        return _j(ok=bool(director_tools._registration.register()))

    @toolset_registry.tool_call
    @staticmethod
    def list_actors(class_name: str = "", label_prefix: str = "") -> str:
        """Inventário COMPLETO do level carregado (o find_actors do MCP corta em 20 sem avisar).

        Args:
            class_name: filtra pelo nome da classe (ex. SkeletalMeshActor); vazio = todas.
            label_prefix: filtra pelo começo do rótulo (ex. TESTE_); vazio = todos.

        Returns:
            JSON com total e lista de {rotulo, classe, caminho, xyz}.
        """
        itens = []
        for a in _atores():
            classe = a.get_class().get_name()
            rot = a.get_actor_label()
            if (class_name and classe != class_name) or (label_prefix and not rot.startswith(label_prefix)):
                continue
            itens.append({"rotulo": rot, "classe": classe, "caminho": a.get_path_name(), "xyz": _v(a.get_actor_location())})
        return _j(ok=True, total=len(itens), atores=itens)

    @toolset_registry.tool_call
    @staticmethod
    def set_pose_eval(actor_label: str, on: bool) -> str:
        """Liga/desliga a avaliação da pose fora do viewport (ALWAYS_TICK_POSE_AND_REFRESH_BONES). Sem isso o
        personagem só atualiza ossos quando aparece na tela. Desligar restaura a opção anterior.

        Args:
            actor_label: rótulo exato do ator.
            on: true liga; false restaura a opção que havia antes.

        Returns:
            JSON com a opção anterior e a atual.
        """
        ator, parecidos = _achar(actor_label)
        if ator is None:
            return _j(ok=False, erro="ator_nao_encontrado", candidatos=parecidos)
        comp = _skel(ator)
        if comp is None:
            return _j(ok=False, erro="sem_esqueleto")
        st = _estado()
        chave = comp.get_path_name()
        atual = comp.get_editor_property("visibility_based_anim_tick_option")
        if on:
            st.tick_anterior.setdefault(chave, atual)
            comp.set_editor_property("visibility_based_anim_tick_option",
                                     unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
        elif chave in st.tick_anterior:
            comp.set_editor_property("visibility_based_anim_tick_option", st.tick_anterior.pop(chave))
        return _j(ok=True, anterior=str(atual), atual=str(comp.get_editor_property("visibility_based_anim_tick_option")))

    @toolset_registry.tool_call
    @staticmethod
    def bone_world_positions(actor_label: str, bones: str = "") -> str:
        """Posição atual dos ossos no mundo, em cm. Para pose num instante: ajustar o tempo numa chamada e ler em
        OUTRA (na mesma chamada o motor ainda não reavaliou a pose).

        Args:
            actor_label: rótulo exato do ator.
            bones: nomes separados por vírgula; vazio = todos os ossos.

        Returns:
            JSON {osso: [x, y, z]} e os nomes pedidos que não existem.
        """
        ator, parecidos = _achar(actor_label)
        if ator is None:
            return _j(ok=False, erro="ator_nao_encontrado", candidatos=parecidos)
        comp = _skel(ator)
        if comp is None:
            return _j(ok=False, erro="sem_esqueleto")
        nomes = [b.strip() for b in bones.split(",") if b.strip()] or [str(n) for n in comp.get_all_socket_names()]
        pos, faltam = {}, []
        for n in nomes:
            if comp.does_socket_exist(n):
                pos[n] = _v(comp.get_socket_location(n))
            else:
                faltam.append(n)
        return _j(ok=True, ossos=pos, inexistentes=faltam,
                  tick=str(comp.get_editor_property("visibility_based_anim_tick_option")))

    @toolset_registry.tool_call
    @staticmethod
    def bone_position_in_clip(animation_path: str, bone_name: str, frame: int) -> str:
        """Posição do osso no ESPAÇO DO CORPO (componente) num quadro do clipe, sem cena. Por índice de quadro
        (0..quadros-1): por tempo o motor dispara um ensure perto do fim (bValidTime) e devolve pose inválida; e a
        API antiga devolvia a posição relativa ao osso pai (mão = constante), corrigido em 06/10.

        Args:
            animation_path: caminho do AnimSequence (ex. /Game/Pasta/Clipe.Clipe).
            bone_name: nome do osso.
            frame: índice do quadro (0 = início; quadros-1 = último).

        Returns:
            JSON com a posição em cm e o número de quadros.
        """
        anim = unreal.load_asset(animation_path)
        if not isinstance(anim, unreal.AnimSequence):
            return _j(ok=False, erro="clipe_nao_encontrado")
        quadros = int(unreal.AnimationLibrary.get_num_frames(anim))
        if frame < 0 or frame > quadros - 1:
            return _j(ok=False, erro="quadro_fora_do_clipe", quadros=quadros)
        return _j(ok=True, xyz=_v(_osso_no_quadro(anim, bone_name, frame)), quadros=quadros)

    @toolset_registry.tool_call
    @staticmethod
    def seq_build(actor_label: str, steps_json: str, dir_x: float, dir_y: float, fps: int) -> str:
        """Monta uma Level Sequence NOVA (nome único SEQ_TESTE_*, nunca sobrescreve, nunca salva) em
        /Game/_AnimLab/Experimentos com uma receita de passos prontos encadeados no ator. Clipes Mixamo andam pelo
        quadril (não pela raiz): a cada troca o ator é reposicionado pelo avanço do clipe anterior, na direção
        corrente; um passo pode girar a direção antes de começar.

        Args:
            actor_label: rótulo exato do ator (boneco TESTE_).
            steps_json: lista JSON de passos {"anim": caminho do AnimSequence, "turn_deg": giro antes do passo (opcional)}.
            dir_x: direção inicial de caminhada no mundo (x), normalizada com dir_y.
            dir_y: direção inicial de caminhada no mundo (y).
            fps: quadros por segundo da sequência.

        Returns:
            JSON com o caminho da sequência, faixas por passo (quadros, avanço, posição) e o ponto final previsto.
        """
        ator, parecidos = _achar(actor_label)
        if ator is None:
            return _j(ok=False, erro="ator_nao_encontrado", candidatos=parecidos)
        passos = json.loads(steps_json)
        anims = [unreal.load_asset(p.get("anim", "")) for p in passos]
        if not anims or any(not isinstance(a, unreal.AnimSequence) for a in anims):
            return _j(ok=False, erro="clipe_nao_encontrado")
        nome = f"SEQ_TESTE_{int(time.time() * 1000) % 10**9}"  # único: criar por cima sobrescreveria (field notes)
        seq = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            nome, "/Game/_AnimLab/Experimentos", unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
        try:
            return DirectorTools._montar(seq, ator, passos, anims, dir_x, dir_y, fps)
        except Exception as e:  # noqa: BLE001 — falhou no meio: não deixa sequência de teste órfã
            unreal.EditorAssetLibrary.delete_asset(seq.get_path_name().split(".")[0])
            return _j(ok=False, erro="falha_ao_montar", detalhe=str(e)[:300])

    @toolset_registry.tool_call
    @staticmethod
    def clip_info(animation_path: str) -> str:
        """Dados de um clipe para montar receitas: duração, quadros, avanço do quadril (frente) e posição do quadril
        no início e no fim (sentado → de pé sobe).

        Args:
            animation_path: caminho do AnimSequence.

        Returns:
            JSON {duracao, quadros, avanco_cm, quadril_ini, quadril_fim}.
        """
        a = unreal.load_asset(animation_path)
        if not isinstance(a, unreal.AnimSequence):
            return _j(ok=False, erro="clipe_nao_encontrado")
        dur = float(a.get_play_length())
        quads = int(unreal.AnimationLibrary.get_num_frames(a))
        ini = _osso_no_quadro(a, "Hips", 0)
        fim = _osso_no_quadro(a, "Hips", quads - 1)
        return _j(ok=True, duracao=round(dur, 4), quadros=quads, avanco_cm=round(DirectorTools._avanco(a), 2),
                  quadril_ini=_v(ini), quadril_fim=_v(fim))

    @staticmethod
    def _avanco(a) -> float:
        """Avanço do quadril no eixo de frente do clipe (eixo 3 nos Mixamo da biblioteca), extrapolado ao fim."""
        quads = int(unreal.AnimationLibrary.get_num_frames(a))
        z = [_osso_no_quadro(a, "Hips", q).z for q in (0, quads - 1, max(quads - 2, 0))]
        return (z[1] - z[0]) + (z[1] - z[2])

    @staticmethod
    def _montar(seq, ator, passos, anims, dir_x, dir_y, fps) -> str:
        seq.set_display_rate(unreal.FrameRate(fps, 1))
        lig = seq.add_possessable(ator)
        trilha = lig.add_track(unreal.MovieSceneSkeletalAnimationTrack)
        trans = lig.add_track(unreal.MovieScene3DTransformTrack).add_section()
        base, rot = ator.get_actor_location(), ator.get_actor_rotation()
        n = math.hypot(dir_x, dir_y) or 1.0
        dx, dy = dir_x / n, dir_y / n
        x, y, yaw, quadro, faixas, chaves = base.x, base.y, rot.yaw, 0, [], []
        for p, a in zip(passos, anims):
            giro = float(p.get("turn_deg", 0.0))
            if giro:
                c, s = math.cos(math.radians(giro)), math.sin(math.radians(giro))
                dx, dy, yaw = dx * c - dy * s, dx * s + dy * c, yaw + giro
            nq = max(1, round(float(a.get_play_length()) * fps))
            sec = trilha.add_section()
            sec.set_range(quadro, quadro + nq)
            prm = sec.get_editor_property("params")
            prm.set_editor_property("animation", a)
            sec.set_editor_property("params", prm)
            av = DirectorTools._avanco(a)
            chaves.append((quadro, x, y, yaw))
            faixas.append({"clipe": a.get_name(), "de": quadro, "ate": quadro + nq, "avanco_cm": round(av, 2),
                           "inicio_xy": [round(x, 1), round(y, 1)], "yaw": round(yaw, 1)})
            x, y, quadro = x + dx * av, y + dy * av, quadro + nq
        trans.set_range(0, quadro)
        canais = trans.get_all_channels()  # 0-2 loc x,y,z; 3-5 rot (roll, pitch, yaw); 6-8 escala
        k = lambda canal, q, v: canal.add_key(unreal.FrameNumber(q), v, 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE,
                                               unreal.MovieSceneKeyInterpolation.CONSTANT)
        for q, cx, cy, cyaw in chaves:
            for i, v in ((0, cx), (1, cy), (2, base.z), (5, cyaw)):
                k(canais[i], q, v)
        for i, v in ((3, rot.roll), (4, rot.pitch), (6, 1.0), (7, 1.0), (8, 1.0)):
            k(canais[i], 0, v)
        seq.set_playback_start(0)
        seq.set_playback_end(quadro)
        return _j(ok=True, sequencia=seq.get_path_name(), quadros=quadro, faixas=faixas,
                  fim_previsto_xy=[round(x, 1), round(y, 1)])

    @toolset_registry.tool_call
    @staticmethod
    def seq_key_transform(sequence_path: str, actor_label: str, keys_json: str) -> str:
        """Anima um segundo ator (ex. folha de porta) na MESMA sequência de teste com chaves de posição e giro
        (interpolação linear). Só em SEQ_TESTE_*.

        Args:
            sequence_path: caminho da Level Sequence de teste.
            actor_label: rótulo exato do ator a animar.
            keys_json: lista JSON [[quadro, x, y, z, yaw], ...] em ordem.

        Returns:
            JSON com o número de chaves gravadas.
        """
        if "/SEQ_TESTE_" not in sequence_path:
            return _j(ok=False, erro="so_em_SEQ_TESTE")
        seq = unreal.load_asset(sequence_path)
        ator, parecidos = _achar(actor_label)
        if not isinstance(seq, unreal.LevelSequence) or ator is None:
            return _j(ok=False, erro="sequencia_ou_ator_nao_encontrado", candidatos=parecidos)
        chaves = json.loads(keys_json)
        sec = seq.add_possessable(ator).add_track(unreal.MovieScene3DTransformTrack).add_section()
        sec.set_range(0, int(seq.get_playback_end()))
        canais = sec.get_all_channels()
        rot, esc = ator.get_actor_rotation(), ator.get_actor_scale3d()
        lin = unreal.MovieSceneKeyInterpolation.LINEAR
        for q, x, y, z, yaw in chaves:
            for i, v in ((0, x), (1, y), (2, z), (5, yaw)):
                canais[i].add_key(unreal.FrameNumber(int(q)), float(v), 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, lin)
        for i, v in ((3, rot.roll), (4, rot.pitch), (6, esc.x), (7, esc.y), (8, esc.z)):
            canais[i].add_key(unreal.FrameNumber(0), float(v), 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, lin)
        return _j(ok=True, chaves=len(chaves))

    @toolset_registry.tool_call
    @staticmethod
    def seq_eval_frame(sequence_path: str, frame: int) -> str:
        """Abre a sequência no Sequencer (se preciso) e põe o cursor no quadro: o editor avalia a cena nesse instante.
        Ler ossos/capturar em OUTRA chamada.

        Args:
            sequence_path: caminho da Level Sequence.
            frame: quadro (na taxa de exibição).

        Returns:
            JSON ok.
        """
        seq = unreal.load_asset(sequence_path)
        if not isinstance(seq, unreal.LevelSequence):
            return _j(ok=False, erro="sequencia_nao_encontrada")
        lib = unreal.LevelSequenceEditorBlueprintLibrary
        if lib.get_current_level_sequence() != seq:
            lib.open_level_sequence(seq)
        lib.set_current_time(frame)
        return _j(ok=True, quadro=frame)

    @toolset_registry.tool_call
    @staticmethod
    def seq_close_delete(sequence_path: str) -> str:
        """Fecha o Sequencer (o ator volta ao estado original) e apaga a sequência de teste (só SEQ_TESTE_*, nunca
        salva).

        Args:
            sequence_path: caminho da Level Sequence de teste.

        Returns:
            JSON com o que foi feito.
        """
        if "/SEQ_TESTE_" not in sequence_path:
            return _j(ok=False, erro="so_apago_SEQ_TESTE")
        unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
        apagou = unreal.EditorAssetLibrary.delete_asset(sequence_path.split(".")[0])
        return _j(ok=True, apagou=bool(apagou))

    @toolset_registry.tool_call
    @staticmethod
    def capture_isolated_setup(actor_label: str, yaw_deg: float, pitch_deg: float, distance_cm: float,
                               width: int, height: int, also_show: str, center_bone: str) -> str:
        """Prepara a câmera de captura isolada: só o ator pedido é renderizado (lista show-only); nada no level é
        escondido ou alterado. Reaproveita o rig se já existir. A foto sai em capture_isolated_shot.

        Args:
            actor_label: rótulo exato do ator.
            yaw_deg: ângulo horizontal da câmera em volta do ator (0 = eixo +X).
            pitch_deg: elevação da câmera em graus.
            distance_cm: distância ao centro do ator; 0 = automática (2,5 x o raio).
            width: largura da imagem em pixels.
            height: altura da imagem em pixels.
            also_show: rótulos exatos de outros atores que também aparecem (cenário: banco, porta), separados por
                vírgula; vazio = só o ator.
            center_bone: osso para mirar (ex. Hips: câmera acompanha o corpo, não o centro geométrico do ator);
                vazio = centro dos limites do ator.

        Returns:
            JSON com a pose da câmera e o centro do ator.
        """
        ator, parecidos = _achar(actor_label)
        if ator is None:
            return _j(ok=False, erro="ator_nao_encontrado", candidatos=parecidos)
        st = _estado()
        mundo = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        centro, ext = ator.get_actor_bounds(False)
        raio = max(ext.x, ext.y, ext.z, 50.0)
        comp = _skel(ator) if center_bone else None
        if comp is not None and comp.does_socket_exist(center_bone):
            osso = comp.get_socket_location(center_bone)
            centro = unreal.Vector(osso.x, osso.y, osso.z - 5.0)
        dist = distance_cm if distance_cm > 0 else max(2.5 * raio, 200.0)
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        cam = unreal.Vector(centro.x + math.cos(pitch) * math.cos(yaw) * dist,
                            centro.y + math.cos(pitch) * math.sin(yaw) * dist,
                            centro.z + math.sin(pitch) * dist)
        olhar = unreal.MathLibrary.find_look_at_rotation(cam, centro)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if st.rig is None or not unreal.SystemLibrary.is_valid(st.rig):
            st.rig = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, olhar)
            st.rig.set_actor_label(ROTULO_RIG)
        else:
            st.rig.set_actor_location(cam, False, False)
            st.rig.set_actor_rotation(olhar, False)
        cap = st.rig.get_editor_property("capture_component2d")
        if st.rt is None or getattr(st, "rt_tam", None) != (width, height):  # câmera que acompanha: reaproveita
            st.rt = unreal.RenderingLibrary.create_render_target2d(mundo, width, height,
                                                                   unreal.TextureRenderTargetFormat.RTF_RGBA8)
            st.rt_tam = (width, height)
        cap.set_editor_property("texture_target", st.rt)
        # VERA: SCS_BASE_COLOR sai branco no 5.7; FINAL_COLOR_LDR funciona
        cap.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
        cap.set_editor_property("primitive_render_mode", unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
        cap.clear_show_only_components()
        cap.show_only_actor_components(ator, True)  # a propriedade não é editável: usar o setter
        extras, faltam = [], []
        for rot in [r.strip() for r in also_show.split(",") if r.strip()]:
            outro, _ = _achar(rot)
            if outro is None:
                faltam.append(rot)
            else:
                cap.show_only_actor_components(outro, True)
                extras.append(rot)
        # céu/atmosfera/nuvens/neblina não são primitivos da lista e continuam aparecendo (Unreal real, 06/10):
        # desligados, o fundo fica preto e a silhueta sai por limiar simples
        flags = []
        for nome in FLAGS_FUNDO:
            s = unreal.EngineShowFlagsSetting()
            s.set_editor_property("show_flag_name", nome)
            s.set_editor_property("enabled", False)
            flags.append(s)
        cap.set_editor_property("show_flag_settings", flags)
        st.alvo = actor_label
        return _j(ok=not faltam, rig=ROTULO_RIG, camera=_v(cam), centro=_v(centro), distancia=round(dist, 1),
                  tambem=extras, nao_encontrados=faltam)

    @toolset_registry.tool_call
    @staticmethod
    def capture_isolated_shot(directory: str, filename: str) -> str:
        """Tira a foto da captura isolada e grava um PNG. Chamar DEPOIS (em outra chamada) de mudar pose ou câmera.

        Args:
            directory: pasta de destino (absoluta).
            filename: nome do arquivo sem caminho.

        Returns:
            JSON com o caminho do arquivo gravado.
        """
        st = _estado()
        if st.rig is None or not unreal.SystemLibrary.is_valid(st.rig):
            return _j(ok=False, erro="sem_rig", dica="chame capture_isolated_setup antes")
        mundo = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        st.rig.get_editor_property("capture_component2d").capture_scene()
        os.makedirs(directory, exist_ok=True)
        unreal.RenderingLibrary.export_render_target(mundo, st.rt, directory, filename)
        caminho = os.path.join(directory, filename)
        candidatos = [caminho] + [caminho + e for e in (".png", ".hdr", ".exr")]
        gravado = next((c for c in candidatos if os.path.exists(c)), None)
        return _j(ok=gravado is not None, arquivo=gravado, alvo=st.alvo,
                  erro=None if gravado else "arquivo_nao_gravado")

    @toolset_registry.tool_call
    @staticmethod
    def capture_isolated_restore() -> str:
        """Desfaz tudo o que a captura isolada e set_pose_eval fizeram: destrói o rig e devolve a opção de tick dos
        personagens. Idempotente: chamar sem nada ativo não faz mal.

        Returns:
            JSON com o que foi restaurado e erros.
        """
        st = sys.modules.pop(ESTADO, None)
        if st is None:
            return _j(ok=True, restaurado=False, motivo="nada_ativo")
        erros, ticks = [], 0
        try:
            if st.rig is not None and unreal.SystemLibrary.is_valid(st.rig):
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(st.rig)
        except Exception as e:  # restauração segue mesmo com erro parcial
            erros.append(f"rig: {e}")
        for caminho, opcao in st.tick_anterior.items():
            try:
                comp = unreal.find_object(None, caminho)
                if comp is not None:
                    comp.set_editor_property("visibility_based_anim_tick_option", opcao)
                    ticks += 1
            except Exception as e:
                erros.append(f"tick {caminho}: {e}")
        return _j(ok=not erros, restaurado=True, ticks_restaurados=ticks, erros=erros[:5])
