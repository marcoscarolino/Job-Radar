"""Relatório de precisão: aprovadas / notificadas, por fonte e por semana.

O funil que já existe no log de cada ciclo (ver main.py: "brutas → filtradas
→ novas") mede ESFORÇO, não ACERTO — 320 notificações por dia contam como
sucesso mesmo que nenhuma sirva pra nada. O botão 👍/👎 (feedback, ver
notifier/telegram.py) é o primeiro sinal real de "essa vaga prestou"; este
relatório é a primeira vez que esse sinal vira número, em vez de ficar só
espalhado no Telegram.

Aprovada = feedback = 'positivo'. Reprovada = feedback = 'negativo'. Vaga
sem reação nenhuma (feedback NULL — hoje a esmagadora maioria, o botão é
recente) conta pro total de notificadas mas NÃO entra em "avaliadas" nem
em nenhuma das duas taxas abaixo — não dá pra julgar o que ninguém julgou.

Duas taxas de propósito, não uma:
  aprovação/notificadas — a conta literal pedida (aprovadas / total
    notificado). Cai perto de zero enquanto pouca gente reage, mesmo pra
    fonte boa — é o denominador "de verdade", mas engana se lido sozinho.
  aprovação/avaliadas — aprovadas / (aprovadas + reprovadas). Ignora quem
    nunca recebeu reação; é o número que reflete precisão de fato, mas
    precisa de volume de reação pra ser confiável (3 avaliadas com 0
    positiva não é a mesma evidência que 30).
Mostrar as duas evita ler taxa baixa por falta de reação como se fosse
fonte ruim.

Usa só feedback (item 09) pra "aprovada" — não situacao (item 08).
Decisão tomada com o usuário: os dois medem coisas diferentes (reação de
qualidade da vaga vs. funil de candidatura), não valem soma.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime

from config import DB_PATH
from database.database import iniciar_db


def _carregar_linhas(conn) -> list[tuple[str, str, str | None]]:
    return conn.execute(
        "SELECT site, encontrada_em, feedback FROM vagas_vistas"
    ).fetchall()


def _taxa(positivas: int, base: int) -> str:
    return f"{100 * positivas / base:.0f}%" if base else "—"


def _linha_tabela(rotulo: str, notificadas: int, positivas: int, negativas: int) -> str:
    avaliadas = positivas + negativas
    return (
        f"{rotulo:<24} notificadas={notificadas:<5} avaliadas={avaliadas:<5} "
        f"👍={positivas:<4} 👎={negativas:<4} "
        f"aprovação/notificadas={_taxa(positivas, notificadas):<6} "
        f"aprovação/avaliadas={_taxa(positivas, avaliadas)}"
    )


def agregar_por_fonte(linhas: list[tuple[str, str, str | None]]) -> dict[str, tuple[int, int, int]]:
    """(notificadas, positivas, negativas) por site. Função pura, separada
    da impressão de propósito -- é a parte que vale testar sem construir
    banco nenhum (mesma lógica de _parsear_callback_data em
    notifier/telegram.py)."""
    agregados: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for site, _, feedback in linhas:
        agregados[site][0] += 1
        if feedback == "positivo":
            agregados[site][1] += 1
        elif feedback == "negativo":
            agregados[site][2] += 1
    return {site: tuple(valores) for site, valores in agregados.items()}


def agregar_por_semana(linhas: list[tuple[str, str, str | None]]) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Mesma agregação, chave (ano ISO, semana ISO) em vez de site."""
    agregados: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    for _, encontrada_em, feedback in linhas:
        try:
            data = datetime.fromisoformat(encontrada_em)
        except (TypeError, ValueError):
            continue  # linha com encontrada_em ausente/corrompido -- não deveria existir, mas não derruba o relatório
        ano_iso, semana_iso, _ = data.isocalendar()
        chave = (ano_iso, semana_iso)
        agregados[chave][0] += 1
        if feedback == "positivo":
            agregados[chave][1] += 1
        elif feedback == "negativo":
            agregados[chave][2] += 1
    return {chave: tuple(valores) for chave, valores in agregados.items()}


def ordenar_pior_primeiro(agregados: dict[str, tuple[int, int, int]]) -> list[tuple[str, tuple[int, int, int]]]:
    """Menor taxa de aprovação ENTRE AVALIADAS primeiro -- é o candidato a
    cortar, não o que tem mais volume bruto. Fonte sem avaliação nenhuma
    não tem como ser "pior" nem "melhor" ainda -- vai pro fim da lista
    (2 > qualquer taxa real, que fica sempre entre 0 e 1), não pro topo."""
    def chave_ordenacao(item):
        _, (notificadas, positivas, negativas) = item
        avaliadas = positivas + negativas
        return (positivas / avaliadas) if avaliadas else 2

    return sorted(agregados.items(), key=chave_ordenacao)


def relatorio_por_fonte(linhas: list[tuple[str, str, str | None]]):
    print("\n=== Por fonte (todo o histórico, pior primeiro) ===")
    for site, (notificadas, positivas, negativas) in ordenar_pior_primeiro(agregar_por_fonte(linhas)):
        print(_linha_tabela(site, notificadas, positivas, negativas))


def relatorio_por_semana(linhas: list[tuple[str, str, str | None]], semanas: int = 8):
    agregados = agregar_por_semana(linhas)
    print(f"\n=== Por semana (últimas {semanas}, todas as fontes somadas) ===")
    for ano_iso, semana_iso in sorted(agregados.keys())[-semanas:]:
        notificadas, positivas, negativas = agregados[(ano_iso, semana_iso)]
        rotulo = f"{ano_iso}-W{semana_iso:02d}"
        print(_linha_tabela(rotulo, notificadas, positivas, negativas))


def main():
    parser = argparse.ArgumentParser(
        description="Relatório de precisão (aprovadas/notificadas) por fonte e por semana."
    )
    parser.add_argument(
        "--semanas", type=int, default=8,
        help="Quantas semanas mais recentes mostrar no corte semanal (padrão: 8).",
    )
    args = parser.parse_args()

    # Roda a mesma migração leve que main.py roda no início de todo ciclo
    # (ver iniciar_db em database/database.py) -- este script é standalone,
    # rodado sob demanda, não dá pra assumir que main.py já rodou depois do
    # último `git pull` e criou a coluna `feedback` (ela só existe depois
    # da migração, não é original da tabela).
    iniciar_db()

    conn = sqlite3.connect(DB_PATH)
    try:
        linhas = _carregar_linhas(conn)
    finally:
        conn.close()

    if not linhas:
        print("Banco vazio -- nada pra medir ainda.")
        return

    total_avaliadas = sum(1 for _, _, feedback in linhas if feedback in ("positivo", "negativo"))
    print(f"{len(linhas)} vaga(s) notificada(s) no total, {total_avaliadas} com reação (👍/👎) registrada.")
    if total_avaliadas == 0:
        print(
            "Nenhuma reação ainda -- o botão 👍/👎 é recente. O relatório roda normal, "
            "mas toda taxa de aprovação vai aparecer vazia (—) até acumular reação de "
            "verdade nas próximas notificações."
        )

    relatorio_por_fonte(linhas)
    relatorio_por_semana(linhas, semanas=args.semanas)


if __name__ == "__main__":
    main()
