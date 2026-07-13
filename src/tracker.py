import sqlite3
import json
import os
import logging
from datetime import datetime, timedelta

class Tracker:
    """
    Menedżer bazy danych SQLite dla RegWatch.
    Odpowiada za przechowywanie aktów, deduplikację i statystyki.
    """
    def __init__(self, db_path=None):
        if db_path is None:
            # Domyślna ścieżka: folder regwatch na pulpicie
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "regwatch.db")
        else:
            self.db_path = db_path
            
        self._init_db()

    def _init_db(self):
        """Tworzy strukturę tabeli acts, jeśli jeszcze nie istnieje."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS acts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT UNIQUE,
                source TEXT,
                title TEXT,
                url TEXT,
                country TEXT,
                language TEXT,
                date_scraped TEXT,
                date_published TEXT,
                full_text TEXT,
                
                -- Pola analizy AI (LLM)
                is_relevant BOOLEAN,
                relevance_level TEXT,
                urgency TEXT,
                summary TEXT,
                affected_areas TEXT, -- JSON
                timeline TEXT,      -- JSON
                change_type TEXT,    -- JSON
                regulatory_stage TEXT,
                vacatio_legis_status TEXT,
                compliance_checklist TEXT, -- JSON
                jurisdictions TEXT,         -- JSON
                
                llm_analyzed BOOLEAN DEFAULT 0
            )
        """)
        
        # Alter table for existing databases (adds missing PRO fields)
        try:
            cursor.execute("ALTER TABLE acts ADD COLUMN regulatory_domains TEXT")
            cursor.execute("ALTER TABLE acts ADD COLUMN key_topics TEXT")
            cursor.execute("ALTER TABLE acts ADD COLUMN cross_references TEXT")
        except sqlite3.OperationalError:
            pass # Columns already exist

        conn.commit()
        conn.close()

    def is_new(self, content_hash):
        """Sprawdza, czy akt o podanym hashu istnieje już w bazie."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM acts WHERE content_hash = ?", (content_hash,))
        exists = cursor.fetchone() is not None
        conn.close()
        return not exists

    def save_scraped(self, item):
        """Zapisuje surowe dane pobrane przez scraper."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        try:
            cursor.execute("""
                INSERT INTO acts (
                    content_hash, source, title, url, country, language, 
                    date_scraped, date_published, full_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item['content_hash'], item['source'], item['title'], item['url'], 
                item['country'], item['language'], now, item['publication_date'],
                item['full_text']
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            # Ignorujemy duplikaty (UNIQUE constraint on content_hash)
            pass
        finally:
            conn.close()

    def get_unanalyzed(self):
        """Zwraca listę aktów, które jeszcze nie zostały przeanalizowane przez AI."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # Dzięki temu mamy dostęp po nazwach kolumn
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM acts WHERE llm_analyzed = 0")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def save_analysis(self, content_hash, analysis):
        # Zapisuje wyniki analizy AI dla konkretnego aktu.
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Konwertujemy listy/słowniki na JSON strings
        affected_areas = json.dumps(analysis.get('affected_areas', []))
        timeline = json.dumps(analysis.get('timeline', {}))
        change_type = json.dumps(analysis.get('change_type', []))
        compliance_checklist = json.dumps(analysis.get('compliance_checklist', []))
        jurisdictions = json.dumps(analysis.get('jurisdictions', []))
        
        # Nowe pola PRO
        regulatory_domains = json.dumps(analysis.get('regulatory_domains', []))
        key_topics = json.dumps(analysis.get('key_topics', []))
        cross_references = json.dumps(analysis.get('cross_references', []))
        
        cursor.execute("""
            UPDATE acts SET 
                is_relevant = ?,
                relevance_level = ?,
                urgency = ?,
                summary = ?,
                affected_areas = ?,
                timeline = ?,
                change_type = ?,
                regulatory_stage = ?,
                vacatio_legis_status = ?,
                compliance_checklist = ?,
                jurisdictions = ?,
                regulatory_domains = ?,
                key_topics = ?,
                cross_references = ?,
                llm_analyzed = 1
            WHERE content_hash = ?
        """, (
            analysis.get('is_relevant'),
            analysis.get('relevance_level'),
            analysis.get('urgency'),
            analysis.get('summary_en', analysis.get('summary')), # Map summary_en to summary
            affected_areas,
            timeline,
            change_type,
            analysis.get('regulatory_stage'),
            analysis.get('vacatio_legis_status'),
            compliance_checklist,
            jurisdictions,
            regulatory_domains,
            key_topics,
            cross_references,
            content_hash
        ))
        conn.commit()
        conn.close()

    def get_approaching_deadlines(self, days=90):
        """
        Zwraca akty, których terminy (z osi czasu) przypadają w ciągu X dni.
        Wymaga, aby 'timeline' zawierał daty w formacie ISO.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM acts WHERE llm_analyzed = 1 AND vacatio_legis_status != 'deadline_passed'")
        rows = cursor.fetchall()
        conn.close()
        
        approaching = []
        now = datetime.now()
        deadline_limit = now + timedelta(days=days)
        
        for row in rows:
            act = dict(row)
            try:
                timeline = json.loads(act['timeline'] or '{}')
            except json.JSONDecodeError:
                continue
                
            # Szukamy najwcześniejszej istotnej daty z przyszłości
            dates_to_check = [
                timeline.get('compliance_deadline'),
                timeline.get('entry_into_force'),
                timeline.get('transition_period_end')
            ]
            
            closest_date = None
            for d in dates_to_check:
                if not d or str(d).lower() in ['none', 'n/a', 'unknown', 'null']: continue
                try:
                    # Próba sparsowania daty YYYY-MM-DD
                    dt = datetime.strptime(str(d[:10]), "%Y-%m-%d")
                    if now <= dt <= deadline_limit:
                        closest_date = str(d[:10])
                        break
                except ValueError:
                    pass
            
            if closest_date:
                act['deadline_date'] = closest_date
                
                # Ustalanie koloru na podstawie dni do terminu
                days_left = (datetime.strptime(closest_date, "%Y-%m-%d") - now).days
                if days_left < 30:
                    act['status_color'] = 'red'
                elif days_left < 60:
                    act['status_color'] = 'amber'
                else:
                    act['status_color'] = 'yellow'
                    
                approaching.append(act)
                
        # Sortowanie od najbliższego terminu
        approaching.sort(key=lambda x: x.get('deadline_date', '9999-99-99'))
        return approaching

    def get_stats(self):
        """Zwraca podstawowe statystyki bazy danych."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT count(*) FROM acts")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(*) FROM acts WHERE llm_analyzed = 1")
        analyzed = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(DISTINCT source) FROM acts")
        sources = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_acts': total,
            'analyzed_acts': analyzed,
            'unique_sources': sources
        }

# --- BLOK TESTOWY ---
if __name__ == "__main__":
    # Usuwamy starą bazę testową, jeśli istnieje
    TEST_DB = "test_regwatch.db"
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    tracker = Tracker(TEST_DB)
    
    # 1. Tworzymy dummy item
    dummy_item = {
        'content_hash': 'abc-123-test',
        'source': 'Test Authority',
        'title': 'Test Act 2026',
        'url': 'http://example.com/act',
        'country': 'PL',
        'language': 'pl',
        'publication_date': '2026-03-20',
        'full_text': 'Full text of the test regulation.'
    }
    
    # 2. Zapisujemy po raz pierwszy
    print(f"Czy akt jest nowy? {tracker.is_new(dummy_item['content_hash'])}")
    tracker.save_scraped(dummy_item)
    print("Zapisano pierwszy akt.")
    
    # 3. Próba zapisu duplikatu
    print(f"Czy duplikat jest nowy? {tracker.is_new(dummy_item['content_hash'])}")
    tracker.save_scraped(dummy_item)
    
    # 4. Zapisujemy drugi akt
    dummy_item_2 = dummy_item.copy()
    dummy_item_2['content_hash'] = 'xyz-789-test'
    dummy_item_2['title'] = 'Second Test Act'
    tracker.save_scraped(dummy_item_2)
    print("Zapisano drugi akt.")
    
    # 5. Wyświetlamy statystyki
    stats = tracker.get_stats()
    print("\n--- STATYSTYKI BAZY ---")
    print(f"Suma aktów: {stats['total_acts']} (powinno być 2)")
    print(f"Źródła:     {stats['unique_sources']}")
    
    # Sprzątanie
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
