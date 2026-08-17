
from __future__ import annotations

import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from job import Job, _e_remoto, _normalizar, extrair_data_publicacao
from logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

# Ver comentário equivalente em scrapers/gupy.py: só a 1a página nunca
# alcançava vaga de cidade menor (Recife, Natal, Maceió etc.). O Indeed
# pagina via &start= (10 vagas por página).
MAX_PAGINAS = 3


class IndeedScraper(BaseScraper):
    """Busca vagas no https://br.indeed.com.

    Aviso: o Indeed tem proteção anti-bot (Cloudflare) que pode bloquear
    acessos automatizados repetidos, mesmo que o scraping funcione em testes
    manuais. Se começar a retornar 0 vagas de forma consistente, é provável
    bloqueio, não erro de seletor.
    """

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[Indeed] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Indeed] Buscando: {termo}")
        vagas: list[Job] = []
        # quote_plus em vez de .replace(" ", "+") manual: termo pode ter "&"
        # (ex: "BI & Analytics Analyst"), que sem escapar quebra a query
        # string no meio e corrompe a busca silenciosamente.
        termo_url = quote_plus(termo)

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
                for pagina in range(MAX_PAGINAS):
                    start = pagina * 10
                    url = f"https://br.indeed.com/jobs?q={termo_url}&l=&start={start}"
                    page.goto(url, timeout=60000)
                    try:
                        page.wait_for_selector(".job_seen_beacon", state="attached", timeout=25000)
                    except PlaywrightTimeoutError:
                        # Timeout de verdade (site lento, bloqueio anti-bot) é
                        # DIFERENTE de "acabaram as vagas" — isso é sinalizado
                        # abaixo, quando a página carrega normal mas devolve 0
                        # cards. Sem essa distinção, um timeout em qualquer
                        # página (inclusive a 1a) virava break silencioso
                        # idêntico ao fim natural da paginação, e o aviso de
                        # "possível bloqueio anti-bot" nunca chegava a disparar
                        # — justamente no caso em que ele mais importa.
                        logger.warning(
                            f"[Indeed] Timeout esperando resultados na página {pagina + 1} "
                            f"de '{termo}' — parando de paginar por falha de carregamento "
                            "(possível bloqueio anti-bot), não por fim real dos resultados. "
                            "Pode ter ficado vaga de fora."
                        )
                        break
                    time.sleep(2)

                    cards = page.query_selector_all(".job_seen_beacon")
                    if not cards:
                        if pagina == 0:
                            logger.warning("[Indeed] Nenhum card encontrado — possível bloqueio anti-bot.")
                        break

                    for card in cards:
                        try:
                            titulo_el = card.query_selector("h3.jobTitle a.jcs-JobTitle span")
                            if not titulo_el:
                                titulo_el = card.query_selector("h3.jobTitle")
                            if not titulo_el:
                                continue
                            titulo = titulo_el.inner_text().strip()

                            empresa_el = card.query_selector('[data-testid="company-name"]')
                            empresa = empresa_el.inner_text().strip() if empresa_el else "Não informado"

                            local_el = card.query_selector('[data-testid="text-location"]')
                            local = local_el.inner_text().strip() if local_el else "Não informado"

                            # Indeed não tem campo de modalidade separado no
                            # card — às vezes o próprio texto de local já diz
                            # "Remoto"/"Home office" organicamente. Detecta uma
                            # vez aqui, na extração, em vez de deixar pro
                            # filtro reparsear `local` toda vez.
                            modalidade = "Remoto" if _e_remoto(_normalizar(local)) else ""

                            link_el = card.query_selector("a[data-jk]")
                            jk = link_el.get_attribute("data-jk") if link_el else None
                            if not jk:
                                continue
                            link = f"https://br.indeed.com/viewjob?jk={jk}"

                            publicado_em = extrair_data_publicacao(card.inner_text())

                            vagas.append(Job(
                                titulo=titulo,
                                empresa=empresa,
                                local=local,
                                link=link,
                                site="Indeed",
                                publicado_em=publicado_em,
                                modalidade=modalidade,
                            ))
                        except Exception as e:
                            logger.warning(f"[Indeed] Erro ao processar card: {e}")
                            continue

            except Exception as e:
                logger.error(f"[Indeed] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
