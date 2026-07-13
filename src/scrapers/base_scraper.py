import hashlib
import time
import logging
import requests
import urllib.robotparser
from urllib.parse import urlparse
from abc import ABC, abstractmethod

# Konfiguracja logowania zdarzeń
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# UWAGA (POC): Brief wymaga respektowania robots.txt.
# W wersji POC pomijamy to świadomie — wszystkie nasze źródła to publiczne
# strony urzędów regulacyjnych, które udostępniają dane do monitorowania.
# W wersji produkcyjnej należy dodać sprawdzanie robots.txt przed każdym zapytaniem
# (np. za pomocą biblioteki 'urllib.robotparser').

class BaseScraper(ABC):
    """
    Abstrakcyjna klasa bazowa dla wszystkich scraperów regulacyjnych.
    Zapewnia wspólne mechanizmy: pobieranie stron, hash, rate limiting, retry.
    """
    def __init__(self, source_config: dict):
        self.config = source_config
        self.name = source_config.get('name', 'Unknown Source')
        self.url = source_config.get('url')
        self.country = source_config.get('country', 'EU')
        self.lang = source_config.get('lang', 'en')
        
        # Profesjonalny nagłówek User-Agent zgodnie z briefem
        self.headers = {
            'User-Agent': "RegWatch/1.0 (Regulatory Monitoring Tool)"
        }

    @abstractmethod
    def scrape(self) -> list[dict]:
        """Metoda, która musi zostać zaimplementowana w klasach pochodnych."""
        pass

    def get_page_content(self, url=None):
        """
        Pobiera zawartość strony HTML.
        - Sprawdza robots.txt przed pobraniem
        - Rate limiting: 2 sekundy opóźnienia przed zapytaniem
        - Retry: 1 powtórzenie po 3 sekundach w razie błędu
        - Timeout: 15 sekund
        Zwraca tekst HTML lub None w razie niepowodzenia.
        """
        target_url = url or self.url
        
        if not self._is_allowed_by_robots(target_url):
            return None
            
        self._delay()

        for attempt in range(2):  # Maksymalnie 2 próby (oryginalna + 1 retry)
            try:
                response = requests.get(target_url, headers=self.headers, timeout=15)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                if attempt == 0:
                    # Pierwsza porażka — czekamy 3 sekundy i próbujemy jeszcze raz
                    logging.warning(f"[{self.name}] Błąd pobierania {target_url}: {e}. Ponawiam za 3s...")
                    time.sleep(3)
                else:
                    # Druga porażka — logujemy i rezygnujemy
                    logging.error(f"[{self.name}] Nie udało się pobrać {target_url} po 2 próbach: {e}")
                    return None

    def _compute_hash(self, title, url, pub_date):
        """Generuje unikalny identyfikator SHA-256 dla dokumentu."""
        unique_str = f"{title}|{url}|{pub_date}"
        return hashlib.sha256(unique_str.encode('utf-8')).hexdigest()

    def _delay(self):
        """Mechanizm opóźniający zapytania - chroni przed zablokowaniem IP."""
        time.sleep(2)

    def _is_allowed_by_robots(self, url):
        """Sprawdza czy robots.txt pozwala na scrapowanie danego URL."""
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        robots_url = f"{base_url}/robots.txt"
        
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
            is_allowed = rp.can_fetch(self.headers['User-Agent'], url)
            if not is_allowed:
                logging.warning(f"[{self.name}] Scrapowanie {url} zablokowane przez robots.txt!")
            return is_allowed
        except Exception:
            # Jeśli nie ma robots.txt lub jest błąd 404, zakładamy zgodę
            return True
