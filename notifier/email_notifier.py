from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import get_logger

logger = get_logger()


def construir_digest_html(vagas: list[dict]) -> str:
    """Monta o HTML do e-mail consolidando todas as vagas agrupadas por score de relevância."""
    vagas_altas = [v for v in vagas if (v.get("score") or v.get("relevancia") or 5) >= 8]
    vagas_medias = [v for v in vagas if 5 <= (v.get("score") or v.get("relevancia") or 5) < 8]
    vagas_baixas = [v for v in vagas if (v.get("score") or v.get("relevancia") or 5) < 5]

    def render_bloco(titulo: str, cor_borda: str, lista: list[dict]) -> str:
        if not lista:
            return ""
        items_html = ""
        for v in lista:
            score_val = v.get("score") or v.get("relevancia") or 5
            empresa = v.get("empresa") or "Não informada"
            local = v.get("local") or "Brasil"
            modalidade = v.get("modalidade") or ""
            link = v.get("url") or v.get("link") or "#"
            tit = v.get("titulo") or "Vaga"
            fonte = v.get("fonte") or v.get("site") or "Portal"
            mod_badge = f" ({modalidade})" if modalidade else ""

            items_html += f"""
            <li style="margin-bottom: 12px; font-size: 14px;">
                <strong>{tit}</strong> — {empresa} <span style="color: #64748b;">({local}{mod_badge})</span><br>
                <span style="font-size: 12px; color: #475569;">Score: {score_val}/10 | Fonte: {fonte}</span> — 
                <a href="{link}" target="_blank" style="color: #2563eb; font-weight: bold; text-decoration: none;">Ver Vaga &rarr;</a>
            </li>
            """
        return f"""
        <div style="margin-bottom: 24px;">
            <h3 style="color: {cor_borda}; border-bottom: 2px solid {cor_borda}; padding-bottom: 4px; font-family: sans-serif;">{titulo} ({len(lista)})</h3>
            <ul style="padding-left: 20px; color: #1e293b;">
                {items_html}
            </ul>
        </div>
        """

    html = f"""
    <div style="font-family: 'Inter', system-ui, sans-serif; color: #0f172a; max-width: 650px; margin: 0 auto; background: #ffffff; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px;">
        <h2 style="color: #2563eb; font-family: sans-serif; margin-top: 0;">JobRadar — Resumo de Vagas Encontradas</h2>
        <p style="color: #475569; font-size: 14px;">Foram identificadas <strong>{len(vagas)} nova(s) vaga(s)</strong> elegíveis no último ciclo de varredura. Confira a lista consolidada abaixo:</p>
        
        {render_bloco("Alta Relevância (Score 8 - 10)", "#059669", vagas_altas)}
        {render_bloco("Média Relevância (Score 5 - 7)", "#d97706", vagas_medias)}
        {render_bloco("Outras Oportunidades (Score 1 - 4)", "#64748b", vagas_baixas)}

        <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 24px;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center;">Alertas automáticos gerados pelo JobRadar</p>
    </div>
    """
    return html


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
        destinatarios_lista = [d.strip() for d in destinatario.split(",") if d.strip()]
        if not destinatarios_lista:
            logger.warning("[EmailNotifier] Nenhum destinatário válido informado.")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"JobRadar Alertas <{smtp_user}>"
        msg["To"] = ", ".join(destinatarios_lista)

        part = MIMEText(corpo_html, "html", "utf-8")
        msg.attach(part)

        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, destinatarios_lista, msg.as_string())

        logger.info(f"[EmailNotifier] E-mail enviado com sucesso para {', '.join(destinatarios_lista)}")
        return True
    except Exception as e:
        logger.error(f"[EmailNotifier] Erro ao enviar e-mail para {destinatario}: {e}")
        return False

