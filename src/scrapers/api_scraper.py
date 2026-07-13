import logging
import requests
from base_scraper import BaseScraper

class ApiScraper(BaseScraper):
    """
    Scraper dedykowany dla zapytań API (m m.in. SPARQL dla EUR-Lex, REST dla ISAP).
    """
    def scrape(self) -> list[dict]:
        logging.info(f"Rozpoczynam zapytanie API: {self.name} ({self.url})...")
        self._delay()
        
        results = []
        try:
            if "isap" in self.url.lower():
                results = self._scrape_isap()
            elif "sparql" in self.url.lower():
                results = self._scrape_eurlex()
            else:
                logging.warning(f"[{self.name}] Nierozpoznany endpoint API. Brak implementacji w POC.")
        except Exception as e:
            logging.error(f"[{self.name}] Błąd podczas zapytania API: {e}")
            
        logging.info(f"Znaleziono {len(results)} wpisów w API {self.name}.")
        return results

    def _scrape_isap(self):
        url = self.url.rstrip('/') + "/acts?offset=0&limit=10"
        response = requests.get(url, headers=self.headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('items', []):
            title = item.get('title', 'Brak tytułu')
            act_url = f"https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id={item.get('address')}"
            pub_date = item.get('promulgation', '2026-03-01')
            
            results.append({
                'source': self.name,
                'title': title,
                'url': act_url,
                'publication_date': pub_date,
                'full_text': title,
                'language': self.lang,
                'country': self.country,
                'content_hash': self._compute_hash(title, act_url, pub_date)
            })
        return results

    def _scrape_eurlex(self):
        try:
            from SPARQLWrapper import SPARQLWrapper, JSON
        except ImportError:
            logging.error("Missing SPARQLWrapper. Install it via pip install SPARQLWrapper.")
            return []
            
        sparql = SPARQLWrapper(self.url)
        sparql.setReturnFormat(JSON)
        # Uproszczone zapytanie POC: 5 najnowszych dyrektyw/rozporządzeń
        query = """
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?work ?creationDate
        WHERE {
          ?work a cdm:regulation .
          ?work cdm:work_date_document ?creationDate .
          FILTER (str(?creationDate) > "2026-01-01")
        }
        ORDER BY DESC(?creationDate)
        LIMIT 5
        """
        sparql.setQuery(query)
        ret = sparql.queryAndConvert()
        
        results = []
        for r in ret["results"]["bindings"]:
            uri = r["work"]["value"]
            date = r["creationDate"]["value"]
            title = f"EU Regulation {uri.split('/')[-1]}"
            act_url = uri
            
            results.append({
                'source': self.name,
                'title': title,
                'url': act_url,
                'publication_date': date,
                'full_text': title,
                'language': self.lang,
                'country': self.country,
                'content_hash': self._compute_hash(title, act_url, date)
            })
        return results
