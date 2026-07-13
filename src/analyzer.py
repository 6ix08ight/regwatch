import os
import time
import json
import yaml
import logging
from google import genai
from google.genai import types

class Analyzer:
    """
    Moduł analizy regulacyjnej oparty na modelu LLM (Gemini).
    Klasyfikuje, streszcza i ocenia wpływ aktów prawnych na działalność banku.
    """
    def __init__(self):
        # Konfiguracja klienta SDK google-genai
        # Sprawdzamy czy używamy Vertex AI (domyślnie True jeśli brak klucza API i/lub ustawiona zmienna)
        use_vertex_str = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower()
        api_key = os.environ.get("GEMINI_API_KEY")
        
        # Jeśli brak klucza API, domyślnie Vertex AI przez ADC
        if not api_key:
            use_vertex = True
            logging.info("GEMINI_API_KEY not set. Defaulting to Vertex AI / ADC authentication.")
        else:
            use_vertex = use_vertex_str in ("true", "1", "yes")

        if use_vertex:
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            logging.info(f"Initializing Google GenAI Client using Vertex AI (Project: {project_id}, Location: {location}).")
            self.client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location
            )
        else:
            logging.info("Initializing Google GenAI Client using Gemini Developer API Key.")
            self.client = genai.Client(api_key=api_key)
        
        # Wczytujemy profil organizacji z configa
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        org_profile_path = os.path.join(base_dir, 'config', 'org_profile.yaml')
        try:
            with open(org_profile_path, 'r', encoding='utf-8') as f:
                org_config = yaml.safe_load(f).get('organization', {})
        except Exception as e:
            logging.warning(f"Nie udało się załadować org_profile.yaml: {e}. Używam profilu domyślnego.")
            org_config = {"name": "European Bank", "type": "bank", "jurisdictions": {"primary": ["EU"]}, "business_lines": ["Banking"], "responsibility_areas": []}

        jurisdictions = ", ".join(org_config.get('jurisdictions', {}).get('primary', ['EU']))
        business_lines = ", ".join(org_config.get('business_lines', ['banking services']))
        areas = "\n   - ".join([a.get('name', 'Unknown') for a in org_config.get('responsibility_areas', [])])
        
        # Instrukcja systemowa definiująca rolę i strukturę odpowiedzi JSON
        self.system_prompt = f"""You are a senior regulatory analyst at an organization named '{org_config.get('name')}' ({org_config.get('type')})
operating primarily in: {jurisdictions}.
The organization's main business lines are: {business_lines}.

Analyze the following regulatory act and determine:

1. RELEVANCE: Is this act relevant to the organization's business lines and operations? (yes/no/partially)
   Consider ALL of the following regulatory domains:

   - Prudential regulation: CRR/CRD VI, Basel III/IV, MREL, BRRD, IRRBB,
     capital requirements, liquidity (LCR, NSFR), leverage ratio
   - Payment services: PSD2/PSD3, PSR, SEPA, instant payments regulation,
     open banking, account access
   - Anti-money laundering: AMLD6, AML Package (AMLR, AMLD), AMLA authority,
     KYC/KYB, sanctions screening, beneficial ownership
   - Digital & technology: DORA, NIS2, AI Act, MiCA, cloud outsourcing,
     ICT risk management
   - Consumer protection: Consumer Credit Directive, Mortgage Credit Directive,
     Distance Marketing of Financial Services, PRIIPs
   - Sustainable finance: CSRD, EU Taxonomy, SFDR, ESG risk management,
     climate stress testing, green bond standards
   - Markets & investment: MiFID II/MiFIR review, EMIR, CSDR, MAR
   - Data protection: GDPR, ePrivacy, data transfers, AI Act data requirements
   - Outsourcing & third parties: EBA Guidelines on outsourcing,
     DORA ICT third-party risk, CTPPs, BaaS regulatory framework
   - Resolution & recovery: BRRD II, MREL, resolution planning, DGSD review
   - Governance: EBA Guidelines on internal governance, fit & proper,
     remuneration policies (CRD), whistleblowing
   - Tax & reporting: DAC7/DAC8, FATCA, CRS, Pillar Two, FTT proposals
   - Structural: Banking union, EDIS, CMDI framework

2. SUMMARY: Concise summary (3-5 sentences) in English regardless of source language.
   Focus on: what changed, who is affected, what action is required.

3. AFFECTED RESPONSIBILITY AREAS: Which areas should be involved?
   Choose from:
   - {areas}
   For each: explain WHY they are affected and WHAT ACTION they should consider.

4. TIMELINE & VACATIO LEGIS: Identify compliance deadlines, transition periods,
   effective dates. Distinguish: publication date, entry into force,
   compliance deadline, transition period end.
   VACATIO LEGIS STATUS: published_not_in_force / in_force / approaching_deadline / deadline_passed

5. URGENCY: HIGH / MEDIUM / LOW
   - HIGH: deadline < 6 months, or significant operational impact, or supervisory sanctions
   - MEDIUM: deadline 6-18 months, or moderate process changes
   - LOW: deadline > 18 months, or minor/clarifying changes, or early-stage proposals

6. CHANGE TYPE: policy_update / organizational_change / infrastructure_change /
   reporting_change / training_required / monitoring_only

7. JURISDICTION: EU-wide, Poland, Belgium, Germany, Spain, Portugal,
   Eurozone (SSM), International (FATF), or combinations.

8. REGULATORY STAGE: Proposal/consultation / Final text adopted /
   Published in Official Journal / Implementing/delegated act / Supervisory guidance/Q&A

9. COMPLIANCE CHECKLIST: 3-5 yes/no readiness questions tailored to the specific act.

Respond ONLY in JSON format:
{{
  "is_relevant": true,
  "relevance_level": "high/medium/low/none",
  "summary_en": "...",
  "regulatory_domains": ["prudential", "AML", "digital"],
  "affected_areas": [
    {{"name": "...", "reason": "...", "suggested_action": "..."}}
  ],
  "timeline": {{
    "publication_date": "...",
    "entry_into_force": "...",
    "compliance_deadline": "...",
    "transition_period_end": "..."
  }},
  "vacatio_legis_status": "...",
  "urgency": "HIGH",
  "change_type": ["policy_update"],
  "jurisdictions": ["EU-wide", "PL", "BE"],
  "regulatory_stage": "...",
  "compliance_checklist": ["..."],
  "key_topics": ["CRR", "capital requirements"],
  "cross_references": ["..."]
}}"""
        # Zdefiniowanie modelu z zmiennej środowiskowej lub domyślnego gemini-2.5-flash
        self.model_name = os.environ.get("REGWATCH_MODEL_NAME", "gemini-2.5-flash")

    def analyze(self, item: dict) -> dict:
        """Wysyła pobrany element do LLM i zwraca sformatowany wynik JSON."""
        time.sleep(1) # Opóźnienie 1 s między zapytaniami z API na wypadek limitów
        
        title = item.get('title', 'No Title')
        text = item.get('full_text', 'No Content')
        pub_date = item.get('publication_date', 'Unknown Date')
        
        prompt = f"Title: {title}\nDate: {pub_date}\n\nAct Text:\n{text}"
        
        try:
            # Wymuszamy format JSON za pomocą response_mime_type by uniknąć problemów z parsowaniem
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    response_mime_type="application/json"
                )
            )
            # Pobieramy tekst
            result_text = response.text
            
            # Parsujemy JSON
            analysis = json.loads(result_text)
            
            # Zabezpieczenie przed samowolką LLMa: jeśli model wrzuci odpowiedź jako listę, np. [{...}], bierzemy pierwszy obiekt
            if isinstance(analysis, list) and len(analysis) > 0:
                analysis = analysis[0]
            elif isinstance(analysis, list):
                analysis = {}

            # Zabezpieczenie przed brakiem kluczowych pól
            if 'summary_en' not in analysis:
                 analysis['summary_en'] = "Failed to extract summary."
                 
            return analysis
            
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse LLM response as JSON: {e}")
            return {"needs_human_review": True, "error": "JSON parse error", "raw_response": response.text if 'response' in locals() else str(e)}
        except Exception as e:
            logging.error(f"Error during LLM analysis: {e}")
            return {"needs_human_review": True, "error": str(e)}

# --- BLOK TESTOWY ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        analyzer = Analyzer()
        
        test_item = {
            "title": "EBA Guidelines on DORA",
            "publication_date": "2024-05-10",
            "full_text": "The European Banking Authority published new Guidelines on ICT and security risk management requirements under DORA, applicable from January 2025."
        }
        
        print(f"Rozpoczynam analizę z użyciem {analyzer.model_name}...")
        start_time = time.time()
        result = analyzer.analyze(test_item)
        duration = time.time() - start_time
        
        print(f"\nUkończono w {duration:.2f} s. Wynik analizy to prawidłowy JSON:\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"\nBŁĄD PODCZAS URUCHOMIENIA: {e}")
        print("Upewnij się, że masz skonfigurowane poświadczenia gcloud i projekt GCP lub ustawioną zmienną GEMINI_API_KEY.")
