
from __future__ import annotations

from collections import Counter

from job import Job, RegrasFiltro


def filtrar_vagas(vagas: list[Job], regras: RegrasFiltro) -> tuple[list[Job], Counter]:
    """Além da lista aprovada, devolve um Counter com os escopos que
    causaram reprovação por mercado (ver Job.escopo_rejeitado_por_mercado)
    e quantas vagas cada um levou — ver MEDIDO lá pro motivo (descarte por
    escopo era invisível no log, só dava pra ver bruta → filtrada → nova,
    nunca o porquê)."""
    aprovadas = []
    descartes_escopo: Counter = Counter()
    for v in vagas:
        if v.combina_com(regras):
            v.relevancia = v.pontuar_relevancia(regras)
            v.motivo = v.motivo_aprovacao(regras)
            aprovadas.append(v)
        else:
            escopo = v.escopo_rejeitado_por_mercado(regras)
            if escopo:
                descartes_escopo[", ".join(sorted(escopo))] += 1
    return aprovadas, descartes_escopo