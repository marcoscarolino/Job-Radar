from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import get_logger

logger = get_logger()


def enviar_email(
    destinatario: str,
    assunto: str,
    corpo_html: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_pass: str = "",
) -> bool:
    """Envia um e-mail formatado via SMTP (ex: Gmail, Outlook, SendGrid, Mailtrap)."""
    if not destinatario or not smtp_user or not smtp_pass:
        logger.warning("[EmailNotifier] Configurações de SMTP ou destinatário ausentes. Pulando envio.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"JobRadar Alertas <{smtp_user}>"
        msg["To"] = destinatario

        part = MIMEText(corpo_html, "html", "utf-8")
        msg.attach(part)

        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [destinatario], msg.as_string())

        logger.info(f"[EmailNotifier] E-mail enviado com sucesso para {destinatario}")
        return True
    except Exception as e:
        logger.error(f"[EmailNotifier] Erro ao enviar e-mail para {destinatario}: {e}")
        return False
