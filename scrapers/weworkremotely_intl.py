
import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from job import Job, extrair_data_publicacao
from logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()


class WeWorkRemotelyIntlScraper(BaseScraper):
    """Agregador de vaga 100% remota internacional (weworkremotely.com) —
    opção 2 do eixo internacional: cobertura melhor pro "remoto
    internacional" que LinkedIn/Indeed, mas foco em anúncio pago/curado, não
    aparelho de busca nacional por país. Sem filtro de idioma na própria
    busca (o site não separa por PT/ES) — a filtragem de cargo (KEYWORDS_INTL)
    já reduz bastante o ruído, e cards que não são vaga de verdade (anúncio
    promovido de outra categoria) simplesmente não batem no título.
    """

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[WeWorkRemotely Intl] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[WeWorkRemotely Intl] Buscando: {termo}")
        vagas: list[Job] = []
        termo_url = quote_plus(termo)
        url = f"https://weworkremotely.com/remote-jobs/search?term={termo_url}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            # MEDIDO ao vivo (Claude in Chrome): endpoint e seletor estão
            # certos — /remote-jobs/search?term=data+analyst devolve vaga
            # real ("Data Analyst – AI Translation Quality"), e
            # `li.new-listing-container` bate 6 elementos na hora, sem
            # nenhuma espera. O 0 resultado consistente de produção não é
            # busca errada, então sobra bloqueio anti-bot ao request
            # automatizado — igual já documentado no docstring da classe
            # pra qualquer fonte. Único scraper deste projeto sem essa
            # linha (indeed_intl.py e catho.py já mascaram); adicionando
            # aqui também. Não tenho como confirmar 100% que resolve sem
            # rodar Playwright de verdade (sandbox não baixa o browser) —
            # confirmar no próximo ciclo real.
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
            )

            try:
                page.goto(url, timeout=60000)
                # MEDIDO: 21 execuções em produção, 0 vaga em todas.
                # Confirmado ao vivo (fetch HTTP puro + inspeção de DOM via
                # Chrome) que a URL e o seletor CONTINUAM corretos — o
                # conteúdo vem renderizado no servidor (já está no HTML
                # antes de qualquer JS rodar), não é SPA que precisa
                # esperar client-side render. `wait_for_selector` sem
                # `state` explícito espera "visible" por padrão — mesma
                # categoria de bug já visto e corrigido no Indeed Intl
                # (ver FILTRO_REMOTO/state="attached" nesse scraper).
                # "attached" é suficiente aqui porque o card já existe no
                # DOM assim que goto() retorna, sem precisar esperar
                # pintura completa.
                #
                # MEDIDO: o except em volta do wait_for_selector original
                # capturava QUALQUER exceção (timeout incluído) e logava
                # "0 resultados" pra todas — sem diferenciar "site
                # confirmou zero vaga" de "não consegui nem confirmar".
                # Confirmado ao vivo (Claude in Chrome): busca sem
                # resultado nenhum (termo inexistente) renderiza
                # <div class="advanced_no_results"> no DOM — sinal
                # estrutural estável, não depende de texto em inglês que
                # pode mudar. Esperando os dois seletores ao mesmo tempo:
                # se nenhum aparecer em 15s, é timeout/bloqueio de
                # verdade (warning, não "0 resultados"); se
                # advanced_no_results aparecer e não houver card, é zero
                # confirmado pelo próprio site.
                try:
                    page.wait_for_selector(
                        "li.new-listing-container, div.advanced_no_results",
                        state="attached",
                        timeout=15000,
                    )
                except Exception:
                    logger.warning(
                        f"[WeWorkRemotely Intl] Timeout em '{termo}' — nem vaga nem "
                        "confirmação de busca vazia apareceu em 15s (possível "
                        "bloqueio/anti-bot, não é 0 vaga confirmado)."
                    )
                    return vagas
                time.sleep(2)

                cards = page.query_selector_all("li.new-listing-container")
                if not cards:
                    logger.info(f"[WeWorkRemotely Intl] 0 resultados confirmados para '{termo}'.")
                    return vagas

                for card in cards:
                    try:
                        titulo_el = card.query_selector(".new-listing__header__title")
                        if not titulo_el:
                            continue
                        titulo = titulo_el.inner_text().strip()

                        empresa_el = card.query_selector(".new-listing__company-name")
                        empresa = empresa_el.inner_text().strip() if empresa_el else "Não informado"

                        # Todo anúncio do WeWorkRemotely já é vaga remota por
                        # definição (é a proposta do site) — modalidade="Remoto"
                        # direto, sem precisar embutir isso em `local`. O campo
                        # abaixo é a sede da empresa, não a modalidade — fica
                        # como informação pura de local, sem hack de texto.
                        #
                        # MEDIDO: sede da empresa NÃO é o mercado onde a vaga
                        # contrata (ex: empresa sediada em San Francisco pode
                        # contratar candidato de qualquer lugar). Desde que
                        # extrair_escopo_remoto passou a usar `local` inteiro
                        # como escopo quando `modalidade` já confirma remoto
                        # (ver Job.escopo_remoto em job.py), guardar a sede
                        # aqui faria vaga remota mundial ser barrada pelo
                        # endereço da empresa. `escopo_indefinido=True` abaixo
                        # tira esse campo da checagem de mercado, sem deixar
                        # de exibir a sede na notificação.
                        sede_el = card.query_selector(".new-listing__company-headquarters")
                        sede = sede_el.inner_text().strip() if sede_el else "Não informado"

                        link_el = card.query_selector('a[href^="/remote-jobs/"]')
                        link = link_el.get_attribute("href") if link_el else None
                        if not link:
                            continue
                        link = f"https://weworkremotely.com{link.split('?')[0]}"

                        publicado_em = extrair_data_publicacao(card.inner_text())

                        vagas.append(Job(
                            titulo=titulo,
                            empresa=empresa,
                            local=sede,
                            link=link,
                            site="We Work Remotely",
                            publicado_em=publicado_em,
                            modalidade="Remoto",
                            escopo_indefinido=True,
                        ))
                    except Exception as e:
                        logger.warning(f"[WeWorkRemotely Intl] Erro ao processar card: {e}")
                        continue

            except Exception as e:
                logger.error(f"[WeWorkRemotely Intl] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
