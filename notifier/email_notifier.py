from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import get_logger

logger = get_logger()


def construir_digest_html(vagas: list[dict]) -> str:
    """Monta o HTML do e-mail consolidando todas as vagas agrupadas por pontuação de relevância."""
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
                <span style="font-size: 12px; color: #475569;">Pontuação: {score_val}/10 | Fonte: {fonte}</span> — 
                <a href="{link}" target="_blank" style="color: #0284c7; font-weight: bold; text-decoration: none;">Ver Vaga &rarr;</a>
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
        <h2 style="color: #0284c7; font-family: sans-serif; margin-top: 0;">JobRadar — Resumo de Vagas Encontradas</h2>
        <p style="color: #475569; font-size: 14px;">Foram identificadas <strong>{len(vagas)} nova(s) vaga(s)</strong> elegíveis no último ciclo de varredura. Confira a lista consolidada abaixo:</p>
        
        {render_bloco("Alta Relevância (Pontuação 8 - 10)", "#15803d", vagas_altas)}
        {render_bloco("Média Relevância (Pontuação 5 - 7)", "#b45309", vagas_medias)}
        {render_bloco("Outras Oportunidades (Pontuação 1 - 4)", "#475569", vagas_baixas)}

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
) -> tuple[bool, str]:
    """Envia um e-mail formatado via SMTP (ex: Gmail, Outlook, SendGrid, Mailtrap)."""
    if not destinatario or not destinatario.strip():
        return False, "O campo 'Seu E-mail de Destino' não foi preenchido nas configurações."
    if not smtp_user or not smtp_user.strip():
        return False, "O campo 'Usuário SMTP' não foi preenchido nas configurações."
    if not smtp_pass or not smtp_pass.strip():
        return False, "O campo 'Senha de App SMTP' não foi preenchido nas configurações."

    try:
        destinatarios_lista = [d.strip() for d in destinatario.split(",") if d.strip()]
        if not destinatarios_lista:
            return False, "Nenhum e-mail de destino válido foi informado."

        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"JobRadar Alertas <{smtp_user.strip()}>"
        msg["To"] = ", ".join(destinatarios_lista)

        part = MIMEText(corpo_html, "html", "utf-8")
        msg.attach(part)

        porta = int(smtp_port) if smtp_port else 587
        host = smtp_host.strip() if smtp_host else "smtp.gmail.com"

        with smtplib.SMTP(host, porta, timeout=12) as server:
            server.starttls()
            server.login(smtp_user.strip(), smtp_pass.strip())
            server.sendmail(smtp_user.strip(), destinatarios_lista, msg.as_string())

        msg_sucesso = f"E-mail enviado com sucesso para {', '.join(destinatarios_lista)}!"
        logger.info(f"[EmailNotifier] {msg_sucesso}")
        return True, msg_sucesso
    except smtplib.SMTPAuthenticationError as e:
        msg_erro = "Falha de autenticação SMTP: Usuário ou Senha incorretos. Se estiver usando Gmail, acesse a Conta Google > Segurança > Senhas de app e crie uma senha de 16 caracteres."
        logger.error(f"[EmailNotifier] {msg_erro} ({e})")
        return False, msg_erro
    except smtplib.SMTPConnectError as e:
        msg_erro = f"Não foi possível conectar ao servidor SMTP ({smtp_host}:{smtp_port}). Verifique sua conexão e o endereço do servidor."
        logger.error(f"[EmailNotifier] {msg_erro} ({e})")
        return False, msg_erro
    except Exception as e:
        msg_erro = f"Erro no envio de e-mail: {e}"
        logger.error(f"[EmailNotifier] {msg_erro}")
        return False, msg_erro
