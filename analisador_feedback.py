from __future__ import annotations

import re
from config_manager import carregar_config, salvar_config
from logger import get_logger

logger = get_logger()


def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    import unicodedata
    n = unicodedata.normalize("NFD", str(texto))
    sem_acento = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return sem_acento.lower().strip()


def analisar_comentario_feedback(vaga: dict, comentario: str) -> dict:
    """Analisa o comentário fornecido pelo usuário ao dar Thumbs Down em uma vaga.
    Detecta intenção de bloquear a empresa ou o título/cargo específico e atualiza
    as regras em user_config.json.
    """
    if not comentario or not comentario.strip():
        return {"alterado": False, "mensagem": "Feedback registrado sem comentários adicionais."}

    com_norm = _normalizar(comentario)
    empresa_vaga = (vaga.get("empresa") or "").strip()
    titulo_vaga = (vaga.get("titulo") or "").strip()

    cfg = carregar_config()
    empresas_bloqueadas = cfg.get("empresas_bloqueadas", [])
    titulos_bloqueados = cfg.get("titulos_bloqueados", [])

    alterado = False
    mensagens = []

    # 1. Detecção de Bloqueio de Empresa
    deve_bloquear_empresa = False

    if empresa_vaga:
        emp_norm = _normalizar(empresa_vaga)

        palavras_chave_empresa = [
            "empresa", "companhia", "organizacao", "consultoria",
            "dessa empresa", "esta empresa", "da empresa", "bloquear empresa",
            "nao quero vagas da", "odiei essa empresa", "nao gosto da"
        ]

        if emp_norm and (emp_norm in com_norm or any(kw in com_norm for kw in palavras_chave_empresa)):
            deve_bloquear_empresa = True

    if deve_bloquear_empresa and empresa_vaga:
        if not any(_normalizar(e) == _normalizar(empresa_vaga) for e in empresas_bloqueadas):
            empresas_bloqueadas.append(empresa_vaga)
            cfg["empresas_bloqueadas"] = empresas_bloqueadas
            alterado = True
            mensagens.append(f"Empresa '{empresa_vaga}' adicionada à lista de bloqueio.")

    # 2. Detecção de Bloqueio de Título / Cargo
    deve_bloquear_titulo = False
    termo_titulo_para_bloquear = ""

    # Se o comentário for focado na empresa (ex: "não quero vagas dessa empresa"), não assume bloqueio de cargo a menos que explicite cargo/título
    menciona_cargo_explicito = any(kw in com_norm for kw in ["cargo", "titulo", "funcao", "posicao", "nivel", "estagiario", "trainee", "scrum master"])
    
    padrao_cargo = re.search(r"(?:nao quero vagas? (?:do cargo|do titulo|de cargo|de titulo)|cargo de|titulo de|bloquear cargo|bloquear titulo)\s+([a-z0-9\s]+)", com_norm)
    if padrao_cargo:
        extraido = padrao_cargo.group(1).strip()
        if len(extraido) >= 3 and not any(w in extraido for w in ("empresa", "vaga", "esta", "essa")):
            termo_titulo_para_bloquear = extraido
            deve_bloquear_titulo = True

    if not deve_bloquear_titulo and menciona_cargo_explicito:
        deve_bloquear_titulo = True
        termo_titulo_para_bloquear = titulo_vaga

    if deve_bloquear_titulo and termo_titulo_para_bloquear:
        if not any(_normalizar(t) == _normalizar(termo_titulo_para_bloquear) for t in titulos_bloqueados):
            titulos_bloqueados.append(termo_titulo_para_bloquear)
            cfg["titulos_bloqueados"] = titulos_bloqueados
            alterado = True
            mensagens.append(f"Título/Cargo '{termo_titulo_para_bloquear}' adicionado à lista de bloqueio.")

    if alterado:
        salvar_config(cfg)
        from database.database import expurgar_vagas_incompativeis, exportar_jobs_json
        try:
            expurgar_vagas_incompativeis()
            exportar_jobs_json()
        except Exception as e:
            logger.warning(f"[AnalisadorFeedback] Erro ao expurgar banco: {e}")

        msg_final = "Feedback analisado! " + " ".join(mensagens)
        logger.info(f"[AnalisadorFeedback] {msg_final}")
        return {"alterado": True, "mensagem": msg_final, "config": cfg}

    return {"alterado": False, "mensagem": "Feedback registrado com sucesso!"}
