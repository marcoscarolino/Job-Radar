
import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from job import Job, extrair_data_publicacao
from logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

_MODALIDADES = {"remota", "híbrida", "hibrida", "presencial"}


class Jobs99Scraper(BaseScraper):
    """Busca vagas no https://www.99jobs.com."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[99Jobs] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[99Jobs] Buscando: {termo}")
        vagas: list[Job] = []
        # quote_plus em vez de .replace(" ", "+") manual: termo pode ter "&"
        # (ex: "BI & Analytics Analyst"), que sem escapar quebra a query
        # string no meio e corrompe a busca silenciosamente.
        termo_url = quote_plus(termo)
        url = f"https://www.99jobs.com/opportunities/filtered_search?search%5Bterm%5D={termo_url}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
            )

            try:
                page.goto(url, timeout=60000)
                sem_resultados = False
                try:
                    page.wait_for_selector("a.opportunity-card", state="attached", timeout=25000)
                except Exception:
                    # page.content() é o HTML bruto — o "0" e "oportunidades" ficam
                    # em elementos separados ali, então nunca batiam como texto
                    # contíguo. inner_text() reflete o texto renderizado (como
                    # aparece na tela), que é onde essa frase realmente é contígua.
                    texto_pagina = page.inner_text("body")
                    if "oportunidades para o termo" in texto_pagina:
                        logger.info(f"[99Jobs] 0 resultados reais para '{termo}'.")
                        sem_resultados = True
                    else:
                        raise

                cards = [] if sem_resultados else page.query_selector_all("a.opportunity-card")
                if cards:
                    time.sleep(2)
                for card in cards:
                    try:
                        titulo_el = card.query_selector("h1")
                        if not titulo_el:
                            continue
                        titulo = titulo_el.inner_text().strip()

                        empresa_el = card.query_selector("h2")
                        empresa = empresa_el.inner_text().strip() if empresa_el else "Não informado"

                        cidade_el = card.query_selector("p")
                        cidade = " ".join(cidade_el.inner_text().split()) if cidade_el else "Não informado"

                        modalidade = ""
                        for span in card.query_selector_all("span"):
                            texto_span = span.inner_text().strip()
                            if texto_span.lower() in _MODALIDADES:
                                modalidade = texto_span
                                break

                        link = card.get_attribute("href")
                        if not link:
                            continue
                        if link.startswith("/"):
                            link = f"https://www.99jobs.com{link}"

                        publicado_em = extrair_data_publicacao(card.inner_text())

                        vagas.append(Job(
                            titulo=titulo,
                            empresa=empresa,
                            local=cidade,
                            link=link,
                            site="99Jobs",
                            publicado_em=publicado_em,
                            modalidade=modalidade,
                        ))
                    except Exception as e:
                        logger.warning(f"[99Jobs] Erro ao processar card: {e}")
                        continue

            except Exception as e:
                logger.error(f"[99Jobs] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
