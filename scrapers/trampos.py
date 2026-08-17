
import re
import time

from playwright.sync_api import sync_playwright

from job import Job, _e_remoto, _normalizar, extrair_data_publicacao
from logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

_PREFIXOS_TIPO = re.compile(r"^(EMPREGO|EST[ÁA]GIO|FREELA|BANCO DE TALENTOS)", re.IGNORECASE)

# Ver comentário equivalente em scrapers/gupy.py: só a 1a página nunca
# alcançava vaga de cidade menor (Recife, Natal, Maceió etc.). O Trampos não
# pagina por URL — o botão "Mostre-me mais vagas!" carrega mais resultados
# via JS (AJAX), então paginamos clicando nele em vez de trocar a URL.
MAX_CLIQUES_MAIS_VAGAS = 2


class TramposScraper(BaseScraper):
    """Busca vagas no https://trampos.co (job board de tecnologia/comunicação)."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[Trampos] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Trampos] Buscando: {termo}")
        vagas: list[Job] = []
        url = f"https://trampos.co/oportunidades/?tr={termo.replace(' ', '%20')}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                page.goto(url, timeout=60000)
                sem_resultados = False
                try:
                    page.wait_for_selector(".opportunity-box a", timeout=15000)
                except Exception:
                    if "página 1 de 0" in page.inner_text("body"):
                        logger.info(f"[Trampos] 0 resultados reais para '{termo}'.")
                        sem_resultados = True
                    else:
                        raise
                if not sem_resultados:
                    time.sleep(2)
                    for _ in range(MAX_CLIQUES_MAIS_VAGAS):
                        botao = page.query_selector('a:has-text("Mostre-me mais vagas")')
                        if not botao:
                            break  # já é a última página, botão some
                        try:
                            botao.click()
                            time.sleep(2)
                        except Exception:
                            break

                cards = [] if sem_resultados else page.query_selector_all(".opportunity-box a")
                for card in cards:
                    try:
                        titulo_el = card.query_selector("h4")
                        if not titulo_el:
                            continue
                        titulo = titulo_el.inner_text().strip()

                        empresa_el = card.query_selector("h5")
                        empresa = empresa_el.inner_text().strip() if empresa_el else ""
                        if not empresa:
                            empresa = "Não informado"

                        linhas = [l.strip() for l in card.inner_text().split("\n") if l.strip()]
                        local = "Não informado"
                        for linha in linhas[1:]:
                            if _PREFIXOS_TIPO.match(linha):
                                local = _PREFIXOS_TIPO.sub("", linha).strip()
                                break

                        # Sem campo de modalidade próprio no card — mesmo
                        # sinal usado nos outros scrapers sem seletor
                        # dedicado, aplicado uma vez aqui na extração.
                        modalidade = "Remoto" if _e_remoto(_normalizar(local)) else ""

                        link = card.get_attribute("href")
                        if not link:
                            continue
                        if link.startswith("/"):
                            link = f"https://trampos.co{link}"

                        publicado_em = extrair_data_publicacao(card.inner_text())

                        vagas.append(Job(
                            titulo=titulo,
                            empresa=empresa,
                            local=local,
                            link=link,
                            site="Trampos",
                            publicado_em=publicado_em,
                            modalidade=modalidade,
                        ))
                    except Exception as e:
                        logger.warning(f"[Trampos] Erro ao processar card: {e}")
                        continue

            except Exception as e:
                logger.error(f"[Trampos] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
