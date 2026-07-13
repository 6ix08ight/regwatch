import jinja2
import os
import json
from datetime import datetime

class ReportGenerator:
    """
    Klasa odpowiedzialna za generowanie profesjonalnych raportów regulacyjnych.
    Tworzy wersję HTML (na maila) oraz Markdown (lokalny podgląd).
    """
    def __init__(self, template_dir=None, output_dir=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.template_dir = template_dir or os.path.join(base_dir, "templates")
        self.output_dir = output_dir or os.path.join(base_dir, "output")
        
        # Inicjalizacja Jinja2
        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.template_dir))
        
        # Upewnienie się, że folder wyjściowy istnieje
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate(self, data):
        """Generuje oba formaty raportów na podstawie dostarczonych danych."""
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Dodajemy techniczne pola do danych dla szablonu
        data['timestamp'] = timestamp
        
        # 1. Generowanie HTML
        template = self.env.get_template("report_email.html")
        html_content = template.render(data)
        
        html_path = os.path.join(self.output_dir, f"regwatch_report_{today}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # 2. Generowanie Markdown (prostsza wersja tekstowa)
        md_content = self._generate_markdown(data)
        md_path = os.path.join(self.output_dir, f"regwatch_report_{today}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        return {
            "html": html_path,
            "markdown": md_path
        }

    def _generate_markdown(self, data):
        """Tworzy wersję tekstową Markdown na potrzeby konsoli/Git."""
        md = [f"# RegWatch Weekly — {data.get('date_range', 'Latest')}\n"]
        md.append(f"## Summary")
        md.append(f"- **New Acts**: {data['stats']['new_count']}")
        md.append(f"- **Urgency**: High ({data['stats']['high_urgency']}), Medium ({data['stats']['medium_urgency']}), Low ({data['stats']['low_urgency']})")
        
        if data.get('deadlines'):
            md.append("\n## Approaching Deadlines")
            for d in data['deadlines']:
                md.append(f"- **{d['deadline_date']}**: [{d['title']}]({d['url']}) (Status: {d['vacatio_legis_status']})")
        
        md.append("\n## New This Week")
        for act in data.get('new_acts', []):
            md.append(f"### [{act['urgency']}] {act['title']}")
            md.append(f"Source: {act['source']} | [Link]({act['url']})")
            md.append(f"\n{act.get('summary_en', 'No summary available.')}\n")
            if act.get('compliance_checklist'):
                md.append("#### Compliance Checklist")
                for item in act['compliance_checklist']:
                    md.append(f"- [ ] {item}")
            md.append("---")
            
        md.append(f"\n*Generated at {data['timestamp']}*")
        return "\n".join(md)

# --- BLOK TESTOWY ---
if __name__ == "__main__":
    # Symulacja danych pobranych z bazy
    dummy_data = {
        "date_range": "20–26 March 2026",
        "stats": {
            "total_sources": 3,
            "new_count": 2,
            "high_urgency": 1,
            "medium_urgency": 1,
            "low_urgency": 0
        },
        "deadlines": [
            {
                "title": "EBA Guidelines on DORA Reporting",
                "url": "https://example.com/dora",
                "deadline_date": "2026-06-30",
                "status_color": "red",
                "vacatio_legis_status": "approaching_deadline"
            }
        ],
        "new_acts": [
            {
                "title": "Commission Delegated Regulation (EU) 2026/123",
                "source": "FSMA",
                "url": "https://example.com/act1",
                "publication_date": "2026-03-24",
                "jurisdictions": ["EU", "BE"],
                "urgency": "HIGH",
                "summary_en": "Requires banking institutions to implement new liquidity reporting protocols starting Q4 2026.",
                "compliance_checklist": ["Review LCR reporting", "Update internal policy"]
            },
            {
                "title": "NBB Circular on Payouts",
                "source": "NBB",
                "url": "https://example.com/act2",
                "publication_date": "2026-03-22",
                "jurisdictions": ["BE"],
                "urgency": "MEDIUM",
                "summary_en": "Recommendations on supplementary pension payouts.",
                "compliance_checklist": ["Train HR staff", "Review pension workflows"]
            }
        ],
        "flagged": [],
        "source_status": [
            {"name": "FSMA RSS", "icon": "✅"},
            {"name": "NBB Web", "icon": "✅"},
            {"name": "EUR-Lex API", "icon": "⏭️"}
        ]
    }
    
    gen = ReportGenerator()
    paths = gen.generate(dummy_data)
    print(f"Raporty wygenerowane pomyślnie!")
    print(f"HTML: {paths['html']}")
    print(f"MD:   {paths['markdown']}")
