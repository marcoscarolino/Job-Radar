"""Módulo de integração com o Firebase Admin SDK (Cloud Firestore & Authentication)
para suporte multi-usuário no Job Radar.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logger import get_logger

logger = get_logger()

_firebase_app = None
_firestore_db = None


def inicializar_firebase() -> Any:
    """Inicializa o Firebase Admin SDK utilizando credenciais de Service Account.
    Procura em variáveis de ambiente ou arquivo local em data/firebase_credentials.json.
    """
    global _firebase_app, _firestore_db

    if _firestore_db is not None:
        return _firestore_db

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            _firestore_db = firestore.client()
            return _firestore_db

        cred = None

        # 1. Variável de ambiente com JSON direto (usado no GitHub Actions / Secrets)
        json_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY") or os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if json_env:
            try:
                cert_dict = json.loads(json_env)
                cred = credentials.Certificate(cert_dict)
            except Exception as e:
                logger.warning(f"[Firebase] Falha ao processar FIREBASE_SERVICE_ACCOUNT_KEY como JSON: {e}")

        # 2. Caminho de arquivo local ou GOOGLE_APPLICATION_CREDENTIALS
        if cred is None:
            caminho_cred = (
                os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                or str(Path(__file__).parent / "data" / "firebase_credentials.json")
            )
            if os.path.exists(caminho_cred):
                cred = credentials.Certificate(caminho_cred)

        # 3. Inicialização padrão (Google Application Default Credentials se disponível)
        if cred is not None:
            _firebase_app = firebase_admin.initialize_app(cred)
            _firestore_db = firestore.client()
            logger.info("[Firebase] Firebase Admin SDK inicializado com sucesso via Service Account.")
        else:
            logger.debug("[Firebase] Nenhuma credencial do Firebase Admin encontrada. Operando em modo local padrão.")
            return None

        return _firestore_db
    except ImportError:
        logger.debug("[Firebase] Pacote 'firebase-admin' não instalado. Operando em modo local.")
        return None
    except Exception as e:
        logger.warning(f"[Firebase] Não foi possível inicializar o Firebase Admin: {e}")
        return None


def is_firebase_disponivel() -> bool:
    """Retorna True se o Firestore Admin estiver conectado e operacional."""
    return inicializar_firebase() is not None


def deve_enviar_alerta(
    frequencia: str,
    ultimo_envio_iso: str | None = None,
    agora: datetime | None = None,
) -> bool:
    """Verifica se o e-mail de alerta deve ser disparado para o usuário neste ciclo
    baseado na frequência configurada e no histórico de envio.

    Frequências suportadas:
    - 'a_cada_3_horas' (ou 'sempre'): Envia a cada ciclo em que novas vagas forem detectadas.
    - 'diario': Envia no máximo 1 vez ao dia.
    - 'semanal': Envia no máximo 1 vez por semana, especificamente às segundas-feiras (weekday == 0).
    """
    if agora is None:
        agora = datetime.now(timezone.utc)

    frequencia = (frequencia or "a_cada_3_horas").lower().strip()

    if frequencia in ("a_cada_3_horas", "3h", "todos_ciclos", "sempre"):
        return True

    if not ultimo_envio_iso:
        # Se nunca enviou antes, é elegível no ciclo atual
        if frequencia == "semanal":
            return agora.weekday() == 0  # 0 = Segunda-feira
        return True

    try:
        ultimo_envio = datetime.fromisoformat(ultimo_envio_iso.replace("Z", "+00:00"))
    except Exception:
        return True

    data_agora = agora.date()
    data_ultimo = ultimo_envio.date()

    if frequencia in ("diario", "1_vez_ao_dia"):
        # Elegível se ainda não enviou hoje
        return data_agora > data_ultimo

    if frequencia in ("semanal", "1_vez_na_semana"):
        # Elegível se hoje for segunda-feira (0) e ainda não enviou hoje
        if agora.weekday() == 0 and data_agora > data_ultimo:
            return True
        return False

    return True


def obter_todos_usuarios_ativos() -> list[dict]:
    """Recupera todos os perfis de usuários com configurações ativas no Cloud Firestore."""
    db = inicializar_firebase()
    if db is None:
        return []

    usuarios = []
    try:
        users_ref = db.collection("users")
        docs = users_ref.stream()

        for doc in docs:
            user_data = doc.to_dict() or {}
            user_id = doc.id
            user_data["uid"] = user_id

            # Se as preferências estiverem em subcoleção config/geral, mescla
            try:
                sub_doc = users_ref.document(user_id).collection("config").document("geral").get()
                if sub_doc.exists:
                    cfg_dict = sub_doc.to_dict() or {}
                    user_data.update(cfg_dict)
            except Exception:
                pass

            # Garante campos fundamentais
            email_dest = (
                user_data.get("email_destinatario")
                or user_data.get("email")
                or user_data.get("canais_notificacao", {}).get("email", {}).get("destinatario")
            )

            # Só inclui usuários que possuem e-mail válido configurado
            if email_dest and "@" in email_dest:
                user_data["email_destinatario"] = email_dest.strip()
                usuarios.append(user_data)

        logger.info(f"[Firebase] {len(usuarios)} usuário(s) ativo(s) carregado(s) do Firestore.")
        return usuarios
    except Exception as e:
        logger.error(f"[Firebase] Erro ao carregar usuários do Firestore: {e}")
        return []


def atualizar_ultimo_envio(uid: str, data_hora_iso: str | None = None) -> bool:
    """Atualiza a data/hora do último envio de e-mail de alerta do usuário no Firestore."""
    db = inicializar_firebase()
    if db is None or not uid:
        return False

    if data_hora_iso is None:
        data_hora_iso = datetime.now(timezone.utc).isoformat()

    try:
        db.collection("users").document(uid).set(
            {"ultimo_envio_email": data_hora_iso},
            merge=True,
        )
        return True
    except Exception as e:
        logger.warning(f"[Firebase] Erro ao atualizar último envio para usuário {uid}: {e}")
        return False
