import copy
import json
import os
from pathlib import Path

# Caminhos para arquivos JSON de configuração
CONFIG_PATH = Path(__file__).parent / "data" / "user_config.json"
LOCAL_CONFIG_PATH = Path(__file__).parent / "data" / "local_user_config.json"

DEFAULT_CONFIG = {
    "score_minimo": "todos",  # "todos", "5", "8"
    "modalidades_aceitas": {
        "remoto": True,
        "hibrido": True,
        "presencial": True,
    },
    "preferencia_modalidade": "remoto",  # "remoto", "hibrido", "presencial" ou "sem_preferencia"
    "senioridades_alvo": ["Júnior", "Pleno", "Sênior"],
    "cargos_fortes": [
        "Gerente de Projetos",
        "Project Manager",
        "Product Designer",
        "Analista de Dados",
    ],
    "cargos_ambiguos": [
        "Coordenador de Projetos",
        "Scrum Master",
    ],
    "ferramentas": [
        "pmp",
        "scrum",
    ],
    "qualificadores_dados": [
        "pmp",
        "scrum",
        "agile",
        "gestão",
        "projetos",
        "certificação",
        "curso",
    ],
    "cidades": [
        "São Paulo",
        "Recife",
        "Rio de Janeiro",
        "Brasil",
    ],
    "aceitar_remoto": True,
    "canais_notificacao": {
        "email": {
            "ativo": False,
            "destinatario": "",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
        },
    },
    "scrapers_ativos": {
        "linkedin": True,
        "gupy": True,
        "indeed": True,
        "solides": True,
        "catho": True,
        "geekhunter": True,
        "trampos": True,
        "jobs99": True,
        "weworkremotely": True,
    },
}


def carregar_config() -> dict:
    """Carrega as configurações salvas em local_user_config.json ou user_config.json.
    Se o arquivo não existir, retorna as configurações padrão (DEFAULT_CONFIG).
    """
    is_default_path = CONFIG_PATH == (Path(__file__).parent / "data" / "user_config.json")
    if is_default_path:
        target_path = LOCAL_CONFIG_PATH if LOCAL_CONFIG_PATH.exists() else CONFIG_PATH
    else:
        target_path = CONFIG_PATH

    if not target_path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        config_completa = copy.deepcopy(DEFAULT_CONFIG)
        for k, v in data.items():
            if k in ("scrapers_ativos", "modalidades_aceitas", "canais_notificacao") and isinstance(v, dict):
                subdict = copy.deepcopy(DEFAULT_CONFIG.get(k, {}))
                subdict.update(v)
                config_completa[k] = subdict
            else:
                config_completa[k] = v

        # Suporte a variáveis de ambiente para execução em nuvem / GitHub Actions (Gmail/SMTP)
        em_cfg = config_completa.get("canais_notificacao", {}).get("email", {})
        env_dest = os.environ.get("EMAIL_DESTINATARIO")
        env_user = os.environ.get("EMAIL_SMTP_USER")
        env_pass = os.environ.get("EMAIL_SMTP_PASS")
        if env_dest and env_user and env_pass:
            em_cfg["ativo"] = True
            em_cfg["destinatario"] = env_dest
            em_cfg["smtp_user"] = env_user
            em_cfg["smtp_pass"] = env_pass
            em_cfg["smtp_host"] = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
            em_cfg["smtp_port"] = int(os.environ.get("EMAIL_SMTP_PORT", 587))
            config_completa["canais_notificacao"]["email"] = em_cfg

        return config_completa
    except Exception:
        return copy.deepcopy(DEFAULT_CONFIG)


def salvar_config(novas_config: dict) -> dict:
    """Valida e salva as novas configurações locais do usuário em data/local_user_config.json."""
    target_path = LOCAL_CONFIG_PATH if CONFIG_PATH == (Path(__file__).parent / "data" / "user_config.json") else CONFIG_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    config_atual = carregar_config()
    for k in DEFAULT_CONFIG.keys():
        if k in novas_config:
            if k in ("scrapers_ativos", "modalidades_aceitas", "canais_notificacao") and isinstance(novas_config[k], dict):
                config_atual[k].update(novas_config[k])
            else:
                config_atual[k] = novas_config[k]

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(config_atual, f, ensure_ascii=False, indent=2)

    return config_atual
