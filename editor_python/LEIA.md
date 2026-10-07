# DirectorTools: toolset Python dentro do editor

**Por quê.** O `execute_tool_script` da Epic roda num sandbox sem `unreal`. As peças do VERA e a leitura de ossos precisam da API completa. Com este toolset, elas aparecem como ferramentas normais no MCP oficial da porta 8001, sob a mesma trava do Director.

## Como o editor carrega
- O UE 5.8 põe cada pasta da variável `UE_PYTHONPATH` no `sys.path`.
- Ao abrir, ele roda o `init_unreal.py` de cada pasta do `sys.path` (conferido em `PythonScriptPlugin.cpp`).
- Assim **nada é escrito no projeto (Y:)**. O código fica nesta pasta, em C:.

## Instalar (uma vez; exige reiniciar o editor)
1. Combinar a janela com o Talis e pôr o Hermes em PAUSA.
2. Definir a variável de usuário (PowerShell):
   `[Environment]::SetEnvironmentVariable("UE_PYTHONPATH", "<repo>\editor_python", "User")`
   Se ela já existir, acrescentar com `;`, sem apagar.
3. Fechar e abrir o editor. No Output Log deve aparecer `DirectorTools registrado no ToolsetRegistry`.
4. Conferir: `python tools/bloco1_unreal.py ping`.

## Desinstalar
`[Environment]::SetEnvironmentVariable("UE_PYTHONPATH", $null, "User")` e reiniciar o editor.

## Ferramentas
Todas devolvem uma string JSON. Nenhuma salva asset nem level.

| Ferramenta | O que faz |
|---|---|
| `ping` | prova o Python completo (versão, mundo, nº de atores) |
| `list_actors` | inventário completo (o `find_actors` corta em 20) |
| `set_pose_eval` | liga/restaura a avaliação da pose fora do viewport |
| `bone_world_positions` | ossos no mundo, em cm |
| `bone_position_in_clip` | osso num instante do clipe, sem cena |
| `capture_isolated_setup` / `_shot` / `_restore` | captura só do ator pedido (adaptada do VERA), PNG em disco, restauração idempotente |
