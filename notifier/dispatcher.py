from __future__ import annotations

import json
from datetime import datetime, timezone
from config_manager import carregar_config
from logger import get_logger
from notifier.email_notifier import enviar_email, construir_digest_html

logger = get_logger()


def deve_enviar_email_agora(frequencia: str) -> bool:
    """Verifica se o intervalo de tempo necessário para a frequência configurada já foi atingido."""
    from database.database import obter_metadado
    ultimo_envio_str = obter_metadado("ultimo_envio_email_timestamp")
    if not ultimo_envio_str:
        config = carregar_config()
        ultimo_envio_str = config.get("ultimo_envio_email_timestamp")

    if not ultimo_envio_str:
        return True

    try:
        ultimo_envio = datetime.fromisoformat(ultimo_envio_str)
        agora = datetime.now(timezone.utc)
        horas_decorridas = (agora - ultimo_envio).total_seconds() / 3600.0
    except Exception:
        return True

    if frequencia == "a_cada_3_horas":
        return True
    elif frequencia == "duas_vezes_ao_dia":
        return horas_decorridas >= 11.0
    elif frequencia == "uma_vez_ao_dia":
        return horas_decorridas >= 23.0
    elif frequencia == "a_cada_2_dias":
        return horas_decorridas >= 47.0
    elif frequencia == "a_cada_1_semana":
        return horas_decorridas >= (7 * 24 - 1.0)
    
    return True


def enviar_notificacao_multicanal(
    texto_simples: str,
    assunto: str = "Nova Vaga Encontrada pelo JobRadar",
    corpo_html: str | None = None,
    vagas_dict_list: list[dict] | None = None,
    forcar_canal: str | None = None,
) -> dict[str, tuple[bool, str]]:
    """Dispara a notificação para TODOS os canais ativados no user_config.json.
    Garante que qualquer alteração nas configurações (filtros, regras de bloqueio, pontuação mínima, ativação de canal)
    seja estritamente respeitada por todos os canais de notificação existentes e futuros.
    """
    config = carregar_config()
    canais = config.get("canais_notificacao", {})
    resultados = {}

    # 1. E-mail (SMTP)
    email_cfg = canais.get("email", {})
    if email_cfg.get("ativo", False) or forcar_canal == "email":
        html_msg = corpo_html or f"<pre style='font-family: sans-serif;'>{texto_simples}</pre>"
        ok, msg = enviar_email(
            destinatario=email_cfg.get("destinatario", ""),
            assunto=assunto,
            corpo_html=html_msg,
            smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
            smtp_port=email_cfg.get("smtp_port", 587),
            smtp_user=email_cfg.get("smtp_user", ""),
            smtp_pass=email_cfg.get("smtp_pass", ""),
        )
        resultados["email"] = (ok, msg)

    # 2. Telegram (Bot API)
    telegram_cfg = canais.get("telegram", {})
    if telegram_cfg.get("ativo", False) or forcar_canal == "telegram":
        token = telegram_cfg.get("bot_token", "").strip()
        chat_id = telegram_cfg.get("chat_id", "").strip()
        if token and chat_id:
            from notifier.telegram import enviar_mensagem
            ok = enviar_mensagem(texto_simples, chat_id=chat_id, token=token)
            resultados["telegram"] = (ok, "Mensagem enviada no Telegram" if ok else "Falha no envio Telegram")

    # 3. Webhook (HTTP POST)
    webhook_cfg = canais.get("webhook", {})
    if webhook_cfg.get("ativo", False) or forcar_canal == "webhook":
        url = webhook_cfg.get("url", "").strip()
        if url:
            try:
                import urllib.request
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"texto": texto_simples, "assunto": assunto, "vagas": vagas_dict_list or []}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ok = (200 <= resp.status < 300)
                    resultados["webhook"] = (ok, f"Webhook disparado (HTTP {resp.status})")
            except Exception as e:
                resultados["webhook"] = (False, f"Erro Webhook: {e}")

    # 4. Outros canais futuros configurados dinamicamente
    for canal_nome, canal_cfg in canais.items():
        if canal_nome in ("email", "telegram", "webhook"):
            continue
        if isinstance(canal_cfg, dict) and (canal_cfg.get("ativo", False) or forcar_canal == canal_nome):
            url_futura = canal_cfg.get("url") or canal_cfg.get("webhook_url")
            if url_futura:
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        url_futura,
                        data=json.dumps({"canal": canal_nome, "texto": texto_simples, "assunto": assunto, "vagas": vagas_dict_list or []}).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        ok = (200 <= resp.status < 300)
                        resultados[canal_nome] = (ok, f"Canal {canal_nome} disparado (HTTP {resp.status})")
                except Exception as e:
                    resultados[canal_nome] = (False, f"Erro no canal {canal_nome}: {e}")

    return resultados


def processar_envio_email_pendentes(forcar: bool = False) -> bool:
    """Envia um ÚNICO e-mail consolidado contendo as vagas inéditas salvas que ainda não foram enviadas,
    respeitando a frequência configurada e a nota mínima."""
    config = carregar_config()
    canais = config.get("canais_notificacao", {})
    email_cfg = canais.get("email", {})

    if not email_cfg.get("ativo", False):
        logger.info("[Dispatcher] E-mail desativado pelo usuário. Nenhum e-mail será enviado.")
        return False

    frequencia = config.get("frequencia_email", "a_cada_3_horas")
    if not forcar and not deve_enviar_email_agora(frequencia):
        logger.info(f"[Dispatcher] Frequência '{frequencia}' ativa. Vagas acumuladas para o próximo envio.")
        return False

    from database.database import obter_vagas_pendentes_email, marcar_email_enviado, definir_metadado

    vagas_pendentes = obter_vagas_pendentes_email("brasil")
    if not vagas_pendentes:
        logger.info("[Dispatcher] Nenhuma vaga inédita pendente de envio por e-mail.")
        return False

    score_minimo = config.get("score_minimo", "todos")
    if score_minimo not in ("todos", "0", 0, None):
        try:
            limiar = int(score_minimo)
            vagas_para_enviar = [v for v in vagas_pendentes if (v.get("score") or 5) >= limiar]
        except (ValueError, TypeError):
            vagas_para_enviar = vagas_pendentes
    else:
        vagas_para_enviar = vagas_pendentes

    if not vagas_para_enviar:
        # Marca como enviado para não travar na fila vagas abaixo do score mínimo
        marcar_email_enviado([v["id"] for v in vagas_pendentes if "id" in v])
        logger.info("[Dispatcher] Vagas pendentes filtradas por score mínimo. Fila liberada.")
        return False

    corpo_html = construir_digest_html(vagas_para_enviar)
    assunto = f"JobRadar — {len(vagas_para_enviar)} Nova(s) Vaga(s) Encontrada(s)"

    ok, msg = enviar_email(
        destinatario=email_cfg.get("destinatario", ""),
        assunto=assunto,
        corpo_html=corpo_html,
        smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
        smtp_port=email_cfg.get("smtp_port", 587),
        smtp_user=email_cfg.get("smtp_user", ""),
        smtp_pass=email_cfg.get("smtp_pass", ""),
    )

    if ok:
        ids_enviados = [v["id"] for v in vagas_pendentes if "id" in v]
        marcar_email_enviado(ids_enviados)
        agora_iso = datetime.now(timezone.utc).isoformat()
        definir_metadado("ultimo_envio_email_timestamp", agora_iso)
        from config_manager import salvar_config
        salvar_config({"ultimo_envio_email_timestamp": agora_iso})
        logger.info(f"[Dispatcher] E-mail consolidado com {len(vagas_para_enviar)} nova(s) vaga(s) enviado com sucesso!")
    else:
        logger.error(f"[Dispatcher] Erro ao enviar e-mail consolidado: {msg}")

    return ok


def enviar_digest_email_multicanal(vagas: list) -> bool:
    """Função compatível: redireciona para processar_envio_email_pendentes."""
    return processar_envio_email_pendentes(forcar=False)

