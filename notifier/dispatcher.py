from __future__ import annotations

import json
import requests
from config_manager import carregar_config
from logger import get_logger
from notifier.email_notifier import enviar_email
from notifier.telegram import enviar_mensagem as enviar_telegram

logger = get_logger()


def enviar_notificacao_multicanal(
    texto_simples: str,
    assunto: str = "📡 Nova Vaga Encontrada pelo JobRadar",
    corpo_html: str | None = None,
    reply_markup: dict | None = None,
) -> dict[str, bool]:
    """Dispara a notificação para todos os canais ativados no user_config.json."""
    config = carregar_config()
    canais = config.get("canais_notificacao", {})
    resultados = {}

    # 1. Telegram
    tg_cfg = canais.get("telegram", {})
    if tg_cfg.get("ativo", True):
        # Se bot_token/chat_id customizados foram informados na UI, envia por eles
        token = tg_cfg.get("bot_token")
        chat_id = tg_cfg.get("chat_id")
        if token and chat_id:
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {"chat_id": chat_id, "text": texto_simples, "parse_mode": "HTML"}
                if reply_markup:
                    payload["reply_markup"] = json.dumps(reply_markup)
                res = requests.post(url, data=payload, timeout=10)
                resultados["telegram"] = res.status_code == 200
            except Exception as e:
                logger.error(f"[Dispatcher] Erro ao enviar Telegram customizado: {e}")
                resultados["telegram"] = False
        else:
            # Usa o envio padrão do telegram.py (.env)
            resultados["telegram"] = enviar_telegram(texto_simples, reply_markup)

    # 2. E-mail (SMTP)
    email_cfg = canais.get("email", {})
    if email_cfg.get("ativo", False):
        html_msg = corpo_html or f"<pre style='font-family: sans-serif;'>{texto_simples}</pre>"
        resultados["email"] = enviar_email(
            destinatario=email_cfg.get("destinatario", ""),
            assunto=assunto,
            corpo_html=html_msg,
            smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
            smtp_port=email_cfg.get("smtp_port", 587),
            smtp_user=email_cfg.get("smtp_user", ""),
            smtp_pass=email_cfg.get("smtp_pass", ""),
        )

    # 3. Webhook (Discord / Slack / Teams)
    wh_cfg = canais.get("webhook", {})
    if wh_cfg.get("ativo", False) and wh_cfg.get("url"):
        try:
            url = wh_cfg.get("url")
            payload = {"content": texto_simples, "text": texto_simples}
            res = requests.post(url, json=payload, timeout=10)
            resultados["webhook"] = res.status_code in (200, 204)
        except Exception as e:
            logger.error(f"[Dispatcher] Erro ao enviar Webhook: {e}")
            resultados["webhook"] = False

    # 4. WhatsApp (via CallMeBot API pública / Twilio / Custom HTTP endpoint)
    wa_cfg = canais.get("whatsapp", {})
    if wa_cfg.get("ativo", False) and wa_cfg.get("numero"):
        try:
            numero = wa_cfg.get("numero").replace("+", "").replace("-", "").replace(" ", "")
            api_key = wa_cfg.get("api_key", "")
            # Exemplo via CallMeBot API (Gratuito para WhatsApp)
            url = f"https://api.callmebot.com/whatsapp.php?phone={numero}&text={requests.utils.quote(texto_simples)}&apikey={api_key}"
            res = requests.get(url, timeout=10)
            resultados["whatsapp"] = res.status_code == 200
        except Exception as e:
            logger.error(f"[Dispatcher] Erro ao enviar WhatsApp: {e}")
            resultados["whatsapp"] = False

    return resultados
