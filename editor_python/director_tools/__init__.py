"""Toolset do Director dentro do editor. Instalação: ver editor_python/LEIA.md."""
from toolset_registry.registration import Registration  # mesmo caminho dos toolsets da Epic (AIModuleToolset)

from .toolset import DirectorTools  # noqa: F401

_registration = Registration([DirectorTools])
