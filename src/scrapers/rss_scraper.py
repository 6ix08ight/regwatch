import feedparser
import logging
from base_scraper import BaseScraper

class RssScraper(BaseScraper):
    """
    Scraper dedykowany dla kanałów RSS (np. EBA, FSMA).
    Wykorzystuje feedparser do pobierania tytułów i linków.
    """
    def scrape(self) -> list[dict]:
        """Główna metoda pobierająca nowości z kanału RSS."""
        logging.info(f"Rozpoczynam pobieranie RSS: {self.name} ({self.url})...")

        if not self._is_allowed_by_robots(self.url):
            return []

        self._delay()

        try:
            feed = feedparser.parse(self.url)
        except Exception as e:
            logging.error(f"[{self.name}] Błąd parsowania RSS {self.url}: {e}")
            return []

        # Jeśli feed nie zawiera wpisów, logujemy ostrzeżenie
        if not feed.entries:
            logging.warning(f"[{self.name}] Kanał RSS nie zwrócił żadnych wpisów.")
            return []

        results = []
        for entry in feed.entries:
            title = entry.get('title', 'No Title')
            url = entry.get('link', '')
            pub_date = entry.get('published', entry.get('updated', ''))

            item = {
                'source': self.name,
                'title': title,
                'url': url,
                'publication_date': pub_date,
                'full_text': entry.get('summary', entry.get('description', '')),
                'language': self.lang,
                'country': self.country,
                'content_hash': self._compute_hash(title, url, pub_date)
            }
            results.append(item)

        logging.info(f"Znaleziono {len(results)} wpisów w RSS {self.name}.")
        return results
