from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
from base_scraper import BaseScraper

class WebScraper(BaseScraper):
    """
    Uniwersalny scraper stron WWW oparty na selektorach CSS z konfiguracji.
    Selektory odczytywane z sekcji 'selectors' w sources.yaml.
    """
    def scrape(self) -> list[dict]:
        """Pobiera nowości ze strony HTML na podstawie selektorów z konfiga."""
        # Sprawdzenie, czy źródło ma zdefiniowane selektory
        selectors = self.config.get('selectors')
        if not selectors:
            logging.warning(f"[{self.name}] Brak selektorów CSS w konfiguracji — pomijam.")
            return []

        logging.info(f"Rozpoczynam scrapowanie: {self.name} ({self.url})...")

        # Pobieranie strony za pomocą metody z klasy bazowej (z retry)
        html = self.get_page_content()
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # Szukamy kafelków nowości wg selektora 'item' z konfiga
        items = soup.select(selectors['item'])

        for item in items:
            # 1. Tytuł — selektor 'title'
            title_node = item.select_one(selectors['title'])
            title = title_node.get_text(strip=True) if title_node else 'No Title'

            # 2. Link — atrybut z selektora 'link_attr' (zazwyczaj 'href')
            link_attr = selectors.get('link_attr', 'href')
            url = item.get(link_attr, '')
            # Naprawiamy linki względne (np. /en/news/... → https://...)
            if url and not url.startswith('http'):
                url = urljoin(self.url, url)

            # 3. Data — selektor 'date'
            date_node = item.select_one(selectors['date'])
            pub_date = date_node.get_text(strip=True) if date_node else 'Unknown Date'

            result = {
                'source': self.name,
                'title': title,
                'url': url,
                'publication_date': pub_date,
                'full_text': title,  # W POC tekst to na razie sam tytuł
                'language': self.lang,
                'country': self.country,
                'content_hash': self._compute_hash(title, url, pub_date)
            }
            results.append(result)

        logging.info(f"Znaleziono {len(results)} wpisów na {self.name}.")
        return results
