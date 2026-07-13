from .base_scraper import BaseScraper
from .rss_scraper import RssScraper
from .web_scraper import WebScraper
from .api_scraper import ApiScraper

# Mapowanie: wartość 'strategy' z sources.yaml → klasa scrapera
SCRAPER_STRATEGIES = {
    'rss': RssScraper,
    'requests': WebScraper,
    'api': ApiScraper,
    'manual': None,    # Pomijane w automatyzacji
}
