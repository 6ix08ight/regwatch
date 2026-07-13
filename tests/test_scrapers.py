import sys
import os
import yaml

# Dodajemy folder 'src/scrapers' do ścieżki importów relatywnie do tego pliku
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(base_dir, 'src', 'scrapers'))

from rss_scraper import RssScraper
from web_scraper import WebScraper

# Mapowanie strategii na klasy (to samo co w __init__.py)
STRATEGY_MAP = {
    'rss': RssScraper,
    'requests': WebScraper,
}

def load_sources():
    """Ładuje konfigurację źródeł z pliku YAML."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, 'config', 'sources.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def test_source(source_config):
    """Testuje pojedyncze źródło i wyświetla wyniki."""
    strategy = source_config.get('strategy')
    scraper_class = STRATEGY_MAP.get(strategy)

    if not scraper_class:
        return  # Pomijamy api/manual — jeszcze nie zaimplementowane

    scraper = scraper_class(source_config)
    results = scraper.scrape()

    print(f"\n=== {source_config['name']} ({strategy}) — {len(results)} wyników ===")
    for res in results[:3]:
        print(f"  TYTUŁ: {res['title']}")
        if res.get('publication_date'):
            print(f"  DATA:  {res['publication_date']}")
        print(f"  LINK:  {res['url']}")
        print()

if __name__ == "__main__":
    sources = load_sources()

    # Testujemy tylko źródła oznaczone jako enabled
    enabled = [s for s in sources if s.get('enabled')]
    print(f"Znaleziono {len(enabled)} aktywnych źródeł. Rozpoczynam testy...\n")

    for source in enabled:
        try:
            test_source(source)
        except Exception as e:
            print(f"\n!!! BŁĄD w {source['name']}: {e}\n")

    print("=== WSZYSTKIE TESTY ZAKOŃCZONE ===")
