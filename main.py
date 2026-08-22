
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from config import DIGEST_HORA_UTC, INTERVALO_MINUTOS, LIMIAR_DIGEST_IMEDIATO
from database.database import (
    BancoVazioSuspeito,
    definir_metadado,
    iniciar_db,
    ja_vista,
    marcar_digest_enviado,
    obter_metadado,
    obter_vagas_pendentes_digest,
    salvar_vaga,
)
from notifier.telegram import (
    enviar_digest,
    enviar_mensagem,
    notificar_vaga,
    notificar_vaga_exploratoria,
    processar_feedback_pendente,
)
from perfis import FREQUENCIA_ALTA, PERFIS, Perfil, obter_scrapers_dinamicos, obter_regras_perfil, obter_termos_busca_perfil
from utils.filtro import filtrar_vagas
from logger import get_logger

logger = get_logger()


def _fontes_baixa_frequencia_ja_rodaram_hoje(perfil: Perfil) -> bool:
    chave = f"baixa_frequencia_ultimo_dia_{perfil.chave}"
    return obter_metadado(chave) == date.today().isoformat()


# Não é mais uma lista fixa construída uma vez: os scrapers recebem só o
# BLOCO de termos do ciclo atual (ver _proximo_bloco_termos), e a lista de
# QUAIS fontes entram também varia por ciclo (fonte de baixa frequência só
# entra na primeira execução do dia) — então precisam ser (re)criados a
# cada ciclo, não guardados numa constante de módulo. Cada perfil tem sua
# própria chave de metadados (sufixo perfil.chave), pra rodar dois perfis
# na mesma execução sem um pisar na cadência do outro.
def _construir_scrapers(perfil: Perfil, termos_busca: list[str]):
    rodar_baixa_frequencia = not _fontes_baixa_frequencia_ja_rodaram_hoje(perfil)
    definicoes = obter_scrapers_dinamicos(perfil.chave)

    scrapers = [
        definicao.classe(termos_busca=termos_busca, **definicao.kwargs_extras)
        for definicao in definicoes
        if definicao.frequencia == FREQUENCIA_ALTA or rodar_baixa_frequencia
    ]

    if rodar_baixa_frequencia:
        # Marca ANTES de rodar (não depois): mesmo que uma fonte de baixa
        # frequência falhe nesse ciclo, ela "rodou" no sentido de já ter
        # sido tentada hoje — não deve ser tentada de novo no ciclo
        # seguinte só porque deu erro. Falha individual já é tratada e
        # logada normalmente em ciclo_de_busca(), como qualquer scraper.
        definir_metadado(f"baixa_frequencia_ultimo_dia_{perfil.chave}", date.today().isoformat())

    return scrapers


def _proximo_bloco_termos(perfil: Perfil) -> list[str]:
    from perfis import obter_termos_busca_perfil
    termos_busca_atuais = obter_termos_busca_perfil(perfil.chave)
    total = len(termos_busca_atuais)
    if total == 0:
        return []

    tamanho_bloco = min(perfil.termos_por_ciclo, total)

    chave_offset = f"termos_offset_{perfil.chave}"
    offset_salvo = obter_metadado(chave_offset)
    offset = int(offset_salvo) % total if offset_salvo else 0

    bloco = [termos_busca_atuais[(offset + i) % total] for i in range(tamanho_bloco)]
    definir_metadado(chave_offset, str((offset + tamanho_bloco) % total))

    return bloco


def _enviar_heartbeat_diario(
    perfil: Perfil, total_novas: int, scrapers_com_problema: list[str], total_fontes: int
):
    """No máximo 1 mensagem por dia (por perfil) confirmando que o ciclo
    rodou.

    O alerta de saúde só dispara quando ≥50% das fontes falha — mas se o
    workflow parar de rodar por completo (cron desabilitado pelo GitHub
    Actions por inatividade do repositório, erro de config, etc.), não
    existe ALERTA NENHUM disso: silêncio no Telegram fica idêntico a "rodou
    e não achou vaga nova". O heartbeat fecha essa lacuna — se ele parar de
    chegar um dia, o problema é o workflow não estar rodando, não a busca
    não ter achado nada. Por perfil: silêncio só do perfil Internacional
    (por exemplo) fica visível mesmo com o perfil Brasil rodando normal.

    A data do último envio fica salva no próprio jobs.db (tabela
    metadados), então sobrevive entre execuções do GitHub Actions (cada
    run é uma máquina nova) e não manda duplicado se o workflow rodar mais
    de uma vez no mesmo dia (cron normal ou workflow_dispatch manual).
    """
    chave = f"heartbeat_ultimo_dia_{perfil.chave}"
    hoje = date.today().isoformat()
    if obter_metadado(chave) == hoje:
        return

    hora_brasilia = datetime.now(timezone.utc).strftime("%H:%M UTC")
    if scrapers_com_problema:
        status = f"{len(scrapers_com_problema)}/{total_fontes} fonte(s) com problema"
    else:
        status = "todas as fontes ok"

    enviar_mensagem(
        f"💓 <b>JobRadar {perfil.nome} ativo</b>\n\n"
        f"Confirmação diária: o ciclo rodou agora ({hora_brasilia}, {status}). "
        f"{total_novas} vaga(s) nova(s) neste ciclo.\n\n"
        "Se essa mensagem parar de chegar, o workflow parou de rodar — "
        "não que faltou vaga."
    )
    definir_metadado(chave, hoje)


def _enviar_digest_diario(perfil: Perfil):
    """No máximo 1 digest por dia (por perfil) — ver item 08. Junta tudo
    que ficou digest_pendente=1 desde o último envio (pode ser de vários
    ciclos de 3h) e manda ranqueado, melhor primeiro.

    Disparo: no ciclo cujo horário UTC bate com DIGEST_HORA_UTC (0 =
    meia-noite UTC = 21h em Brasília) — o cron já passa por essa hora
    exata todo dia, não precisa de agendamento à parte. Mesma lógica de
    "só uma vez por dia" do heartbeat (data salva em metadados), mas com
    um reforço: se por qualquer motivo o ciclo exato de DIGEST_HORA_UTC
    falhar/pular um dia inteiro, manda no primeiro ciclo depois de 24h
    sem envio — não deixa a fila crescer indefinidamente esperando um
    horário exato que pode não voltar a bater certo (ex: workflow atrasado
    pelo GitHub Actions naquele dia).
    """
    chave = f"digest_ultimo_dia_{perfil.chave}"
    hoje = date.today()
    agora = datetime.now(timezone.utc)

    ultimo_envio_str = obter_metadado(chave)
    se_ja_enviou_hoje = ultimo_envio_str == hoje.isoformat()
    if se_ja_enviou_hoje:
        return

    horario_certo = agora.hour == DIGEST_HORA_UTC
    atrasado = ultimo_envio_str is not None and (
        hoje - date.fromisoformat(ultimo_envio_str)
    ).days >= 2
    if not (horario_certo or atrasado):
        return

    vagas_pendentes = obter_vagas_pendentes_digest(perfil.chave)
    if not vagas_pendentes:
        # Marca mesmo sem vaga nenhuma — senão o "atrasado" acima dispara
        # todo ciclo seguinte até aparecer alguma vaga pendente de novo.
        definir_metadado(chave, hoje.isoformat())
        return

    if enviar_digest(vagas_pendentes, perfil.nome):
        marcar_digest_enviado(perfil.chave)
        definir_metadado(chave, hoje.isoformat())
        logger.info(f"[{perfil.nome}] Digest diário enviado: {len(vagas_pendentes)} vaga(s).")
    else:
        # Não marca metadado nem limpa a fila — tenta de novo no próximo
        # ciclo (ver enviar_digest/marcar_digest_enviado: preferir duplicar
        # a perder vaga).
        logger.warning(
            f"[{perfil.nome}] Falha ao enviar digest diário ({len(vagas_pendentes)} vaga(s) "
            "pendentes) - tenta de novo no próximo ciclo."
        )


def ciclo_de_busca(perfil: Perfil):
    from perfis import obter_regras_perfil, obter_termos_busca_perfil

    total_novas = 0
    total_brutas = 0
    total_filtradas = 0
    scrapers_com_problema = []
    descartes_escopo_ciclo: Counter = Counter()
    novas_vagas_ciclo = []

    regras_atuais = obter_regras_perfil(perfil.chave)
    termos_busca_atuais = obter_termos_busca_perfil(perfil.chave)

    termos_do_ciclo = _proximo_bloco_termos(perfil)
    logger.info(
        f"[{perfil.nome}] Bloco de termos deste ciclo: {len(termos_do_ciclo)}/"
        f"{len(termos_busca_atuais)} — {', '.join(termos_do_ciclo)}"
    )
    scrapers = _construir_scrapers(perfil, termos_do_ciclo)

    # A parte lenta (abrir navegador, navegar, esperar seletor) roda em
    # paralelo aqui. Tudo que segue (filtrar, checar dedup, notificar,
    # salvar) continua rodando só na thread principal, um scraper de cada
    # vez, conforme a future dele termina — nunca duas threads escrevendo
    # no SQLite ou chamando o Telegram ao mesmo tempo. Cada scraper já é
    # auto-contido (cria e fecha seu(s) próprio(s) browser(s) Playwright
    # dentro de buscar_vagas()), então dá pra rodar vários ao mesmo tempo em
    # threads sem risco — nenhum compartilha Browser/Page com outro.
    with ThreadPoolExecutor(max_workers=perfil.max_scrapers_concorrentes) as executor:
        futures = {executor.submit(scraper.buscar_vagas): scraper for scraper in scrapers}

        for future in as_completed(futures):
            scraper = futures[future]
            nome = scraper.__class__.__name__

            try:
                vagas = future.result()
            except Exception as e:
                logger.error(f"[{perfil.nome}] Erro no scraper {nome}: {e}")
                scrapers_com_problema.append(nome)
                continue

            # Cada scraper trata timeout por termo internamente (só loga e
            # segue pro próximo termo), então um site totalmente bloqueado
            # não lança exceção pra cá — só devolve lista vazia. Por isso
            # também contamos "0 vaga bruta nessa fonte" como problema, não
            # só exceção.
            if not vagas:
                logger.warning(f"[{perfil.nome}] {nome} não retornou nenhuma vaga bruta neste ciclo.")
                scrapers_com_problema.append(nome)
                continue

            total_brutas += len(vagas)
            vagas_filtradas, descartes = filtrar_vagas(vagas, regras_atuais)
            descartes_escopo_ciclo.update(descartes)

            # Eixo secundário (Ibéria, quando ligado): mesma regra de cargo,
            # cidade diferente — sem duplicar o que já bateu na regra
            # primária.
            vagas_secundarias = []
            if perfil.eixo_secundario_ativo and perfil.regras_eixo_secundario is not None:
                ids_filtradas = {v.id for v in vagas_filtradas}
                candidatas, descartes_secundario = filtrar_vagas(vagas, perfil.regras_eixo_secundario)
                descartes_escopo_ciclo.update(descartes_secundario)
                vagas_secundarias = [v for v in candidatas if v.id not in ids_filtradas]

            total_filtradas += len(vagas_filtradas) + len(vagas_secundarias)

            novas_da_fonte = 0
            for vaga in vagas_filtradas:
                if ja_vista(vaga):
                    continue

                salvar_vaga(vaga, perfil_chave=perfil.chave)
                logger.info(f"[{perfil.nome}] Nova vaga encontrada: {vaga.titulo} - {vaga.empresa}")

                total_novas += 1
                novas_da_fonte += 1
                novas_vagas_ciclo.append(vaga)

            for vaga in vagas_secundarias:
                if ja_vista(vaga):
                    continue

                salvar_vaga(vaga, perfil_chave=perfil.chave, exploratoria=True)
                logger.info(
                    f"[{perfil.nome}] Nova vaga exploratória ({perfil.eixo_secundario_rotulo}): "
                    f"{vaga.titulo} - {vaga.empresa}"
                )

                total_novas += 1
                novas_da_fonte += 1
                novas_vagas_ciclo.append(vaga)

            logger.info(
                f"[{perfil.nome}][{nome}] Funil: {len(vagas)} brutas → "
                f"{len(vagas_filtradas) + len(vagas_secundarias)} filtradas → {novas_da_fonte} novas"
            )

    logger.info(
        f"[{perfil.nome}] Ciclo concluído: {total_brutas} brutas → {total_filtradas} filtradas → "
        f"{total_novas} nova(s)."
    )

    if novas_vagas_ciclo:
        from notifier.dispatcher import enviar_digest_email_multicanal
        logger.info(f"[{perfil.nome}] Disparando 1 e-mail consolidado com {len(novas_vagas_ciclo)} nova(s) vaga(s)...")
        enviar_digest_email_multicanal(novas_vagas_ciclo)

    # MEDIDO: descarte por escopo era invisível no log — o funil mostra
    # bruta → filtrada → nova, mas nunca QUAL escopo derrubou vaga nem
    # QUANTAS. Um escopo mal reconhecido (texto cru tipo "lagos nigeria",
    # não mapeado em _MERCADOS_REMOTO) barra do jeito certo, mas some sem
    # rastro — foi assim que um bug real (escopo virando allowlist) passou
    # despercebido até virar relato explícito. Loga só quando há descarte
    # (a maioria dos ciclos não tem nenhum), ordenado do que mais derrubou
    # vaga pro que menos derrubou.
    if descartes_escopo_ciclo:
        detalhe = "; ".join(
            f"{escopo} ({n})" for escopo, n in descartes_escopo_ciclo.most_common()
        )
        logger.info(f"[{perfil.nome}] Descarte por escopo: {detalhe}")

    # Alerta de saúde: se a maioria das fontes falhou/voltou vazia, avisa no
    # Telegram. Sem isso, um bloqueio geral ou mudança de layout passaria
    # despercebido — o workflow do GitHub Actions continuaria "verde" mesmo
    # com tudo quebrado.
    if scrapers and len(scrapers_com_problema) >= len(scrapers) / 2:
        enviar_mensagem(
            f"⚠️ <b>JobRadar {perfil.nome} com problema</b>\n\n"
            f"{len(scrapers_com_problema)}/{len(scrapers)} fontes falharam ou voltaram "
            f"vazias neste ciclo: {', '.join(scrapers_com_problema)}.\n\n"
            "Vale checar o log do GitHub Actions."
        )

    _enviar_heartbeat_diario(perfil, total_novas, scrapers_com_problema, len(scrapers))
    _enviar_digest_diario(perfil)


def _rodar_um_ciclo_de_cada(perfis: list[Perfil]):
    # Uma vez por execução, não por perfil: o offset do getUpdates (ver
    # processar_feedback_pendente) é global — feedback de vaga não tem
    # perfil, e rodar duas vezes na mesma execução só gastaria uma chamada
    # de API à toa (a segunda sempre veria "nada novo desde a última vez").
    processar_feedback_pendente()

    for perfil in perfis:
        print(f"\n{'=' * 50}")
        print(f"PERFIL: {perfil.nome.upper()}")
        print("=" * 50)

        print("\nPalavras monitoradas:")
        for palavra in perfil.palavras_monitoradas:
            print(f"• {palavra}")

        if perfil.paises_pesquisados:
            print("\nPaíses pesquisados:")
            for pais in perfil.paises_pesquisados:
                print(f"• {pais}")

        ciclo_de_busca(perfil)

    try:
        from database.database import _conectar
        with _conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, titulo, empresa, local, link AS url, site AS fonte,
                       encontrada_em AS criado_em, modalidade, relevancia AS score,
                       publicado_em
                FROM vagas_vistas
                ORDER BY encontrada_em DESC, ROWID DESC
                LIMIT 100
                """
            )
            colunas = [col[0] for col in cursor.description]
            vagas = [dict(zip(colunas, r)) for r in cursor.fetchall()]

        usuarios_firebase = []
        try:
            from firebase_service import is_firebase_disponivel, obter_todos_usuarios_ativos, deve_enviar_alerta, atualizar_ultimo_envio
            if is_firebase_disponivel():
                usuarios_firebase = obter_todos_usuarios_ativos()
        except Exception as e:
            logger.debug(f"[Multi-User] Verificação do Firebase: {e}")

        if usuarios_firebase:
            from perfis import criar_regras_usuario
            from job import Job
            from notifier.dispatcher import enviar_digest_email_para_usuario

            logger.info(f"[Multi-User] Processando alertas para {len(usuarios_firebase)} usuário(s) do Firebase...")
            for usr in usuarios_firebase:
                uid = usr.get("uid")
                freq = usr.get("frequencia_alerta", "a_cada_3_horas")
                ultimo_envio = usr.get("ultimo_envio_email")

                if not deve_enviar_alerta(freq, ultimo_envio):
                    logger.info(f"[Multi-User] Usuário {usr.get('email_destinatario')} fora da janela de disparo (frequência: {freq}).")
                    continue

                regras_usr = criar_regras_usuario(usr)
                vagas_usr = []
                for v_raw in vagas:
                    j = Job(
                        titulo=v_raw.get("titulo") or "",
                        empresa=v_raw.get("empresa") or "",
                        local=v_raw.get("local") or "",
                        link=v_raw.get("url") or "",
                        site=v_raw.get("fonte") or "",
                        publicado_em=v_raw.get("publicado_em") or "",
                        modalidade=v_raw.get("modalidade") or "",
                    )
                    if j.combina_com(regras_usr):
                        v_copy = dict(v_raw)
                        v_copy["score"] = j.pontuar_relevancia(regras_usr)
                        vagas_usr.append(v_copy)

                if vagas_usr:
                    ok = enviar_digest_email_para_usuario(usr, vagas_usr)
                    if ok and uid:
                        atualizar_ultimo_envio(uid)
                        logger.info(f"[Multi-User] Digest enviado para {usr.get('email_destinatario')} ({len(vagas_usr)} vagas).")
        elif vagas:
            from notifier.dispatcher import enviar_digest_email_multicanal
            enviar_digest_email_multicanal(vagas)
    except Exception as e:
        logger.warning(f"Erro ao enviar digest por e-mail no ciclo: {e}")

    try:
        from database.database import exportar_jobs_json
        exportar_jobs_json()
    except Exception as e:
        logger.warning(f"Erro ao exportar data/jobs.json: {e}")





def main():
    parser = argparse.ArgumentParser(description="JobRadar - monitor de vagas")
    parser.add_argument(
        "--perfil",
        required=True,
        nargs="+",
        choices=sorted(PERFIS.keys()),
        help=(
            "Qual(is) mercado(s) rodar nesta execução — 'brasil', 'internacional', "
            "ou os dois (--perfil brasil internacional)."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Roda um único ciclo de busca (de cada perfil selecionado) e encerra "
             "(usado no GitHub Actions, que já dispara o script periodicamente via cron).",
    )
    args = parser.parse_args()

    perfis_selecionados = [PERFIS[chave] for chave in args.perfil]

    if not args.once:
        print(f"\nIntervalo de checagem: {INTERVALO_MINUTOS} min\n")

    # Chamado UMA VEZ só, antes de qualquer perfil rodar — não por perfil.
    # A checagem de "banco suspeito" (ver database.py) compara se o arquivo
    # já existia ANTES desta execução; se cada perfil chamasse iniciar_db()
    # separadamente na mesma execução, o segundo perfil veria o arquivo que
    # o primeiro acabou de criar/popular momentos atrás e podia disparar
    # falso positivo (arquivo "já existia" só porque o perfil anterior já
    # rodou nesta mesma execução, não porque é run antigo de verdade).
    try:
        iniciar_db()
    except BancoVazioSuspeito as e:
        logger.error(str(e))
        nomes = ", ".join(p.nome for p in perfis_selecionados)
        enviar_mensagem(f"🛑 <b>JobRadar abortado</b>\n\nPerfis desta execução: {nomes}\n\n{e}")
        sys.exit(1)

    if args.once:
        _rodar_um_ciclo_de_cada(perfis_selecionados)
        return

    while True:
        _rodar_um_ciclo_de_cada(perfis_selecionados)
        logger.info(f"Aguardando {INTERVALO_MINUTOS} minutos até a próxima checagem...")
        time.sleep(INTERVALO_MINUTOS * 60)


if __name__ == "__main__":
    main()
