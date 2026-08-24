import os
from dotenv import load_dotenv
from config_manager import carregar_config

load_dotenv()


def obter_cargos_fortes() -> list[str]:
    cfg = carregar_config()
    return cfg.get("cargos_fortes", ["Gerente de Projetos", "Project Manager"])


def obter_cargos_ambiguos() -> list[str]:
    cfg = carregar_config()
    return cfg.get("cargos_ambiguos", [])


def obter_qualificadores_dados() -> list[str]:
    cfg = carregar_config()
    return cfg.get("qualificadores_dados", ["pmp", "scrum", "agile", "gestão", "projetos", "certificação", "curso"])


def obter_ferramentas() -> list[str]:
    cfg = carregar_config()
    return cfg.get("ferramentas", [])


def obter_termos_busca() -> list[str]:
    cargos = set(k.lower() for k in (obter_cargos_fortes() + obter_cargos_ambiguos()))
    ferramentas = set(f.lower() for f in obter_ferramentas())
    res = sorted(set(cargos | ferramentas))
    return res if res else ["gerente de projetos", "project manager"]


def obter_cidades() -> list[str]:
    cfg = carregar_config()
    cidades_usr = cfg.get("cidades", ["São Paulo", "Recife"])
    if cfg.get("aceitar_remoto", True):
        return ["Remoto"] + [c for c in cidades_usr if c.lower() != "remoto"]
    return [c for c in cidades_usr if c.lower() != "remoto"]


# Aliases para retrocompatibilidade
KEYWORDS_CARGO_FORTE = obter_cargos_fortes()
KEYWORDS_CARGO_AMBIGUO = obter_cargos_ambiguos()
QUALIFICADORES_DADOS = obter_qualificadores_dados()
FERRAMENTAS_TITULO = ["Power BI"]
QUALIFICADORES_CARGO = ["analista", "analyst", "especialista", "specialist", "consultor", "consultant", "gerente", "manager", "coordenador"]
KEYWORDS = KEYWORDS_CARGO_FORTE + KEYWORDS_CARGO_AMBIGUO
TERMOS_CARGO = sorted(set(k.lower() for k in KEYWORDS))
TERMOS_FERRAMENTA = obter_ferramentas()
TERMOS_BUSCA = obter_termos_busca()
TERMOS_POR_CICLO = 10
CIDADES = obter_cidades()

CIDADES_EUROPA_IBERICA = [
    "Portugal",
    "Lisboa",
    "Porto",
    "Braga",
    "Espanha",
    "España",
    "Spain",
    "Madrid",
    "Barcelona",
    "Valencia",
]

ATIVAR_EIXO_IBERICO_BR = False
LOCATIONS_LINKEDIN = ["Brasil"]
LOCATIONS_LINKEDIN_REMOTO_APENAS = ["Argentina", "Chile", "México", "Colômbia", "Espanha", "Portugal"]
MERCADOS_REMOTO_ACEITOS = ["Brasil", "LATAM", "Argentina", "Chile", "México", "Colômbia", "Portugal", "Espanha"]

INTERVALO_MINUTOS = int(os.getenv("INTERVALO_MINUTOS", 180))
LIMIAR_DIGEST_IMEDIATO = 7
DIGEST_HORA_UTC = 0

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "jobs.db")