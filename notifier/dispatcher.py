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


def enviar_digest_email_multicanal(vagas: list[dict]) -> bool:
    """Envia um ÚNICO e-mail contendo a lista completa de todas as vagas categorizadas pela pontuação."""
    if not vagas:
        return False

    config = carregar_config()
    score_minimo = config.get("score_minimo", "todos")
    if score_minimo not in ("todos", "0", 0, None):
        try:
            limiar = int(score_minimo)
            vagas = [v for v in vagas if (v.get("score") or v.get("relevancia") or 5) >= limiar]
        except (ValueError, TypeError):
            pass

    if not vagas:
        return False

    canais = config.get("canais_notificacao", {})
    email_cfg = canais.get("email", {})

    if not email_cfg.get("ativo", False):
        return False

    from notifier.email_notifier import construir_digest_html, enviar_email
    corpo_html = construir_digest_html(vagas)
    assunto = f"JobRadar — Resumo de {len(vagas)} Vaga(s) Encontrada(s)"

    ok, _ = enviar_email(
        destinatario=email_cfg.get("destinatario", ""),
        assunto=assunto,
        corpo_html=corpo_html,
        smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
        smtp_port=email_cfg.get("smtp_port", 587),
        smtp_user=email_cfg.get("smtp_user", ""),
        smtp_pass=email_cfg.get("smtp_pass", ""),
    )
    return ok
