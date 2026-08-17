
import time

from playwright.sync_api import sync_playwright

from job import Job, _e_remoto, _normalizar, extrair_data_publicacao
from logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()


def _slug(termo: str) -> str:
    return termo.strip().lower().replace(" ", "-")


class CathoScraper(BaseScraper):
    """Busca vagas no https://www.catho.com.br.

    Observação sobre modalidade: o Catho NÃO tem parâmetro de URL pra filtro
    de remoto — testei ao vivo (checkbox "Home Office" em Modalidade +
    "Confirmar") e a URL nunca muda, é filtro client-side sem reflexo
    navegável. Só que não precisa disso: as próprias vagas remotas do Catho
    já anunciam isso no TÍTULO ("Work From Home Data Analyst", "Trabalhe de
    Casa Analista de Business Intelligence" — confirmado ao vivo, inclusive
    aparecendo já na busca sem filtro nenhum aplicado). Por isso, em vez de
    automatizar o filtro (frágil, seletor duplicado por categoria de filtro)
    ou abrir cada vaga (caro), verifica o sinal de remoto no título e, se
    achar, marca isso no campo `modalidade` (não em `local` — local guarda só
    a cidade que o card mostra, mesmo pra vaga remota).
    """

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[Catho] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Catho] Buscando: {termo}")
        vagas: list[Job] = []
        url = f"https://www.catho.com.br/vagas/{_slug(termo)}/"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            # Alguns sites detectam automação verificando navigator.webdriver.
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
            )

            try:
                page.goto(url, timeout=60000)
                page.wait_for_selector("article", state="attached", timeout=25000)
                time.sleep(2)

                cards = page.query_selector_all("article")
                for card in cards:
                    try:
                        titulo_el = card.query_selector("h2 a")
                        if not titulo_el:
                            continue
                        titulo = titulo_el.inner_text().strip()

                        link = titulo_el.get_attribute("href")
                        if not link:
                            continue
                        if link.startswith("/"):
                            link = f"https://www.catho.com.br{link}"

                        paragrafos = card.query_selector_all("p")
                        empresa = "Não informado"
                        if paragrafos:
                            empresa = paragrafos[0].inner_text().split("Por que")[0].strip()
                            empresa = empresa or "Não informado"

                        local = "Não informado"
                        if len(paragrafos) > 1:
                            texto_local = paragrafos[1].inner_text()
                            if "-" in texto_local:
                                local = texto_local.split("-")[-1].strip()

                        # Título já entrega o sinal de remoto que o card não
                        # expõe em campo próprio (ver docstring da classe).
                        # Sem distinção híbrido/presencial possível por essa via.
                        modalidade = ""
                        if _e_remoto(_normalizar(titulo)) or _e_remoto(_normalizar(local)):
                            modalidade = "Remoto"

                        publicado_em = extrair_data_publicacao(card.inner_text())

                        vagas.append(Job(
                            titulo=titulo,
                            empresa=empresa,
                            local=local,
                            link=link,
                            site="Catho",
                            publicado_em=publicado_em,
                            modalidade=modalidade,
                        ))
                    except Exception as e:
                        logger.warning(f"[Catho] Erro ao processar card: {e}")
                        continue

            except Exception as e:
                logger.error(f"[Catho] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
