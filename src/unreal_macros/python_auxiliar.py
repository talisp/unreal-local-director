"""Cálculo auxiliar do laboratório: subconjunto Python sem IO/imports, não régua Unreal.

Não é sandbox do perfil Hermes nem autorização para Python livre. Dados são JSON
copiados da campanha; o processo filho tem prazo e devolve somente stdout/stderr.
"""
import ast
import builtins
import json
import math
import statistics

FUNCOES = ('print', 'len', 'range', 'sum', 'min', 'max', 'abs', 'round', 'sorted',
           'enumerate', 'zip', 'list', 'dict', 'tuple', 'set', 'float', 'int', 'str', 'bool', 'all', 'any')
MODULOS = {'math': math, 'json': json, 'statistics': statistics}
ATRIBUTOS = {'math': {'dist', 'hypot', 'sqrt', 'isfinite', 'fabs', 'sin', 'cos', 'radians', 'degrees', 'pi'},
             'json': {'dumps', 'loads'}, 'statistics': {'mean', 'median', 'stdev', 'pstdev'}}
NOS = (ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.Name, ast.Load, ast.Store,
       ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Subscript, ast.Slice,
       ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.If, ast.IfExp, ast.For,
       ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.comprehension,
       ast.Call, ast.keyword, ast.Attribute, ast.JoinedStr, ast.FormattedValue,
       ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.Pass, ast.Break, ast.Continue)


def validar(texto: str):
    if len(texto) > 100_000:
        raise ValueError('script auxiliar grande demais')
    arvore = ast.parse(texto)
    for n in ast.walk(arvore):
        if not isinstance(n, NOS):
            raise ValueError(f'Python auxiliar não permite {type(n).__name__}; sem imports/IO/Unreal')
        if isinstance(n, ast.Name) and n.id.startswith('_'):
            raise ValueError('nomes internos proibidos')
        if isinstance(n, ast.Attribute):
            if not isinstance(n.value, ast.Name) or n.attr not in ATRIBUTOS.get(n.value.id, set()):
                raise ValueError('atributo fora das funções de cálculo permitidas')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id not in FUNCOES:
            raise ValueError('função fora do cálculo auxiliar permitido')
        if isinstance(n, ast.Assign) and any(not isinstance(t, (ast.Name, ast.Tuple, ast.List)) for t in n.targets):
            raise ValueError('não modificar objetos externos')
    return arvore


def executar(texto: str, dados):
    arvore = validar(texto)
    globais = {'__builtins__': {k: getattr(builtins, k) for k in FUNCOES}, **MODULOS, 'dados': dados}
    exec(compile(arvore, '<python-auxiliar-campanha>', 'exec'), globais)
