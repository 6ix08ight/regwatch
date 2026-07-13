import yaml
import os
import sys
import json
import sqlite3
import webbrowser
from datetime import datetime, timedelta

# Dodajemy foldery do ścieżki importu relatywnie do ścieżki pliku
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(base_dir, 'src'))
sys.path.append(os.path.join(base_dir, 'src/scrapers'))

from tracker import Tracker
from analyzer import Analyzer
from report_generator import ReportGenerator
from scrapers import SCRAPER_STRATEGIES

def run_pipeline():
    # --- ETAP 0: Inicjalizacja ---
    tracker = Tracker()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, 'config', 'sources.yaml')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        sources = yaml.safe_load(f)
        
    active_sources = [s for s in sources if s.get('enabled')]
    source_status = []

    # --- ETAP 1: Pobieranie (Scraping) ---
    print(f"\n[ ETAP 1 ] Scraping {len(active_sources)} źródeł...")
    
    for source_cfg in active_sources:
        strategy = source_cfg.get('strategy')
        scraper_class = SCRAPER_STRATEGIES.get(strategy)
        
        if not scraper_class:
            source_status.append({"name": source_cfg['name'], "icon": "⏭️"})
            continue
            
        try:
            scraper = scraper_class(source_cfg)
            scraped_items = scraper.scrape()
            
            new_count_source = 0
            for item in scraped_items:
                if tracker.is_new(item['content_hash']):
                    tracker.save_scraped(item)
                    new_count_source += 1
            
            source_status.append({"name": source_cfg['name'], "icon": "✅"})
            print(f"  OK: {source_cfg['name']} (znaleziono {len(scraped_items)}, nowych: {new_count_source})")
        except Exception as e:
            source_status.append({"name": source_cfg['name'], "icon": "❌"})
            print(f"  Błąd w {source_cfg['name']}: {e}")

    # --- ETAP 2: Analiza (AI) ---
    unanalyzed = tracker.get_unanalyzed()
    if unanalyzed:
        print(f"\n[ ETAP 2 ] Analiza AI (limit 5 z {len(unanalyzed)})...")
        try:
            analyzer = Analyzer()
            items_to_process = unanalyzed[:5] # Testowy limit
            
            for item in items_to_process:
                print(f"  Analizuję: {item['title'][:60]}...")
                analysis = analyzer.analyze(item)
                tracker.save_analysis(item['content_hash'], analysis)
        except Exception as e:
            print(f"  Błąd inicjalizacji/analizy AI: {e}")
    else:
        print("\n[ ETAP 2 ] Brak nowych aktów do przeanalizowania.")

    # --- ETAP 3: Generowanie Raportu ---
    print("\n[ ETAP 3 ] Generowanie raportu HTML...")
    
    # Pobieramy przeanalizowane z bazy (wszystkie dla tego raportu POC)
    conn = sqlite3.connect(tracker.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM acts WHERE llm_analyzed = 1 ORDER BY date_scraped DESC")
    rows = cursor.fetchall()
    
    new_acts = []
    stats = {"total_sources": len(active_sources), "new_count": 0, "high_urgency": 0, "medium_urgency": 0, "low_urgency": 0}
    
    for row in rows:
        act = dict(row)
        # Przywracamy listy z formatu JSON w bazie
        act['affected_areas'] = json.loads(act['affected_areas'] or '[]')
        act['compliance_checklist'] = json.loads(act['compliance_checklist'] or '[]')
        act['jurisdictions'] = json.loads(act['jurisdictions'] or '[]')
        
        new_acts.append(act)
        stats['new_count'] += 1
        
        urgency = str(act.get('urgency', '')).upper()
        if urgency == 'HIGH': stats['high_urgency'] += 1
        elif urgency == 'MEDIUM': stats['medium_urgency'] += 1
        elif urgency == 'LOW': stats['low_urgency'] += 1

    report_data = {
        "date_range": datetime.now().strftime("%d %B %Y"),
        "stats": stats,
        "deadlines": [], # Filtrowanie po terminach dodamy w finalnej wersji
        "new_acts": new_acts,
        "flagged": [],
        "source_status": source_status
    }

    generator = ReportGenerator()
    paths = generator.generate(report_data)
    
    print(f"\nRaport gotowy: {paths['html']}")
    print("Otwieram w przeglądarce...")
    
    # Automatyczne otwarcie pliku HTML (na Macu)
    os.system(f"open {paths['html']}")

if __name__ == "__main__":
    run_pipeline()
