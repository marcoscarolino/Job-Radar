
import re
import time
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from job import Job, extrair_data_publicacao
from logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

_MODALIDADES = {"presencial", "híbrido", "hibrido", "remoto"}

# Ver comentário equivalente em scrapers/gupy.py: só a 1a página nunca
# alcançava vaga de cidade menor (Recife, Natal, Maceió etc.).
MAX_PAGINAS = 3


def _empresa_da_url(path: str) -> str:
    """A listagem não mostra o nome da empresa, só o slug na URL
    (/pt/{empresa}/jobs/{vaga}). Deriva um nome legível a partir dele."""
    partes = path.strip("/").split("/")
    if len(partes) >= 2:
        slug = partes[1]
        return slug.replace("-", " ").title()
    return "Não informado"


class GeekHunterScraper(BaseScraper):
    """Busca vagas no https://www.geekhunter.com/pt/vagas."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[GeekHunter] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[GeekHunter] Buscando: {termo}")
        vagas: list[Job] = []
        # quote_plus (não um .replace(" ", "+") manual) porque termo pode ter
        # caractere reservado de query string — ex: "BI & Analytics Analyst"
        # tem "&", que sem escapar cortaria a URL no meio e criaria um
        # parâmetro falso, quebrando a busca silenciosamente pra esse termo.
        termo_url = quote_plus(termo)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                for pagina in range(1, MAX_PAGINAS + 1):
                    url = f"https://www.geekhunter.com/pt/vagas?searchTerm={termo_url}&page={pagina}"
                    page.goto(url, timeout=60000)
                    sem_resultados = False
                    try:
                        page.wait_for_selector('a[href*="/jobs/"]', timeout=15000)
                    except PlaywrightTimeoutError:
                        if pagina > 1:
                            # Ver comentário equivalente em scrapers/gupy.py: timeout
                            # de verdade é DIFERENTE de "acabaram as vagas" (isso é
                            # sinalizado abaixo, quando a página carrega normal mas
                            # devolve 0 cards). Sem separar os dois, a perda por
                            # timeout ficava invisível — virava break silencioso
                            # idêntico ao fim natural da paginação.
                            logger.warning(
                                f"[GeekHunter] Timeout esperando resultados na página "
                                f"{pagina} de '{termo}' — parando de paginar por falha "
                                "de carregamento, não por fim real dos resultados. "
                                "Pode ter ficado vaga de página seguinte de fora."
                            )
                            break
                        if "0 vagas disponíveis" in page.inner_text("body"):
                            logger.info(f"[GeekHunter] 0 resultados reais para '{termo}'.")
                            sem_resultados = True
                        else:
                            raise
                    if not sem_resultados:
                        time.sleep(2)

                    cards = [] if sem_resultados else page.query_selector_all('a[href*="/jobs/"]')
                    if not cards:
                        break

                    for card in cards:
                        try:
                            linhas = [l.strip() for l in card.inner_text().split("\n") if l.strip()]
                            if not linhas:
                                continue
                            titulo = linhas[0]

                            modalidade = ""
                            cidade = ""
                            for linha in linhas[1:]:
                                if linha.lower() in _MODALIDADES:
                                    modalidade = linha.capitalize()
                                elif re.match(r"^🇧🇷", linha):
                                    cidade = linha.replace("🇧🇷", "").strip()

                            local = cidade or "Não informado"

                            link = card.get_attribute("href")
                            if not link:
                                continue

                            path = urlparse(link).path if link.startswith("http") else link
                            empresa = _empresa_da_url(path)

                            if link.startswith("/"):
                                link = f"https://www.geekhunter.com{link}"

                            publicado_em = extrair_data_publicacao(card.inner_text())

                            vagas.append(Job(
                                titulo=titulo,
                                empresa=empresa,
                                local=local,
                                link=link,
                                site="GeekHunter",
                                publicado_em=publicado_em,
                                modalidade=modalidade,
                            ))
                        except Exception as e:
                            logger.warning(f"[GeekHunter] Erro ao processar card: {e}")
                            continue

                    if sem_resultados:
                        break

            except Exception as e:
                logger.error(f"[GeekHunter] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
