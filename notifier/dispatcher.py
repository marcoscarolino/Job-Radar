from __future__ import annotations

import json
import requests
from config_manager import carregar_config
from logger import get_logger
from notifier.email_notifier import enviar_email

logger = get_logger()


def enviar_notificacao_multicanal(
    texto_simples: str,
    assunto: str = "Nova Vaga Encontrada pelo JobRadar",
    corpo_html: str | None = None,
    reply_markup: dict | None = None,
    forcar_canal: str | None = None,
) -> dict[str, tuple[bool, str]]:
    """Dispara a notificação para os canais ativados no user_config.json (E-mail)."""
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

    return resultados


def enviar_digest_email_multicanal(vagas: list) -> bool:
    """Envia um ÚNICO e-mail consolidado contendo a lista de todas as vagas encontradas no ciclo."""
    if not vagas:
        return False

    config = carregar_config()
    canais = config.get("canais_notificacao", {})
    email_cfg = canais.get("email", {})

    if not email_cfg.get("ativo", False):
        logger.info("[Dispatcher] E-mail desativado nas configurações. Digest não será enviado.")
        return False

    from perfis import obter_regras_perfil
    regras = obter_regras_perfil("brasil")

    vagas_dict = []
    for v in vagas:
        if hasattr(v, "titulo"):
            v_dict = {
                "titulo": v.titulo,
                "empresa": v.empresa,
                "local": v.local,
                "url": v.link,
                "fonte": v.site,
                "score": v.relevancia if v.relevancia else v.pontuar_relevancia(regras),
                "modalidade": v.modalidade,
            }
            vagas_dict.append(v_dict)
        elif isinstance(v, dict):
            vagas_dict.append(v)

    score_minimo = config.get("score_minimo", "todos")
    if score_minimo not in ("todos", "0", 0, None):
        try:
            limiar = int(score_minimo)
            vagas_dict = [v for v in vagas_dict if (v.get("score") or 5) >= limiar]
        except (ValueError, TypeError):
            pass

    if not vagas_dict:
        logger.info("[Dispatcher] Nenhuma vaga no digest após aplicar o filtro de pontuação mínima.")
        return False

    from notifier.email_notifier import construir_digest_html, enviar_email
    corpo_html = construir_digest_html(vagas_dict)
    assunto = f"JobRadar — {len(vagas_dict)} Nova(s) Vaga(s) Encontrada(s)"

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
        logger.info(f"[Dispatcher] Digest de {len(vagas_dict)} vaga(s) enviado por e-mail com sucesso!")
    else:
        logger.error(f"[Dispatcher] Erro ao enviar digest por e-mail: {msg}")

    return ok


def enviar_digest_email_para_usuario(
    usuario_cfg: dict,
    vagas: list,
    smtp_global: dict | None = None,
) -> bool:
    """Envia o e-mail de resumo consolidado com as vagas selecionadas para o e-mail do usuário informado."""
    import os

    if not vagas:
        return False

    destinatario = (
        usuario_cfg.get("email_destinatario")
        or usuario_cfg.get("email")
        or usuario_cfg.get("canais_notificacao", {}).get("email", {}).get("destinatario")
    )
    if not destinatario or "@" not in destinatario:
        return False

    # Configurações de SMTP: prioriza as do usuário se existirem, senão utiliza as globais de ambiente
    email_cfg = usuario_cfg.get("canais_notificacao", {}).get("email", {})
    smtp_host = email_cfg.get("smtp_host") or os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = email_cfg.get("smtp_port") or int(os.environ.get("EMAIL_SMTP_PORT", 587))
    smtp_user = email_cfg.get("smtp_user") or os.environ.get("EMAIL_SMTP_USER", "")
    smtp_pass = email_cfg.get("smtp_pass") or os.environ.get("EMAIL_SMTP_PASS", "")

    if smtp_global:
        if not smtp_user:
            smtp_user = smtp_global.get("smtp_user", "")
        if not smtp_pass:
            smtp_pass = smtp_global.get("smtp_pass", "")
        if not smtp_host:
            smtp_host = smtp_global.get("smtp_host", "smtp.gmail.com")

    if not smtp_user or not smtp_pass:
        logger.warning(f"[Dispatcher] Credenciais SMTP ausentes para envio ao usuário {destinatario}.")
        return False

    vagas_dict = []
    for v in vagas:
        if hasattr(v, "titulo"):
            v_dict = {
                "titulo": v.titulo,
                "empresa": v.empresa,
                "local": v.local,
                "url": v.link,
                "fonte": v.site,
                "score": v.relevancia if v.relevancia else 5,
                "modalidade": v.modalidade,
                "publicado_em": getattr(v, "publicado_em", "") or "Recente",
            }
            vagas_dict.append(v_dict)
        elif isinstance(v, dict):
            vagas_dict.append(v)

    score_minimo = usuario_cfg.get("score_minimo", "todos")
    if score_minimo not in ("todos", "0", 0, None):
        try:
            limiar = int(score_minimo)
            vagas_dict = [v for v in vagas_dict if (v.get("score") or 5) >= limiar]
        except (ValueError, TypeError):
            pass

    if not vagas_dict:
        return False

    from notifier.email_notifier import construir_digest_html, enviar_email
    corpo_html = construir_digest_html(vagas_dict)
    assunto = f"JobRadar — {len(vagas_dict)} Nova(s) Vaga(s) Encontrada(s)"

    ok, msg = enviar_email(
        destinatario=destinatario,
        assunto=assunto,
        corpo_html=corpo_html,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
    )
    return ok

