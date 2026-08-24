from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
import hashlib
import re
import unicodedata


def _normalizar(texto: str) -> str:
    """Minúsculo e sem acento, pra comparação não depender de site nenhum
    escrever "Maceio"/"Maceió", "e-commerce"/"ecommerce" etc. de forma
    diferente da nossa lista de keywords/cidades."""
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _contem_termo(termo: str, texto: str, aceitar_plural: bool = False, aceitar_sufixo: bool = True) -> bool:
    """Substring com borda de palavra inicial. Permite sufixos comuns de cargos (ex: 'product design' -> 'product designer', 'analista' -> 'analistas')."""
    if not termo or not texto:
        return False
    if len(termo) <= 2:
        return re.search(rf"(?<!\w){re.escape(termo)}(?!\w)", texto) is not None
    if aceitar_sufixo or aceitar_plural:
        return re.search(rf"(?<!\w){re.escape(termo)}", texto) is not None
    return re.search(rf"(?<!\w){re.escape(termo)}(?!\w)", texto) is not None


# Vocabulário de "é vaga remota" usado no campo local. Antes só tinha
# "remot" + "home office" — "Remote" (inglês) só passava por acidente, por
# conter a substring "remot", e faltava vocabulário que não compartilha
# essa raiz: "teletrabalho" (termo padrão em Portugal), "work from home",
# "anywhere". Centralizado aqui em vez de espalhado, e documentado que
# "remot" sozinho já cobre bastante coisa por ser raiz de palavra, não uma
# palavra fixa: Remoto, Remota, Remote, Trabalho Remoto, 100% Remoto,
# Fully Remote — todas contêm "remot" em algum ponto. "Remoto"/"remota"
# em espanhol usa a mesma raiz ("trabajo remoto"), então já cobertos.
#
# MEDIDO: faltava o vocabulário que NÃO compartilha a raiz "remot" em
# espanhol — "teletrabajo" é o termo padrão no mercado espanhol (visto ao
# vivo: "España (Teletrabajo)"), "trabajo a distancia" e "desde casa"
# também aparecem soltos, sem a raiz "remot" perto. Sem isso, vaga desses
# mercados ficava sem sinal orgânico de remoto (afeta a passada nacional
# de LinkedIn/LinkedIn Intl, que só tem esse texto como fallback quando
# não há filtro nativo — ver _e_remoto em scrapers/linkedin.py e
# linkedin_intl.py) — direto no alvo do perfil internacional (Espanha +
# América Latina).
TERMOS_REMOTO = [
    "remot",  # raiz: Remoto/Remota/Remote/Trabalho Remoto/100% Remoto/Fully Remote
    "home office",
    "work from home",
    "trabalhe de casa",  # variante em português vista ao vivo no Catho
    "teletrabalho",  # português (Portugal)
    "teletrabajo",  # espanhol — termo padrão no mercado espanhol
    "trabajo a distancia",  # espanhol
    "desde casa",  # espanhol ("trabajo desde casa")
    "anywhere",
]


def _e_remoto(texto: str) -> bool:
    return any(termo in texto for termo in TERMOS_REMOTO)


# Vocabulário que, no TÍTULO da vaga, contradiz "remoto" — usado pra não
# confiar cegamente em fonte com filtro nativo de remoto (f_WT=2 do
# LinkedIn) quando ela diverge do próprio anúncio. MEDIDO em produção: 1
# de 81 vagas internacionais veio com modalidade=Remoto (via f_WT=2, o
# LinkedIn classificou como remota) mas o título dizia "Data Analyst
# (Analista de Datos) - Hybrid" — o filtro do próprio LinkedIn às vezes
# diverge do anúncio real. Como o perfil internacional só quer remoto de
# verdade, o título vence quando contradiz a classificação da fonte.
_TERMOS_TITULO_HIBRIDO = ["hybrid", "hibrido"]
_TERMOS_TITULO_PRESENCIAL = ["on-site", "onsite", "on site", "presencial"]


def _modalidade_pelo_titulo(titulo: str) -> str | None:
    """Devolve a modalidade real quando o TÍTULO contradiz "remoto"
    (Híbrido/Presencial) — None quando o título não contradiz nada (a
    classificação da fonte permanece confiável)."""
    titulo_norm = _normalizar(titulo)
    if any(termo in titulo_norm for termo in _TERMOS_TITULO_HIBRIDO):
        return "Híbrido"
    if any(termo in titulo_norm for termo in _TERMOS_TITULO_PRESENCIAL):
        return "Presencial"
    return None


# MEDIDO: "Remote — US only", "Remote — India", "Remote — Portugal" e
# "Remote — Brazil only" passavam TODOS igual no filtro, porque _e_remoto()
# só confirma que existe a raiz "remot" e para de ler ali — não olha o que
# vem depois. "Remoto" não é uma categoria única: cada uma dessas vagas só
# aceita candidato de um país/região específico, e sem separar isso o
# sistema notifica vaga que o candidato nunca conseguiria assumir. Mapa
# nome de mercado (normalizado, sem acento) -> nome canônico pra exibir/
# comparar. Não é exaustivo de propósito — cobre os países já relevantes
# pro projeto (LOCATIONS_INTL/DOMINIOS_INDEED_INTL) mais os mercados
# medidos ao vivo (US, Índia) e alguns comuns o bastante pra valer a pena.
_MERCADOS_REMOTO = {
    "us": "Estados Unidos",
    "usa": "Estados Unidos",
    "united states": "Estados Unidos",
    "estados unidos": "Estados Unidos",
    "eua": "Estados Unidos",
    "uk": "Reino Unido",
    "united kingdom": "Reino Unido",
    "reino unido": "Reino Unido",
    "india": "Índia",
    "brazil": "Brasil",
    "brasil": "Brasil",
    "portugal": "Portugal",
    "spain": "Espanha",
    "espanha": "Espanha",
    "espana": "Espanha",  # "España" já normalizado (sem ~) vira "espana"
    "mexico": "México",
    "colombia": "Colômbia",
    "argentina": "Argentina",
    "chile": "Chile",
    "canada": "Canadá",
    "germany": "Alemanha",
    "alemanha": "Alemanha",
    "latam": "LATAM",
    "latin america": "LATAM",
    "america latina": "LATAM",
    "europe": "Europa",
    "europa": "Europa",
    "emea": "EMEA",
    # Resto dos países hispanofalantes/lusófonos que MERCADOS_REMOTO_ACEITOS_INTL
    # passou a aceitar — sem entrada aqui, "Remote - Peru"/"Remote - Uruguay"
    # cai no mesmo "mercado não mapeado" que qualquer país não aceito (ver
    # comentário em _mercado_correspondente), e nunca bateria contra a lista
    # aceita mesmo sendo um país que o projeto quer aceitar.
    "peru": "Peru",
    "uruguay": "Uruguai",
    "uruguai": "Uruguai",
    "paraguay": "Paraguai",
    "paraguai": "Paraguai",
    "bolivia": "Bolívia",
    "ecuador": "Equador",
    "equador": "Equador",
    "venezuela": "Venezuela",
    "costa rica": "Costa Rica",
    "panama": "Panamá",
    "guatemala": "Guatemala",
    "honduras": "Honduras",
    "el salvador": "El Salvador",
    "nicaragua": "Nicarágua",
    "dominican republic": "República Dominicana",
    "republica dominicana": "República Dominicana",
    "puerto rico": "Porto Rico",
    "porto rico": "Porto Rico",
    "cuba": "Cuba",
    "angola": "Angola",
    "mozambique": "Moçambique",
    "mocambique": "Moçambique",
    "cape verde": "Cabo Verde",
    "cabo verde": "Cabo Verde",
}

# MEDIDO: "Remoto (Porto Alegre, RS)" e "Remoto (Santiago do Cacém)"
# viravam Portugal/Chile — a chave "porto" batia via \bporto\b dentro de
# "porto alegre" (busca por substring/palavra do _mercado_correspondente),
# e "santiago" batia dentro de "santiago do cacem" pelo mesmo motivo.
# Nome de cidade curto e comum É um pedaço válido de outro nome de lugar
# bem mais vezes do que nome de país (nenhum país se chama só "porto" ou
# "santiago" por acaso, mas MUITA cidade brasileira/portuguesa começa
# assim). Por isso cidade não entra em _MERCADOS_REMOTO (busca por
# substring, adequada pra nome de país inteiro) — fica num dicionário
# separado, casado por IGUALDADE do candidato inteiro (ver
# extrair_escopo_remoto), não por substring. "Remoto (Porto Alegre, RS)"
# nem chega aqui: a sigla "RS" já resolve Brasil antes (ver
# _SIGLAS_UF_BRASIL). Isso só entra em jogo quando NÃO há sigla/país
# junto do nome — ex: "Remoto (Lisboa)" sozinho.
#
# Ainda existe ambiguidade entre PAÍSES diferentes pro mesmo nome de
# cidade (Valencia existe na Espanha E na Venezuela; Córdoba na Argentina
# E na Espanha; San José é capital da Costa Rica mas também cidade nos
# EUA) — sem base geográfica de verdade não dá pra resolver isso com
# certeza; a escolha abaixo é a leitura mais provável dado o escopo do
# projeto (mercado hispanofalante/lusófono), não uma garantia.
_CIDADES_MERCADO = {
    "lisboa": "Portugal",
    "lisbon": "Portugal",  # grafia inglesa, comum em card do LinkedIn
    "porto": "Portugal",
    "madrid": "Espanha",
    "barcelona": "Espanha",
    "valencia": "Espanha",
    "bilbao": "Espanha",
    # Comunidade autônoma/região espanhola — mesmo tratamento de cidade
    # (candidato inteiro igual à chave, sem risco de substring cruzado
    # com outro país, já que nenhuma colide).
    "catalunya": "Espanha",
    "cataluna": "Espanha",  # "Catalunya"/"Cataluña" sem acento
    "andalucia": "Espanha",
    "galicia": "Espanha",
    "pais vasco": "Espanha",
    "euskadi": "Espanha",
    "canarias": "Espanha",
    "sevilla": "Espanha",
    "malaga": "Espanha",
    "lugo": "Espanha",
    "vizcaya": "Espanha",
    "bizkaia": "Espanha",
    "guipuzcoa": "Espanha",
    "gipuzkoa": "Espanha",
    "leiria": "Portugal",
    "cidade do mexico": "México",
    "ciudad de mexico": "México",
    "guadalajara": "México",
    "monterrey": "México",
    "bogota": "Colômbia",
    "medellin": "Colômbia",
    "buenos aires": "Argentina",
    "cordoba": "Argentina",
    "santiago": "Chile",
    "lima": "Peru",
    "montevideu": "Uruguai",
    "montevideo": "Uruguai",
    "assuncao": "Paraguai",
    "asuncion": "Paraguai",
    "la paz": "Bolívia",
    "santa cruz de la sierra": "Bolívia",
    "quito": "Equador",
    "guayaquil": "Equador",
    "caracas": "Venezuela",
    "san jose": "Costa Rica",
    "cidade do panama": "Panamá",
    "panama city": "Panamá",
    "cidade da guatemala": "Guatemala",
    "guatemala city": "Guatemala",
    "tegucigalpa": "Honduras",
    "san salvador": "El Salvador",
    "managua": "Nicarágua",
    "santo domingo": "República Dominicana",
    "san juan": "Porto Rico",
    "havana": "Cuba",
    "havanna": "Cuba",
    "luanda": "Angola",
    "maputo": "Moçambique",
    "praia": "Cabo Verde",
}

# Termos que aparecem depois de "remote" mas NÃO restringem geografia —
# "Remote (Anywhere)"/"Remote - Worldwide" é remoto sem escopo nenhum,
# equivalente a não achar mercado nenhum (retorna "").
_MERCADOS_SEM_RESTRICAO = {"anywhere", "worldwide", "global"}

# Palavras de apoio que aparecem junto do nome do mercado mas não fazem
# parte dele — "US only", "Brazil based", "US timezone" — removidas antes de
# tentar casar contra _MERCADOS_REMOTO, senão "us only" nunca bateria com a
# chave "us".
_PALAVRAS_IGNORAR_ESCOPO = {
    "only", "based", "timezone", "timezones", "time", "zone", "zones",
    "somente", "apenas",
    # MEDIDO: "Greater Buenos Aires", "Medellín Metropolitan Area", "Porto
    # Metropolitan Area", "Madrid, Madrid provincia" — formato comum de
    # local do LinkedIn pra cidade da Ibéria/LATAM, mas "greater"/
    # "metropolitan"/"area"/"provincia" sobrando no meio impedia bater
    # contra _CIDADES_MERCADO (que exige igualdade do candidato inteiro).
    # NÃO é o mesmo risco do comentário abaixo sobre "Greater Seattle
    # Area" virar aceito sem querer: aqui a palavra só é REMOVIDA do
    # candidato antes de checar contra a lista fechada de cidades
    # aceitas — "seattle" continua não estando nela, então "Greater
    # Seattle Area" continua caindo em "não reconhecido" normalmente.
    "greater", "metropolitan", "metropolitana", "area", "provincia",
}

# Palavras em português que indicam descrição de ABRANGÊNCIA dentro do
# Brasil, não nome de país — ex: "Remoto (Barueri + 35 cidades)" (visto ao
# vivo em jobs.db). Sem essa lista, esse tipo de vaga nacional virava
# "escopo declarado mas não reconhecido" e era barrada pela mesma lógica
# que bloqueia país estrangeiro fora da lista aceita (ver
# extrair_escopo_remoto). Só cobre vocabulário em PORTUGUÊS de propósito —
# o equivalente em inglês ("area", "metropolitan", "county", "metro") é
# exatamente o sinal real de vaga americana sem sigla de estado explícita
# (ex: "Remote (Greater Seattle Area)", "Remote (Dallas-Fort Worth
# Metroplex)") e esse caso PRECISA continuar caindo em "não reconhecido" —
# tratá-lo como sem restrição reabriria o vazamento de vaga americana que
# esse fix inteiro existe pra fechar.
_PALAVRAS_REGIAO_BR = {"cidade", "cidades", "regiao", "distrito", "condado"}

# Separador entre a raiz "remot..." e o texto de escopo que vem depois:
# travessão/hífen ("Remote — US only", "Remote - India"), vírgula ("Remote,
# United States") ou parênteses ("Remote (Brazil only)"). Sem nenhum desses
# logo após "remot", não tem escopo textual pra ler (ex: "Remote" sozinho,
# ou "Remoto" sem complemento) — trata como sem restrição.
_PADRAO_ESCOPO_SEPARADOR = re.compile(r"remot[eoa]\w*\s*[–—\-,(:]+\s*")

# MEDIDO: quando quem confirma remoto é `modalidade` (não o separador —
# ver ramo `elif modalidade_norm in (...)` em extrair_escopo_remoto),
# `resto` vira o texto de `local` INTEIRO, sem cortar nada antes dele.
# Isso deixa vocabulário de modalidade (raiz "remot", "home office"...) e
# o placeholder "Não informado" (valor padrão de `local` em todo scraper
# que não achou o campo — Catho, Gupy, Indeed, LinkedIn, Solides, Trampos,
# WeWorkRemotely...) dentro do candidato a mercado. Nenhum dos dois é
# nome de país: local="Remoto" -> candidato "remoto"; local="Não
# informado" -> candidato "nao informado"; local="Não informado (Remoto)"
# -> candidato "nao informado (remoto)"; local="Home Office" -> candidato
# "home office" — todos caem no fallback de _mercados_correspondentes
# como "escopo desconhecido" e são BARRADOS por MERCADOS_REMOTO_ACEITOS,
# quando na verdade são vaga remota sem NENHUM escopo geográfico
# declarado (deveria ser conjunto vazio, sem restrição). 59 registros
# nesse formato sobreviviam no jobs.db só porque foram gravados quando
# `modalidade` ainda vinha vazia (o ramo modalidade nem existia). Remove
# os dois antes de montar `candidato` — ver _remover_ruido_escopo.
_PLACEHOLDER_LOCAL_AUSENTE = "nao informado"

_PADRAO_VOCABULARIO_MODALIDADE = re.compile(
    "|".join(
        r"remot\w*" if termo == "remot" else re.escape(termo)
        for termo in TERMOS_REMOTO
    )
)


def _remover_ruido_escopo(texto: str) -> str:
    """Tira vocabulário de modalidade e o placeholder de local ausente de
    um texto já normalizado (ver MEDIDO acima) — o que sobrar é candidato
    real a nome de mercado, não ruído de "isso é remoto" repetido ou "não
    sei o local"."""
    texto = _PADRAO_VOCABULARIO_MODALIDADE.sub(" ", texto)
    texto = texto.replace(_PLACEHOLDER_LOCAL_AUSENTE, " ")
    texto = texto.replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", texto).strip()

# MEDIDO em produção (jobs.db, fonte LinkedIn): 246 de 269 notificações
# (91%) vieram no formato "Remoto (Cidade, SIGLA)" — ex: "Remoto (New York,
# NY)", "Remoto (Austin, TX)", "Remoto (Seattle, WA)". Nenhuma batia em
# _MERCADOS_REMOTO porque esse dicionário só reconhece NOME DE PAÍS
# ("us"/"united states"/...), nunca sigla de estado — e o texto real do
# LinkedIn pra vaga remota americana quase nunca escreve "United States"
# por extenso, só a cidade-âncora + sigla de 2 letras do estado. Resultado:
# toda essa vaga passava como "remoto sem escopo declarado" (comportamento
# correto só quando de fato não há como saber o mercado) mesmo sendo
# claramente uma vaga americana — driblava MERCADOS_REMOTO_ACEITOS por
# completo. Lista das 50 siglas + DC.
_SIGLAS_ESTADOS_EUA = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}

# MEDIDO: "Remoto (Maceió, AL)", "Remoto (Belém, PA)", "Remoto (Florianópolis,
# SC)", "Remoto (Cuiabá, MT)", "Remoto (São Luís, MA)", "Remoto (Campo
# Grande, MS)" — as 27 UFs brasileiras usam sigla de 2 letras igual ao
# estado americano, e 6 delas colidem literalmente com uma sigla dos EUA
# (AL/Alabama, MA/Massachusetts, MT/Montana, MS/Mississippi, PA/Pennsylvania,
# SC/South Carolina). Sem desambiguar, toda vaga remota numa capital
# brasileira com sigla ambígua virava "Estados Unidos" e era barrada — o
# mesmo bug que motivou o fix de _SIGLAS_ESTADOS_EUA, só que na direção
# oposta.
#
# Todas as 27 siglas de UF, não só as ambíguas — cidade brasileira fora do
# Nordeste (Rio de Janeiro/RJ, São Paulo/SP...) também não tinha como bater
# em _MERCADOS_REMOTO nem na rede de segurança de CIDADES (que é só
# Nordeste, feita pra vaga presencial/híbrida, não pensada pra cobrir
# escopo de vaga remota do Brasil inteiro).
_SIGLAS_UF_BRASIL = {
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms",
    "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc",
    "sp", "se", "to",
}

# As 6 siglas que colidem com estado americano — só nessas precisa olhar o
# nome da cidade antes de decidir Brasil vs EUA. Sigla de UF que não colide
# (RJ, SP, PE...) já resolve sozinha, nenhum estado americano usa essas.
_SIGLAS_UF_AMBIGUAS = {"al", "ma", "mt", "ms", "pa", "sc"}

# Capital de cada estado brasileiro (+DF), normalizado — usado só pra
# desambiguar as 6 siglas acima. Cobre exatamente o formato que o LinkedIn
# mostra pra vaga remota brasileira ("Remoto (Capital, UF)"), sem precisar
# de uma base de cidade completa.
_CAPITAIS_BRASIL = {
    "rio branco", "maceio", "macapa", "manaus", "salvador", "fortaleza",
    "brasilia", "vitoria", "goiania", "sao luis", "cuiaba", "campo grande",
    "belo horizonte", "belem", "joao pessoa", "curitiba", "recife",
    "teresina", "rio de janeiro", "natal", "porto alegre", "porto velho",
    "boa vista", "florianopolis", "sao paulo", "aracaju", "palmas",
}

# MEDIDO: "Monterrey, N.L.", "Cuauhtémoc, CDMX", "León, Gto.", "Ciudad
# Juárez, Chih.", "Guadalajara, Jal.", "San Luis Potosí, S.L.P." — mesmo
# formato "Cidade, SIGLA" do card americano/brasileiro, mas o LinkedIn
# nunca resolvia porque não existia sigla mexicana nenhuma cadastrada.
# Sem colisão com _SIGLAS_UF_BRASIL/_SIGLAS_ESTADOS_EUA (nenhuma bate
# igual), então checa direto, sem precisar de desambiguação por cidade
# como as 6 UFs brasileiras ambíguas. Ponto já foi removido de `texto_norm`
# antes de chegar aqui (ver extrair_escopo_remoto), então "n.l"/"s.l.p"
# chegam como "nl"/"slp".
_SIGLAS_ESTADOS_MEXICO = {
    "ags", "bc", "bcs", "cam", "chis", "chih", "coah", "col", "cdmx",
    "dgo", "gto", "gro", "hgo", "jal", "mex", "mich", "mor", "nay", "nl",
    "oax", "pue", "qro", "qroo", "slp", "sin", "son", "tab", "tamps",
    "tlax", "ver", "yuc", "zac",
}


def _mercados_correspondentes(candidato: str) -> set[str]:
    """Devolve TODOS os mercados que o candidato menciona, não só o
    primeiro.

    MEDIDO: "Remote - Brazil/LATAM" e "Remote - LATAM + Brazil" resolviam
    pra um único mercado ("Brasil"), porque a versão antiga (chamada
    _mercado_correspondente) parava no primeiro match — e a ordem de busca
    era por tamanho de chave ("brazil", 6 letras, antes de "latam", 5),
    não pela ordem em que os mercados aparecem no texto. Vaga aberta pra
    LATAM inteira (que o perfil internacional aceita) virava só "Brasil"
    (que ele rejeita de propósito), e a vaga se perdia mesmo sendo válida.
    Agora coleta todo mercado que aparece no texto — combina_com() aprova
    se qualquer um bater na lista aceita.
    """
    if not candidato or candidato in _MERCADOS_SEM_RESTRICAO:
        return set()
    encontrados = {
        nome for chave, nome in _MERCADOS_REMOTO.items()
        if re.search(rf"\b{re.escape(chave)}\b", candidato)
    }
    if encontrados:
        return encontrados
    # MEDIDO: filtro de mercado era blocklist disfarçada de allowlist —
    # país fora do dicionário (Vietnã, Nigéria, Polônia, Filipinas...)
    # devolvia conjunto vazio aqui, e conjunto vazio é tratado por
    # extrair_escopo_remoto/combina_com como "sem restrição declarada", ou
    # seja, PASSAVA pelo mesmo motivo que país aceito passava. Devolve o
    # candidato bruto num conjunto de 1 item em vez de vazio — não-vazio
    # sinaliza "escopo foi declarado no texto, só não está mapeado", o que
    # combina_com() agora trata como reprovado quando não bate a lista
    # aceita (ver RegrasFiltro.mercados_remoto_aceitos). Conjunto vazio
    # continua reservado só pra quando NÃO HÁ texto de escopo nenhum (ver
    # extrair_escopo_remoto) ou pra "Anywhere"/"Worldwide" explícito acima.
    return {candidato}


def extrair_escopo_remoto(texto_local: str, modalidade: str = "") -> set[str]:
    """Deriva o(s) mercado(s) geográfico(s) de uma vaga remota a partir do
    texto de `local`, quando a fonte expõe isso ali (ex: "Remote — US
    only", "Remote, Brazil", "Remote - LATAM + Brazil"). Retorna um
    CONJUNTO de nomes canônicos ({"Estados Unidos"}, {"Brasil", "LATAM"}...),
    um conjunto de 1 item com o texto bruto quando um escopo FOI declarado
    mas não bate em nenhum país conhecido (ex: "Remote - Vietnam" ->
    {"vietnam"} literal), ou conjunto VAZIO só quando não há NENHUM texto
    de escopo pra ler (remoto "puro", sem qualificador nenhum, ou
    "Anywhere"/"Worldwide" explícito).

    Conjunto vazio e "escopo desconhecido" são sinais DIFERENTES pra
    combina_com(): vazio é "sem restrição, aceita" (não tem base nenhuma
    pra rejeitar); qualquer conjunto não-vazio cuja INTERSEÇÃO com
    mercados_remoto_aceitos for vazia é rejeitado, mesmo quando os valores
    são país que o dicionário não reconhece — ver _mercados_correspondentes.

    MEDIDO: "Remote - Brazil/LATAM" e "Remote - LATAM + Brazil" (vaga
    aberta pra América Latina inteira) resolviam só pra "Brasil" quando a
    função devolvia um único valor — a vaga válida pro perfil
    internacional (que aceita LATAM) se perdia porque o valor sobrevivente
    era justamente o que ele rejeita de propósito. Devolver todos os
    mercados do texto, e aprovar se QUALQUER um bater na lista aceita
    (ver combina_com), resolve isso sem perder a precisão dos outros casos.

    MEDIDO: desde que modalidade virou campo próprio do Job (scraper não
    escreve mais "Remoto" dentro de `local`), toda essa extração ficava
    inalcançável pra fonte com filtro nativo — LinkedIn (f_WT=2) e
    WeWorkRemotely confirmam via `modalidade`, não mais via texto, então
    `local` chega aqui como só "New York, NY" ou "Bangalore, India", sem a
    raiz "remot" nenhuma. Sem o parâmetro `modalidade`, _PADRAO_ESCOPO_SEPARADOR
    nunca casava e a função devolvia conjunto vazio (sem restrição) pra
    QUALQUER vaga remota confirmada por campo — inclusive as americanas/
    indianas/etc que esse fix inteiro existe pra barrar. Quando não há
    separador no texto mas `modalidade` já diz remoto, trata `local`
    INTEIRO como candidato de escopo (a fonte confirmou modalidade por
    fora; o que sobra em `local` é só a âncora geográfica, sem precisar
    achar "remot" dentro dele). MEDIDO: tratar `local` inteiro sem limpar
    vocabulário de modalidade ("Remoto", "Home Office"...) nem o
    placeholder "Não informado" fazia esse vocabulário virar candidato a
    mercado — local="Remoto" resolvia pra {"remoto"}, desconhecido pra
    qualquer lista aceita, e a vaga era barrada mesmo sendo remota sem
    NENHUM escopo declarado. _remover_ruido_escopo tira os dois antes de
    montar o candidato.
    """
    texto_norm = _normalizar(texto_local)
    # MEDIDO: abreviação de estado com ponto ("N.L.", "S.L.P.", "Gto.",
    # "Chih.") sobrevivia ao _normalizar (que só mexe em caixa/acento) e
    # nunca batia contra sigla nenhuma (_SIGLAS_UF_MEXICO abaixo usa forma
    # sem ponto). Remove ponto do texto inteiro, cedo — mais simples que
    # tratar em cada abreviação/dicionário separadamente. "u.s" deixou de
    # ser alcançável em _MERCADOS_REMOTO por causa disso (a chave "us" já
    # cobre o mesmo caso), removida de lá.
    texto_norm = texto_norm.replace(".", "")
    modalidade_norm = _normalizar(modalidade)
    m = _PADRAO_ESCOPO_SEPARADOR.search(texto_norm)
    if m:
        resto = texto_norm[m.end():]
        resto = re.split(r"[)\n]", resto)[0]
    elif modalidade_norm in ("remoto", "remota"):
        resto = _remover_ruido_escopo(texto_norm)
        if not resto:
            return set()
    else:
        return set()

    # Formato "Cidade, SIGLA" (ex: "new york, ny") — a sigla de estado
    # depois da vírgula é o sinal de mercado aqui, não o nome da cidade
    # antes dela. Checa todo segmento separado por vírgula que NÃO seja o
    # primeiro (o primeiro é sempre a cidade nesse formato, nunca a sigla)
    # — ver comentário de _SIGLAS_ESTADOS_EUA acima.
    segmentos = [s.strip(" .") for s in resto.split(",")]
    cidade = segmentos[0] if segmentos else ""
    for seg in segmentos[1:]:
        # UF brasileira primeiro: só as 6 ambíguas (colidem com sigla dos
        # EUA) precisam confirmar pela cidade — ver _SIGLAS_UF_AMBIGUAS.
        # UF que não colide (RJ, SP, PE...) já resolve sozinha.
        if seg in _SIGLAS_UF_BRASIL:
            if seg not in _SIGLAS_UF_AMBIGUAS or cidade in _CAPITAIS_BRASIL:
                return {"Brasil"}
        if seg in _SIGLAS_ESTADOS_EUA:
            return {"Estados Unidos"}
        if seg in _SIGLAS_ESTADOS_MEXICO:
            return {"México"}

    # Nome de mercado por extenso também pode vir DEPOIS da cidade, não só
    # antes ("Florida, United States" — cortar no primeiro segmento, como
    # antes, jogava fora justamente o "United States" e devolvia "Florida",
    # que não bate em nenhuma chave de _MERCADOS_REMOTO). Substitui a
    # vírgula por espaço em vez de cortar, mantendo os segmentos na ordem
    # original — _mercados_correspondentes já faz busca por substring com
    # borda de palavra, então acha todo nome de mercado presente, em
    # qualquer posição.
    # MEDIDO: "08015, Barcelona, Barcelona provincia" — código postal
    # espanhol na frente vira palavra solta no candidato ("08015 barcelona
    # barcelona"), nunca bate em nenhuma chave. Puramente numérico nunca é
    # nome de mercado, então descarta direto.
    palavras = [
        p for p in resto.replace(",", " ").split()
        if p not in _PALAVRAS_IGNORAR_ESCOPO and not p.isdigit()
    ]

    # MEDIDO: formato espanhol "Cidade, Cidade provincia" (província tem o
    # mesmo nome da capital na maioria dos casos — "Madrid, Madrid
    # provincia", "Barcelona, Barcelona provincia") sobra como palavra
    # repetida depois de tirar "provincia" acima ("madrid madrid"), que
    # nunca bate IGUALDADE contra _CIDADES_MERCADO (que tem só "madrid").
    # Candidato com todas as palavras iguais colapsa pra uma só — não
    # afeta cidade composta de palavras DIFERENTES ("buenos aires",
    # "porto alegre"), só o caso degenerado de repetição.
    if len(set(palavras)) == 1:
        palavras = palavras[:1]

    candidato = " ".join(palavras).strip()

    if not candidato:
        return set()

    # "Barueri + 35 cidades" é abrangência DENTRO do Brasil, não nome de
    # país estrangeiro — ver _PALAVRAS_REGIAO_BR. Sai como conjunto vazio
    # (sem restrição) antes de chegar no fallback de "escopo desconhecido"
    # de _mercados_correspondentes, que rejeitaria isso pelo motivo errado.
    if any(p in _PALAVRAS_REGIAO_BR for p in candidato.split()):
        return set()

    # Cidade sozinha, sem sigla/país junto (ex: "Remoto (Porto Alegre)",
    # "Remoto (Lisboa)") — casamento por IGUALDADE do candidato inteiro,
    # não substring (ver comentário de _CIDADES_MERCADO acima pro motivo).
    # Capital brasileira primeiro: cobre "Porto Alegre"/"Porto Velho" sem
    # UF junto, que sem isso cairiam direto em _CIDADES_MERCADO e virariam
    # Portugal via "porto" — aqui o candidato já é a cidade inteira, então
    # não tem esse risco de substring.
    if candidato in _CAPITAIS_BRASIL:
        return {"Brasil"}
    if candidato in _CIDADES_MERCADO:
        return {_CIDADES_MERCADO[candidato]}

    return _mercados_correspondentes(candidato)


# Padrões de data confirmados ao vivo neste projeto: "Publicada em 11/08"
# (Catho) e "Há 4 meses" / "Há 3 semanas" (LinkedIn, no card de busca).
# Regex sobre o TEXTO INTEIRO do card, em vez de um seletor CSS por site —
# cada fonte marca isso de um jeito diferente (às vezes nem tag própria,
# só texto solto), e adivinhar seletor sem inspecionar o DOM ao vivo é
# arriscado (podia quebrar silenciosamente ou pegar texto errado). Regex
# sobre o texto renderizado funciona em qualquer site sem esse risco — na
# pior hipótese não acha nada e publicado_em fica "" (aceitável, "quando
# existir").
_PADRAO_DATA_ABSOLUTA = re.compile(
    r"publicad[ao]\s+(?:em|há)?\s*:?\s*"
    r"(\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{2,4})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
    re.IGNORECASE,
)
_PADRAO_DATA_RELATIVA = re.compile(
    # Plural como sufixo opcional (dias?/semanas?/anos?), não alternativa
    # separada — "dia|dias" bate "dia" primeiro e para aí, cortando o "s"
    # de "dias" (regex não escolhe o match mais longo, escolhe o primeiro).
    r"há\s+\d+\s+(?:dias?|semanas?|m[êe]s(?:es)?|anos?)",
    re.IGNORECASE,
)
_PADRAO_HOJE_ONTEM = re.compile(r"\b(hoje|ontem)\b", re.IGNORECASE)


def extrair_data_publicacao(texto_card: str) -> str:
    """Procura sinal de data de publicação no texto renderizado de um card
    de vaga. Cobre formato absoluto ("Publicada em 11/08", "Publicada em 11
    de agosto de 2026") e relativo ("Há 4 meses"). Retorna "" quando o site
    não expõe isso no card de busca — nem toda fonte tem.
    """
    for padrao in (_PADRAO_DATA_ABSOLUTA, _PADRAO_DATA_RELATIVA, _PADRAO_HOJE_ONTEM):
        m = padrao.search(texto_card)
        if m:
            return m.group(0).strip()
    return ""


# Ordem importa: do mais específico pro mais genérico. Título não é
# filtrado por senioridade — só é classificado, pra decidir isso na hora de
# ler a notificação, não em deixar a vaga passar ou não.
_NIVEIS_SENIORIDADE = [
    ("Estágio/Trainee", (r"estagi[ao]", r"estagio", r"trainee")),
    ("Júnior", (r"junior", r"jr\.?")),
    ("Pleno", (r"pleno", r"pl\.?")),
    ("Sênior", (r"senior", r"sr\.?", r"sênior")),
    ("Especialista", (r"especialista", r"specialist")),
    ("Liderança", (r"coordenador", r"coordenadora", r"gerente", r"manager", r"head")),
]


def _detectar_senioridade(titulo: str) -> str:
    """Classifica o nível pelo título, sem excluir nada — a ideia é decidir
    na hora de ler a notificação se vale a pena abrir o link, não descartar
    vaga automaticamente (júnior pode virar sênior lendo a descrição, e
    "PL"/"Sr" no título nem sempre reflete o que a empresa pede de verdade).
    """
    titulo_norm = _normalizar(titulo)

    for nivel, padroes in _NIVEIS_SENIORIDADE:
        for padrao in padroes:
            if re.search(rf"(?<!\w){padrao}(?!\w)", titulo_norm):
                return nivel

    numeral = re.search(r"(?<!\w)(i{1,3}|iv)(?!\w)", titulo_norm)
    if numeral:
        return f"Nível {numeral.group(1).upper()}"

    return "Não especificado"


@dataclass
class RegrasFiltro:
    """Agrupa as 6 regras que Job.combina_com() usa pra decidir se uma vaga
    bate ou não. Antes eram 6 parâmetros posicionais soltos, atravessando
    job.py -> utils/filtro.py -> main.py/main_intl.py — cada regra nova
    (já foram 6: forte, ambíguo, qualificador de dados, ferramenta,
    qualificador de cargo, cidade) alongava a lista de posições, e trocar a
    ordem de dois argumentos do mesmo tipo (duas list[str] quaisquer) não dá
    erro nenhum, só passa a filtrar errado em silêncio — nada no Python
    detecta isso, já que todos os parâmetros têm o mesmo tipo. Um objeto
    único com nome em cada campo elimina esse risco: a ordem da CHAMADA
    deixa de importar (kwargs/atributos nomeados), e esquecer um campo vira
    TypeError na hora (dataclass sem default nos campos obrigatórios), não
    filtro errado descoberto só depois.
    """
    keywords_forte: list[str]
    keywords_ambiguo: list[str]
    qualificadores_dados: list[str]
    ferramentas_titulo: list[str]
    qualificadores_cargo: list[str]
    cidades: list[str]
    # Mercados aceitos pra vaga remota COM escopo geográfico explícito no
    # texto (ver Job.escopo_remoto/extrair_escopo_remoto). None = não checa
    # escopo nenhum (aceita qualquer remoto, comportamento de antes desse
    # campo existir — default seguro pra quem ainda não configurou isso).
    # Lista vazia é diferente de None: significa "só aceita remoto SEM
    # escopo declarado", rejeitando todo mercado explícito.
    mercados_remoto_aceitos: list[str] | None = None
    # MEDIDO: perfil internacional não exigia espanhol/português na vaga em
    # si — só nos TERMOS de busca (ex: "data analyst spanish speaker"), que
    # nunca eram checados de novo depois. "Senior Data Analyst"/"Data
    # Analyst" remoto e sem mercado declarado passava sem nenhuma relação
    # com o idioma, porque o resultado bateu no termo de busca (que casa
    # contra o anúncio inteiro, não só o título que a gente guarda) sem que
    # "spanish"/"portuguese"/"latam" apareça em nada que sobra depois.
    #
    # Mesma lógica de keywords_ambiguo (cargo ambíguo só conta com
    # qualificador junto): quando o escopo já é um país que fala espanhol/
    # português (ver mercados_remoto_aceitos), o PAÍS é o próprio sinal de
    # idioma — não precisa achar a palavra no título também. Só entra em
    # jogo quando a vaga é remota SEM mercado declarado (escopo vazio, não
    # tem como saber o país), aí sim o título precisa mencionar idioma/
    # mercado hispanofalante-lusófono explicitamente. None = não checa
    # (BR não precisa — fonte já é 100% brasileira/portuguesa).
    idiomas_exigidos: list[str] | None = None
    modalidades_aceitas: dict[str, bool] | None = None
    preferencia_modalidade: str = "sem_preferencia"
    senioridades_alvo: list[str] | None = None


@dataclass
class _Avaliacao:
    """Resultado intermediário de Job._avaliar() — reaproveitado por
    combina_com() (filtro, decide passa/não passa) e pontuar_relevancia()
    (score, só ordena o que já passou). Extraído pra um lugar só depois de
    escopo_rejeitado_por_mercado ter precisado refazer parte da mesma conta
    separadamente (ver MEDIDO lá) — mais um método calculando a mesma coisa
    de outro jeito é exatamente o padrão que já causou bug real nesta base
    (ver extrair_escopo_remoto)."""
    aprovada: bool
    bate_forte: bool
    bate_ambiguo: bool
    bate_ferramenta: bool
    bate_remoto: bool
    escopos: set[str]
    mercado_confirmado: bool  # escopo bateu explicitamente um mercado aceito
    idioma_bateu_titulo: bool


# Pesos do score de relevância (pontuar_relevancia, máximo 10) — soma
# simples, sem aprendizado de máquina: o conjunto de sinais é pequeno (5) e
# o peso de cada um já é conhecido, não precisa de modelo pra isso. NÃO é
# filtro — só ordena o que já passou combina_com(). MEDIDO: com ~320
# vaga/dia aprovada (item 01 do perfil internacional sozinho já passou de
# 10/dia pra isso), toda vaga chegava com o mesmo destaque no Telegram, a
# ideal e a tolerável lado a lado sem diferença nenhuma.
_PESO_CARGO_FORTE = 3
_PESO_CARGO_AMBIGUO = 2
_PESO_FERRAMENTA = 2
_PESO_SENIORIDADE_ALVO = 2
_PESO_SENIORIDADE_NEUTRA = 1  # título sem nível classificável — não penaliza por falta de informação
# MEDIDO: classificar sem excluir (ver docstring de _detectar_senioridade)
# continua certo, mas 0 pontos pra Sênior/Especialista/Liderança tratava
# "acima do alvo" igual a "não deu pra saber" — as duas ficavam empatadas
# no score. Medido contra as 780 vagas do jobs.db real: 25% classificam
# Sênior/Especialista/Liderança, 65% não especificado, só 5,5%
# Júnior/Pleno — sem separar os dois grupos de zero pontos, a maioria das
# vagas realmente no alvo não se destacava de vaga acima do alvo nenhuma.
# Peso negativo simétrico ao bônus (+2/-2): puxa pra baixo sem excluir —
# a vaga continua passando por combina_com() e notificando (imediata ou no
# digest), só cai mais no ranking.
_PESO_SENIORIDADE_ACIMA_DO_ALVO = -2
_PESO_MERCADO = 2
_PESO_MERCADO_NAO_CONFIRMADO = 1  # remota sem mercado declarado no texto (aceita por padrão, sem confirmar)
_PESO_IDIOMA = 1

# Prioridade definida pelo usuário: Júnior e Pleno pontuam o teto de
# senioridade (bônus). Sênior/Especialista/Liderança pontuam negativo
# (acima do alvo, deságio). Estágio/Trainee fica neutro — nem é o alvo nem
# é o problema de "vaga tolerável demais" que motivou o deságio (volume
# desprezível: 0,3% da base). Nada disso é filtro — a vaga ainda notifica,
# só muda a posição no ranking (imediata vs. digest, topo vs. fundo).
_NIVEIS_SENIORIDADE_ALVO = {"Júnior", "Pleno"}
_NIVEIS_SENIORIDADE_ACIMA_DO_ALVO = {"Sênior", "Especialista", "Liderança"}


@dataclass
class Job:
    titulo: str
    empresa: str
    local: str
    link: str
    site: str
    # Data anunciada pela FONTE (não a data em que o JobRadar achou a vaga —
    # essa já existe em vagas_vistas.encontrada_em). Sem isso não dá pra
    # medir latência real (quanto tempo entre a vaga ser publicada e o
    # JobRadar notificar) nem priorizar vaga recente na notificação. Formato
    # livre (string), porque cada site anuncia diferente — data absoluta
    # ("11/08", "11 de agosto de 2026"), timestamp ISO (Trampos), ou texto
    # relativo ("Há 4 meses", "Contratando agora"). Normalizar tudo pra um
    # formato único exigiria parser por site (relativo→absoluto), fora do
    # escopo agora — string crua já é suficiente pra exibir na notificação e
    # é o que a fonte realmente disse. "" quando o site não expõe a data.
    publicado_em: str = ""
    # Modalidade (Remoto/Híbrido/Presencial) como campo PRÓPRIO, preenchido
    # pelo scraper na hora da extração. Antes vivia embutida dentro do texto
    # de `local` (ex: "São Paulo - SP (Remoto)") e era redetectada por
    # substring toda vez que combina_com() rodava — inclusive mais de uma
    # vez pra mesma vaga, quando o pipeline internacional roda a mesma lista
    # de vagas contra CIDADES_INTL e depois CIDADES_EUROPA_IBERICA. Detectar
    # uma vez, na fonte, e guardar aqui elimina o retrabalho e mantém
    # `local` só com informação de localização de verdade. Valores usados:
    # "Remoto", "Híbrido", "Presencial", ou "" quando a fonte não expõe.
    modalidade: str = ""
    # MEDIDO: WeWorkRemotelyIntlScraper preenche `local` com a SEDE da
    # empresa (".new-listing__company-headquarters"), não o mercado onde a
    # vaga contrata — o site é 100% remoto por definição, sede não diz nada
    # sobre de onde a empresa aceita candidato. Depois que
    # extrair_escopo_remoto passou a usar `local` inteiro como escopo
    # quando `modalidade` já confirma remoto (ver Job.escopo_remoto), uma
    # vaga remota mundial de empresa sediada nos EUA passaria a ser barrada
    # pelo endereço da sede, que nunca foi o mercado real da vaga. Esse
    # flag existe pra distinguir os dois casos: `local` como mercado de
    # contratação de verdade (LinkedIn/Indeed, onde o campo reflete a
    # vaga) vs `local` como informação de sede (WeWorkRemotely, onde não
    # reflete). Mantém `local` preenchido pra exibir na notificação — só
    # tira ele da checagem de mercado.
    escopo_indefinido: bool = False
    # Score de pontuar_relevancia() (0-10), preenchido por filtrar_vagas()
    # depois que a vaga passa combina_com() — 0 até lá (nunca usado sozinho
    # pra decidir nada, só pra ORDENAR/destacar na notificação).
    relevancia: int = 0
    # Texto de motivo_aprovacao() (ver método), preenchido junto de
    # relevancia — "" até lá. Só pra aparecer na notificação; não
    # influencia filtro nem score.
    motivo: str = ""

    def __post_init__(self):
        """Sobrepõe modalidade="Remoto" quando o TÍTULO contradiz (Híbrido/
        Presencial) — ver _modalidade_pelo_titulo.

        MEDIDO: essa correção existia só dentro de linkedin.py/
        linkedin_intl.py, aplicada manualmente na hora de montar o Job.
        indeed_intl.py tinha o mesmo problema (modalidade="Remoto" cravada
        direto quando o filtro nativo da URL está ligado, sem olhar o
        título) e não usava a correção — vaga híbrida do Indeed com filtro
        nativo passava como remota no perfil internacional. Import por
        scraper depende de cada um lembrar de aplicar; aqui roda pra TODO
        Job automaticamente, incluindo fonte futura que ainda nem existe.
        """
        modalidade_real = _modalidade_pelo_titulo(self.titulo)
        if modalidade_real and self.modalidade == "Remoto":
            self.modalidade = modalidade_real

    @property
    def id(self) -> str:
        """Identificador único da vaga, baseado no link (evita duplicatas).

        O hash usa o link sem query string (?utm_source=..., ?jobBoardSource=...
        etc.), porque alguns sites variam esses parâmetros entre visitas à
        mesma vaga — se entrassem no hash, a mesma vaga poderia gerar IDs
        diferentes em runs distintos e disparar notificação duplicada.
        """
        partes = urlsplit(self.link)
        link_normalizado = urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))
        return hashlib.md5(link_normalizado.encode()).hexdigest()

    @property
    def chave_secundaria(self) -> str:
        """Chave de dedup secundária: empresa + título normalizados.

        O `.id` sozinho é hash da URL — a mesma vaga publicada em fontes
        diferentes (ex: Gupy e LinkedIn, ou LinkedIn BR e LinkedIn Intl) tem
        URL diferente em cada uma, então o `.id` também diverge e a vaga
        passa como "nova" mais de uma vez. Medido: 23% de repetição (60
        registros pra 46 pares distintos). Empresa+título normalizados
        (minúsculo, sem acento) captura isso mesmo com pequena variação de
        formatação entre sites.
        """
        return f"{_normalizar(self.empresa)}|{_normalizar(self.titulo)}"

    @property
    def senioridade(self) -> str:
        """Nível classificado a partir do título (Júnior/Pleno/Sênior/...).

        Isso é só informativo pra notificação — a vaga não é excluída por
        senioridade em nenhum momento do filtro.
        """
        return _detectar_senioridade(self.titulo)

    @property
    def publicacao_antiga(self) -> bool:
        """True quando a vaga foi publicada há mais de 14 dias (mais de 2 semanas)."""
        texto = _normalizar(self.publicado_em)
        if not texto:
            return False

        from datetime import date
        m_dt = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
        if m_dt:
            try:
                d_pub = date(int(m_dt.group(3)), int(m_dt.group(2)), int(m_dt.group(1)))
                if (date.today() - d_pub).days > 14:
                    return True
            except Exception:
                pass

        m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
        if m_iso:
            try:
                d_pub = date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
                if (date.today() - d_pub).days > 14:
                    return True
            except Exception:
                pass

        if any(w in texto for w in ("mes", "ano", "month", "year")):
            return True

        m_dia = re.search(r"(\d+)\s*(?:dia|d\b)", texto)
        if m_dia:
            return int(m_dia.group(1)) > 14

        m_sem = re.search(r"(\d+)\s*(?:semana|sem\b|w\b)", texto)
        if m_sem:
            return int(m_sem.group(1)) > 2

        return False


    @property
    def escopo_remoto(self) -> set[str]:
        if self.escopo_indefinido:
            return set()
        return extrair_escopo_remoto(self.local, self.modalidade)

    def determinar_modalidade(self) -> str:
        """Classifica categoricamente a modalidade da vaga em 'remoto', 'hibrido' ou 'presencial'.
        
        Prioridade:
        1. Híbrido: se o título, modalidade ou local indicar 'híbrido' / 'hybrid' / 'semi-presencial'.
        2. Remoto: se indicar remoto, home office, teletrabalho, remote, etc., sem sinal contraditório.
        3. Presencial: se indicar presencial, on-site, ou se for atrelada a uma localidade sem menção a remoto/híbrido.
        """
        mod_norm = _normalizar(self.modalidade)
        tit_norm = _normalizar(self.titulo)
        loc_norm = _normalizar(self.local)

        # 1. Checagem de Híbrido (prevalência se qualquer campo indicar híbrido)
        if any(h in mod_norm for h in ("hibrid", "hybrid", "semi-presencial", "semipresencial")) or \
           any(h in tit_norm for h in ("hibrid", "hybrid", "semi-presencial", "semipresencial")) or \
           any(h in loc_norm for h in ("hibrid", "hybrid", "semi-presencial", "semipresencial")):
            return "hibrido"

        # 2. Checagem de Remoto
        e_rem = any(r in mod_norm for r in ("remoto", "remota", "remote", "home office", "teletrabalho", "teletrabajo", "anywhere")) or \
                _e_remoto(loc_norm) or _e_remoto(tit_norm)

        if e_rem:
            # Se o título ou local indicar explicitamente presencial/on-site, vence presencial
            if any(p in tit_norm for p in ("on-site", "onsite", "on site", "presencial")) or \
               any(p in loc_norm for p in ("on-site", "onsite", "on site", "presencial")):
                return "presencial"
            return "remoto"

        # 3. Padrão: Presencial
        return "presencial"

    def combina_com(self, regras: RegrasFiltro) -> bool:
        return self._avaliar(regras).aprovada

    def _avaliar(self, regras: RegrasFiltro) -> _Avaliacao:
        """Faz a conta completa uma vez só — combina_com() e
        pontuar_relevancia() leem o mesmo resultado."""
        if self.publicacao_antiga:
            return _Avaliacao(
                aprovada=False,
                bate_forte=False,
                bate_ambiguo=False,
                bate_ferramenta=False,
                bate_remoto=False,
                escopos=set(),
                mercado_confirmado=False,
                idioma_bateu_titulo=False,
            )

        titulo_norm = _normalizar(self.titulo)
        local_norm = _normalizar(self.local)
        modalidade_norm = _normalizar(self.modalidade)

        bate_forte = any(
            _contem_termo(_normalizar(k), titulo_norm) for k in regras.keywords_forte
        )

        bate_ambiguo = any(
            _normalizar(k) in titulo_norm for k in regras.keywords_ambiguo
        ) and any(
            _contem_termo(_normalizar(q), titulo_norm, aceitar_plural=True)
            for q in regras.qualificadores_dados
        )

        # Espelho da regra acima: ferramenta no título só vale com cargo junto.
        bate_ferramenta = any(
            _normalizar(f) in titulo_norm for f in regras.ferramentas_titulo
        ) and any(
            _contem_termo(_normalizar(q), titulo_norm, aceitar_plural=True)
            for q in regras.qualificadores_cargo
        )

        bate_keyword = bate_forte or bate_ambiguo or bate_ferramenta

        # Classificação estrita e universal da modalidade
        mod_canonica = self.determinar_modalidade()

        # Gate Estrito e Simétrico de Modalidades Aceitas
        if regras.modalidades_aceitas is not None:
            aceita_remoto = bool(regras.modalidades_aceitas.get("remoto", True))
            aceita_hibrido = bool(regras.modalidades_aceitas.get("hibrido", True))
            aceita_presencial = bool(regras.modalidades_aceitas.get("presencial", True))

            if mod_canonica == "remoto" and not aceita_remoto:
                return _Avaliacao(
                    aprovada=False,
                    bate_forte=bate_forte,
                    bate_ambiguo=bate_ambiguo,
                    bate_ferramenta=bate_ferramenta,
                    bate_remoto=False,
                    escopos=set(),
                    mercado_confirmado=False,
                    idioma_bateu_titulo=False,
                )
            if mod_canonica == "hibrido" and not aceita_hibrido:
                return _Avaliacao(
                    aprovada=False,
                    bate_forte=bate_forte,
                    bate_ambiguo=bate_ambiguo,
                    bate_ferramenta=bate_ferramenta,
                    bate_remoto=False,
                    escopos=set(),
                    mercado_confirmado=False,
                    idioma_bateu_titulo=False,
                )
            if mod_canonica == "presencial" and not aceita_presencial:
                return _Avaliacao(
                    aprovada=False,
                    bate_forte=bate_forte,
                    bate_ambiguo=bate_ambiguo,
                    bate_ferramenta=bate_ferramenta,
                    bate_remoto=False,
                    escopos=set(),
                    mercado_confirmado=False,
                    idioma_bateu_titulo=False,
                )

        _FLAGS_REMOTO = ("remoto", "remota", "remote")
        bate_remoto = (mod_canonica == "remoto")
        escopos = self.escopo_remoto if bate_remoto else set()

        if bate_remoto and regras.mercados_remoto_aceitos is not None:
            if escopos:
                mercados_aceitos_norm = {_normalizar(m) for m in regras.mercados_remoto_aceitos}
                escopos_norm = {_normalizar(e) for e in escopos}
                if not (escopos_norm & mercados_aceitos_norm):
                    bate_remoto = False

        idioma_bateu_titulo = regras.idiomas_exigidos is not None and any(
            _contem_termo(_normalizar(i), titulo_norm) for i in regras.idiomas_exigidos
        )

        if bate_remoto and regras.idiomas_exigidos is not None and not escopos:
            if not idioma_bateu_titulo:
                bate_remoto = False

        # Validação de Localização / Cidade
        if mod_canonica == "remoto":
            # Para vagas remotas, a cidade não é restritiva
            bate_cidade = bate_remoto
        else:
            # Para presenciais ou híbridas, DEVE casar com a lista de cidades aceitas
            bate_cidade = any(
                _contem_termo(_normalizar(c), local_norm)
                for c in regras.cidades
                if _normalizar(c) not in _FLAGS_REMOTO
            )

        return _Avaliacao(
            aprovada=bate_keyword and bate_cidade,
            bate_forte=bate_forte,
            bate_ambiguo=bate_ambiguo,
            bate_ferramenta=bate_ferramenta,
            bate_remoto=bate_remoto,
            escopos=escopos,
            mercado_confirmado=bate_remoto and bool(escopos),
            idioma_bateu_titulo=idioma_bateu_titulo,
        )

    def pontuar_relevancia(self, regras: RegrasFiltro) -> int:
        """Score (1 a 10 na prática) pra ORDENAR vagas que já passaram combina_com()."""
        av = self._avaliar(regras)

        if av.bate_forte:
            pontos_cargo = _PESO_CARGO_FORTE
        elif av.bate_ambiguo:
            pontos_cargo = _PESO_CARGO_AMBIGUO
        else:
            pontos_cargo = 0

        pontos_ferramenta = _PESO_FERRAMENTA if av.bate_ferramenta else 0

        nivel = self.senioridade
        nivel_norm = _normalizar(nivel)

        senioridades_alvo_raw = regras.senioridades_alvo if regras.senioridades_alvo is not None else ["Júnior", "Pleno"]
        senioridades_alvo_norm = {_normalizar(s) for s in senioridades_alvo_raw}

        if any(target in nivel_norm or nivel_norm in target for target in senioridades_alvo_norm):
            pontos_senioridade = _PESO_SENIORIDADE_ALVO
        elif nivel == "Não especificado" or nivel.startswith("Nível "):
            pontos_senioridade = _PESO_SENIORIDADE_NEUTRA
        else:
            pontos_senioridade = _PESO_SENIORIDADE_ACIMA_DO_ALVO

        if not av.bate_remoto or av.mercado_confirmado:
            pontos_mercado = _PESO_MERCADO
        else:
            pontos_mercado = _PESO_MERCADO_NAO_CONFIRMADO

        pontos_idioma = _PESO_IDIOMA if av.idioma_bateu_titulo else 0

        pref = _normalizar(regras.preferencia_modalidade or "sem_preferencia")
        mod_norm = _normalizar(self.modalidade)
        pontos_preferencia = 0
        if pref != "sem_preferencia":
            if pref == "remoto" and any(f in mod_norm for f in ("remoto", "remota", "remote")):
                pontos_preferencia = 3
            elif pref == "hibrido" and any(f in mod_norm for f in ("hibrido", "híbrido", "hybrid")):
                pontos_preferencia = 3
            elif pref == "presencial" and any(f in mod_norm for f in ("presencial", "on-site", "onsite")):
                pontos_preferencia = 3

        return (
            pontos_cargo + pontos_ferramenta + pontos_senioridade
            + pontos_mercado + pontos_idioma + pontos_preferencia
        )

    def motivo_aprovacao(self, regras: RegrasFiltro) -> str:
        """Qual sinal aprovou a vaga — só pra aparecer na notificação, não
        influencia combina_com() nem pontuar_relevancia(). MEDIDO: a
        mensagem nunca dizia qual regra bateu; via o resultado (vaga
        chegou), nunca a causa (por que ela passou) — sem isso não dá pra
        perceber, olhando as notificações, que uma keyword_ambiguo ou uma
        ferramenta específica está trazendo lixo (teria que ir direto no
        código/log pra descobrir).

        Sinal de cargo (sempre um dos três — bate_keyword exige pelo menos
        um pra aprovar), mesma prioridade de pontuar_relevancia:
        - "Cargo forte": bateu keyword inequívoca de dados/BI.
        - "Cargo ambíguo + qualificador": cargo genérico (ex: "Business
          Analyst") só aprovado por causa do qualificador junto.
        - "Ferramenta + cargo": aprovou por ferramenta no título (ex:
          "Power BI"), não por palavra de cargo.

        Mais " · idioma sem mercado" quando a vaga é remota, o texto não
        declarou mercado nenhum, e só passou no gate de geografia porque o
        idioma apareceu no título — o caminho mais frágil dos três (ver
        MEDIDO no item 03: foi exatamente esse caminho que deixava passar
        vaga sem relação nenhuma com o mercado antes da correção)."""
        av = self._avaliar(regras)
        if av.bate_forte:
            motivo = "Cargo forte"
        elif av.bate_ambiguo:
            motivo = "Cargo ambíguo + qualificador"
        else:
            motivo = "Ferramenta + cargo"
        if av.bate_remoto and not av.escopos and av.idioma_bateu_titulo:
            motivo += " · idioma sem mercado"
        return motivo

    def escopo_rejeitado_por_mercado(self, regras: RegrasFiltro) -> set[str] | None:
        """Só pra diagnóstico/log (ver utils/filtro.py) — refaz o mesmo
        cálculo do gate de mercado que combina_com() usa, sem decidir nada
        sozinho (não influencia se a vaga passa ou não). Devolve o conjunto
        de escopos declarados quando ELE é o motivo da vaga não bater
        (remota, mercado declarado no texto, nenhum mercado declarado está
        na lista aceita) — None quando não se aplica: não é remota, não
        declarou mercado nenhum, ou o mercado bateu.

        MEDIDO: sem visibilidade de QUAL escopo derrubou a vaga, um país
        mal reconhecido (texto cru tipo "lagos nigeria", não mapeado em
        _MERCADOS_REMOTO) só aparece pro funil como "menos uma filtrada" —
        indistinguível de qualquer outro descarte. Foi assim que o bug do
        item 01 (escopo virando allowlist) passou despercebido até virar
        relato explícito.
        """
        if regras.mercados_remoto_aceitos is None:
            return None
        modalidade_norm = _normalizar(self.modalidade)
        _FLAGS_REMOTO = ("remoto", "remota", "remote")
        quer_remoto = any(_normalizar(c) in _FLAGS_REMOTO for c in regras.cidades)
        if not (quer_remoto and modalidade_norm in ("remoto", "remota")):
            return None
        escopos = self.escopo_remoto
        if not escopos:
            return None
        mercados_aceitos_norm = {_normalizar(m) for m in regras.mercados_remoto_aceitos}
        escopos_norm = {_normalizar(e) for e in escopos}
        if escopos_norm & mercados_aceitos_norm:
            return None
        return escopos