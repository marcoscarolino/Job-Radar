from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import get_logger

logger = get_logger()


def construir_digest_html(vagas: list[dict]) -> str:
    """Monta o HTML do e-mail consolidando todas as vagas agrupadas por pontuação de relevância,
    seguindo rigorosamente a identidade visual do JobRadar (Onest, Olive & Lime 400, Target Icon)."""
    vagas_altas = [v for v in vagas if (v.get("score") or v.get("relevancia") or 5) >= 8]
    vagas_medias = [v for v in vagas if 5 <= (v.get("score") or v.get("relevancia") or 5) < 8]
    vagas_baixas = [v for v in vagas if (v.get("score") or v.get("relevancia") or 5) < 5]

    def extrair_data(v: dict) -> str:
        raw = v.get("publicado_em") or v.get("criado_em") or ""
        if not raw:
            return "Recente"
        limpo = raw.replace("publicada em:", "").replace("Publicada em:", "").strip()
        return limpo or "Recente"

    def render_bloco(titulo_secao: str, lista: list[dict]) -> str:
        if not lista:
            return ""
        items_html = ""
        for v in lista:
            score_val = v.get("score") or v.get("relevancia") or 5
            empresa = v.get("empresa") or "Empresa confidencial"
            local = v.get("local") or "Brasil"
            modalidade = v.get("modalidade") or ""
            link = v.get("url") or v.get("link") or "#"
            tit = v.get("titulo") or "Vaga"
            fonte = v.get("fonte") or v.get("site") or "Portal"
            divulgada_em = extrair_data(v)

            mod_texto = f" • {modalidade}" if modalidade else ""

            if score_val >= 8:
                score_badge_style = "background-color: #a3e635; color: #1e2019; border: 0;"
            elif score_val >= 5:
                score_badge_style = "background-color: #fef3c7; color: #78350f; border: 0;"
            else:
                score_badge_style = "background-color: #f0f2ea; color: #4b5338; border: 0;"

            items_html += f"""
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 14px; background-color: #f8f9f5; border: 1px solid #e1e5d5; border-radius: 14px; padding: 16px; box-sizing: border-box;">
                <tr>
                    <td style="padding-bottom: 6px;">
                        <table width="100%" border="0" cellspacing="0" cellpadding="0">
                            <tr>
                                <td align="left" style="font-size: 14px; font-weight: 500; color: #3f4530; line-height: 1.3;">
                                    {tit}
                                </td>
                                <td align="right" style="vertical-align: top; width: 65px;">
                                    <span style="display: inline-block; padding: 3px 8px; border-radius: 8px; font-size: 14px; font-weight: 500; {score_badge_style}">
                                        {score_val}/10
                                    </span>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td style="font-size: 14px; font-weight: 400; color: #5c6743; padding-bottom: 12px;">
                        {empresa} • {local}{mod_texto} • {fonte}
                    </td>
                </tr>
                <tr>
                    <td>
                        <table width="100%" border="0" cellspacing="0" cellpadding="0">
                            <tr>
                                <td align="left" style="font-size: 12px; font-weight: 400; color: #768456;">
                                    {divulgada_em}
                                </td>
                                <td align="right">
                                    <a href="{link}" target="_blank" style="display: inline-block; background-color: #a3e635; color: #1e2019; padding: 6px 14px; border-radius: 12px; font-size: 14px; font-weight: 500; text-decoration: none; border: 0;">
                                        Ver vaga &rarr;
                                    </a>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
            """
        return f"""
        <div style="margin-bottom: 28px;">
            <h3 style="color: #3f4530; font-size: 18px; font-weight: 500; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e1e5d5; padding-bottom: 8px;">
                {titulo_secao} ({len(lista)})
            </h3>
            {items_html}
        </div>
        """

    # URL pública hospedada no repositório GitHub para renderização universal em todos os clientes de e-mail (Gmail, Outlook, Apple Mail)
    logo_url = "https://raw.githubusercontent.com/marcoscarolino/Job-Radar/main/assets/logo.png"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JobRadar — Resumo de Vagas</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9f5; font-family: 'Onest', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; -webkit-font-smoothing: antialiased;">
<table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8f9f5; padding: 24px 12px;">
    <tr>
        <td align="center">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 620px; background-color: #ffffff; border: 1px solid #e1e5d5; border-radius: 16px; padding: 28px; box-sizing: border-box;">
                <!-- Header Logo -->
                <tr>
                    <td style="padding-bottom: 20px; border-bottom: 1px solid #f0f2ea;">
                        <table border="0" cellspacing="0" cellpadding="0">
                            <tr>
                                <td style="vertical-align: middle; padding-right: 8px;">
                                    <img src="{logo_url}" width="26" height="26" alt="🎯" style="display: block; border: 0; width: 26px; height: 26px; outline: none; text-decoration: none;">
                                </td>
                                <td style="font-size: 24px; font-weight: 600; color: #3f4530; line-height: 1; vertical-align: middle;">
                                    JobRadar
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <!-- Descrição da Varredura -->
                <tr>
                    <td style="padding-top: 20px; padding-bottom: 24px; font-size: 14px; font-weight: 400; color: #5c6743; line-height: 1.5;">
                        Foram identificadas <strong style="color: #3f4530; font-weight: 500;">{len(vagas)} vaga(s)</strong> elegíveis no último ciclo de varredura. Confira a lista consolidada abaixo:
                    </td>
                </tr>
                <!-- Blocos de Vagas -->
                <tr>
                    <td>
                        {render_bloco("Alta relevância", vagas_altas)}
                        {render_bloco("Média relevância", vagas_medias)}
                        {render_bloco("Outras oportunidades", vagas_baixas)}
                    </td>
                </tr>
                <!-- Rodapé -->
                <tr>
                    <td align="center" style="padding-top: 24px; border-top: 1px solid #f0f2ea; font-size: 12px; font-weight: 400; color: #768456; line-height: 1.6;">
                        Alertas automáticos gerados pelo JobRadar<br>
                        <span style="font-size: 11px; color: #94a273;">
                            Desenvolvido por <a href="https://www.linkedin.com/in/marcoscarolino/" target="_blank" style="color: #5c6743; text-decoration: underline; font-weight: 500;">Marcos Carolino</a>
                        </span>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>
</body>
</html>
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
