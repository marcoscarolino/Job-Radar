
import os
from dotenv import load_dotenv
from config_manager import carregar_config

load_dotenv()

_usr_cfg = carregar_config()

# Cargo forte: título que só existe mesmo em vaga de dados/BI, sem
# possibilidade real de ser outra área.
KEYWORDS_CARGO_FORTE = _usr_cfg.get("cargos_fortes", [
    "Analista de Dados",
    "Analista BI",
    "Analista de BI",
    "Business Intelligence",
    "Data Analytics",
    "Analista de Analytics",
    "Data Analyst",
    "Desenvolvedor BI",
    "Consultor BI",
    "Analista de Inteligência de Negócios",
    "BI Developer",
    "BI Analyst",
    "Analista de Reporting",
    "Analista de Inteligência de Mercado",
    "Analista de Indicadores",
    "Reporting Analyst",
    "Insights Analyst",
    "Data Insights Analyst",
    "MIS Analyst",
    "Analista de MIS",
    "Assistente de BI",
    "Auxiliar de BI",
    "Analista de Inteligência Comercial",
    "Data Specialist",
    "Data Quality Analyst",
    "Data Intelligence Analyst",
    "BI & Analytics Analyst",
    "Analytics Specialist",
    "Especialista em Dados",
    "Analista de Planejamento e Dados",
    "Analista de Datos",
    "Analítica de Datos",
])

# Cargo ambíguo: título que também é usado em vaga sem nada a ver com dados/BI.
KEYWORDS_CARGO_AMBIGUO = _usr_cfg.get("cargos_ambiguos", [
    "Business Analyst",
    "Analista de Negócios",
    "Business Analytics",
    "Analista de Performance",
])

# Termo que precisa aparecer junto no título quando o cargo é ambíguo.
QUALIFICADORES_DADOS = _usr_cfg.get("qualificadores_dados", [
    "dados",
    "data",
    "bi",
    "sql",
    "power bi",
    "analytics",
    "kpi",
    "dashboard",
    "métricas",
    "reporting",
    "insights",
])

# Ferramenta que aparece como núcleo do título ("Analista de Power BI").
FERRAMENTAS_TITULO = [
    "Power BI",
]

# Palavra de cargo que confirma que a vaga de ferramenta é de análise.
QUALIFICADORES_CARGO = [
    "analista",
    "analyst",
    "especialista",
    "specialist",
    "consultor",
    "consultant",
]

KEYWORDS = KEYWORDS_CARGO_FORTE + KEYWORDS_CARGO_AMBIGUO

TERMOS_CARGO_EXTRA = [
    "power bi",
    "inteligência de mercado",
]

TERMOS_CARGO = sorted(set(k.lower() for k in KEYWORDS) | set(TERMOS_CARGO_EXTRA))

TERMOS_FERRAMENTA = _usr_cfg.get("ferramentas", [
    "sql",
    "python",
    "tableau",
    "qlik",
    "looker",
    "bigquery",
])

TERMOS_BUSCA = sorted(set(TERMOS_CARGO + TERMOS_FERRAMENTA))

TERMOS_POR_CICLO = 10

_cidades_user = _usr_cfg.get("cidades", [
    "Maceió",
    "Recife",
    "Salvador",
    "Aracaju",
    "João Pessoa",
    "Natal",
    "Fortaleza",
])

if _usr_cfg.get("aceitar_remoto", True):
    CIDADES = ["Remoto"] + [c for c in _cidades_user if c.lower() != "remoto"]
else:
    CIDADES = [c for c in _cidades_user if c.lower() != "remoto"]

# MEDIDO: "Data Analyst @ Lisboa" e "Analista de Datos @ Madrid" reprovavam
# na localização, não no cargo — CIDADES acima é whitelist só de cidade
# brasileira, e a expansão de LOCATIONS_LINKEDIN pra Argentina/Chile (ver
# abaixo) passou a trazer vaga presencial/híbrida em Portugal/Espanha de
# vez em quando junto. Lista SEPARADA (não misturada em CIDADES, que
# continua só-Brasil de propósito — ver decisão registrada na criação do
# config_intl.py) com toggle próprio, pra dar pra ligar/desligar esse eixo
# sem mexer no resto do filtro. Canônica aqui porque config_intl.py já
# importa de config.py (não o contrário) — o pipeline internacional reusa
# essa mesma lista em vez de manter uma cópia (risco de divergir, mesmo
# motivo da unificação de _contem_termo/_tem_termo).
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

# Toggle independente do ATIVAR_EIXO_IBERICO de config_intl.py — são dois
# eixos diferentes (esse aqui é do pipeline BR/main.py, aquele é do
# pipeline internacional/main_intl.py), cada um com seu próprio liga/
# desliga, mesmo compartilhando a mesma lista de cidades acima.
#
# DESLIGADO: do mercado internacional, só interessa vaga remota — vaga
# presencial/híbrida em Lisboa/Madrid (o que esse eixo notifica, marcada
# "exploratória") não é o que o usuário quer. CIDADES_EUROPA_IBERICA
# continua definida (não precisa apagar) pra caso o eixo volte a ser
# ligado depois — só o toggle muda.
ATIVAR_EIXO_IBERICO_BR = False

# LinkedInScraper é a única fonte do pipeline BR que também alcança vaga
# fora do Brasil (as outras são portais brasileiros) — mas até aqui rodava
# só com location=Brasil fixo no código (scrapers/linkedin.py:88), então
# essa "porta pra fora" nunca era usada.
#
# Mercado "casa": busca modalidade completa (presencial/híbrida + remoto),
# porque o usuário mora aqui e vaga local de verdade interessa.
LOCATIONS_LINKEDIN = ["Brasil"]

# Mercados adicionais: só busca REMOTA (f_WT=2) — vaga presencial/híbrida
# num país onde o usuário não mora não serve, então nem faz sentido gastar
# a passada nacional ali (era puro desperdício: Argentina/Chile já rodavam
# as duas passadas antes, mas a nacional nunca batia em CIDADES mesmo,
# que é só cidade brasileira). Espanhol ou português — mesmo critério do
# pipeline internacional. Lista reaproveita exatamente os países já usados
# e testados ao vivo no endpoint do LinkedIn em config_intl.py
# (LOCATIONS_INTL) — evita arriscar nome de país nunca testado (grafia
# errada ou região que o LinkedIn não resolve como location de verdade,
# como já visto com "LATAM"/"Latin America").
LOCATIONS_LINKEDIN_REMOTO_APENAS = ["Argentina", "Chile", "México", "Colômbia", "Espanha", "Portugal"]

# Mercado que a vaga remota precisa aceitar pra contar, quando o texto de
# local DECLARA um escopo geográfico ("Remote — US only", "Remote — India").
# Ver Job.escopo_remoto/RegrasFiltro.mercados_remoto_aceitos em job.py — sem
# isso, uma vaga remota só pra outro país passava igual a uma remota de
# verdade pro Brasil. Vaga remota SEM escopo declarado no texto (a grande
# maioria) continua batendo normalmente, isso só filtra quando a fonte
# EXPLICITA um mercado incompatível.
#
# MEDIDO: Argentina/Chile/México/Colômbia ENTRAM nominalmente agora — a
# suposição de que "LATAM" cobria os quatro como guarda-chuva só valia
# enquanto extrair_escopo_remoto resolvia o texto pra "LATAM" literal.
# Depois que passou a reconhecer cidade (Buenos Aires/Santiago/Cidade do
# México/Bogotá — ver _CIDADES_MERCADO em job.py), o escopo passou a
# resolver pro PAÍS específico, não mais pro guarda-chuva — e o país
# específico nunca esteve nessa lista. Resultado: LOCATIONS_LINKEDIN_
# REMOTO_APENAS pagava o custo de buscar nesses 4 países e o filtro
# descartava tudo que a busca trazia de lá. "LATAM" continua na lista pra
# quando o texto disser isso literalmente (guarda-chuva de verdade, não
# substituto de nome de país). Portugal e Espanha entraram nominalmente
# pelo mesmo motivo, desde antes.
MERCADOS_REMOTO_ACEITOS = ["Brasil", "LATAM", "Argentina", "Chile", "México", "Colômbia", "Portugal", "Espanha"]

INTERVALO_MINUTOS = int(os.getenv("INTERVALO_MINUTOS", 180))

# Digest ranqueado (item 08): vaga com Job.pontuar_relevancia() >= este
# limiar notifica na hora (como sempre foi); abaixo disso, fica na fila do
# digest diário — ver _enviar_digest_diario em main.py.
#
# MEDIDO: rodei o score contra as ~305 vagas do jobs.db real que ainda
# batem as regras atuais. Distribuição: score 4 (2%), 5 (24%), 6 (67%),
# 7 (5%), 8 (2%) — nada em 9-10 na amostra (exige acertar praticamente
# todo sinal ao mesmo tempo: cargo forte + ferramenta + senioridade alvo +
# mercado confirmado). Limiar 7 deixa ~7% imediata e ~93% no digest — bate
# com o pedido ("vaga de score alto na hora, resto agrupado"); 6 deixava
# 74% imediata (pouca redução de ruído); 8 deixava só 2% (digest com
# praticamente tudo, quase nenhuma vaga "excelente" se destacando na hora).
LIMIAR_DIGEST_IMEDIATO = 7

# Hora UTC em que o digest diário dispara (uma vez por perfil, por dia —
# ver _enviar_digest_diario). 0 = meia-noite UTC = 21h em Brasília (UTC-3).
# O cron do workflow (0 */3 * * *) já passa por essa hora exata todo dia,
# então não precisa de agendamento à parte.
DIGEST_HORA_UTC = 0

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "jobs.db")