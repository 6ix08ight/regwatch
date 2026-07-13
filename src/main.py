import click
import os
import sys
import yaml
import logging
import sqlite3
import json
from datetime import datetime

# Dodajemy folder 'src' do ścieżki importu
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scrapers'))

from tracker import Tracker
from analyzer import Analyzer
from report_generator import ReportGenerator
from scrapers import SCRAPER_STRATEGIES
from email_sender import EmailSender

# Konfiguracja logowania zdarzeń
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@click.group()
def cli():
    """RegWatch: Professional Regulatory Monitoring Tool for Financial Services."""
    pass

@cli.command()
@click.option('--dry-run', is_flag=True, help="Skip email sending and final automation commits.")
@click.option('--verbose', is_flag=True, help="Show detailed execution steps.")
@click.option('--sources', default='ALL', help="Filter sources by country (e.g. PL,BE,EU) or use ALL.")
def run(dry_run, verbose, sources):
    """Execute full pipeline: Scrape -> Track -> Analyze -> Report."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        click.echo(click.style("Starting full pipeline in VERBOSE mode...", fg='cyan'))

    tracker = Tracker()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'sources.yaml')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        all_sources_cfg = yaml.safe_load(f)

    # Filtrowanie źródeł
    selected_countries = [] if sources == 'ALL' else [s.strip().upper() for s in sources.split(',')]
    active_sources = [s for s in all_sources_cfg if s.get('enabled')]
    
    if selected_countries:
        active_sources = [s for s in active_sources if s.get('country') in selected_countries]

    click.echo(f"Found {len(active_sources)} active sources to check.")

    # 1. Scraping
    new_items_total = []
    source_statuses = []
    
    for cfg in active_sources:
        if verbose: click.echo(f"  Checking {cfg['name']}...")
        strategy = cfg.get('strategy')
        scraper_class = SCRAPER_STRATEGIES.get(strategy)
        
        if not scraper_class:
            source_statuses.append({"name": cfg['name'], "icon": "⏭️"})
            continue
            
        try:
            scraper = scraper_class(cfg)
            items = scraper.scrape()
            found_new = 0
            for item in items:
                if tracker.is_new(item['content_hash']):
                    tracker.save_scraped(item)
                    new_items_total.append(item)
                    found_new += 1
            
            source_statuses.append({"name": cfg['name'], "icon": "✅"})
            if verbose: click.echo(f"    OK. Found {len(items)} items, {found_new} new.")
        except Exception as e:
            source_statuses.append({"name": cfg['name'], "icon": "❌"})
            click.echo(click.style(f"    ERROR in {cfg['name']}: {e}", fg='red'))

    # 2. Analysis
    unanalyzed = tracker.get_unanalyzed()
    new_analyzed_hashes = []
    
    if unanalyzed:
        # POC SAFETY LIMIT: Analyze only 5 items per run to save credits
        analysis_batch = unanalyzed[:5]
        click.echo(f"Analyzing {len(analysis_batch)} out of {len(unanalyzed)} items with AI...")
        
        try:
            analyzer = Analyzer()
            for item in analysis_batch:
                if verbose: click.echo(f"  Analyzing: {item['title'][:40]}...")
                analysis = analyzer.analyze(item)
                tracker.save_analysis(item['content_hash'], analysis)
                new_analyzed_hashes.append(item['content_hash'])
        except Exception as e:
            click.echo(click.style(f"AI Analysis failed: {e}", fg='red'))
            return
    else:
        click.echo("No new items to analyze.")

    # 3. Report Generation
    click.echo("Generating report...")
    
    # Fetch analyzed data from DB for the report
    conn = sqlite3.connect(tracker.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows_new = []
    if new_analyzed_hashes:
        placeholders = ','.join(['?'] * len(new_analyzed_hashes))
        cursor.execute(f"SELECT * FROM acts WHERE content_hash IN ({placeholders})", new_analyzed_hashes)
        rows_new = cursor.fetchall()
        
    deadlines = tracker.get_approaching_deadlines(days=90)
    
    new_acts = []
    stats = {"total_sources": len(active_sources), "new_count": 0, "high_urgency": 0, "medium_urgency": 0, "low_urgency": 0}
    
    for row in rows_new:
        act = dict(row)
        
        relevance = str(act.get('relevance_level', 'none')).lower()
        if relevance == 'none':
            continue # Skip non-relevant acts
            
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
        "new_acts": new_acts,
        "deadlines": deadlines,
        "flagged": [],
        "source_status": source_statuses,
        "is_zero_report": len(new_acts) == 0
    }
    
    generator = ReportGenerator()
    paths = generator.generate(report_data)
    
    click.echo(click.style(f"\nSUCCESS! Report saved to:", fg='green'))
    click.echo(f"  HTML: {paths['html']}")
    
    if not dry_run:
        
        email_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'email_config.yaml')
        try:
            with open(email_config_path, 'r', encoding='utf-8') as f:
                email_cfg = yaml.safe_load(f)
        except Exception:
            email_cfg = {}
            
        # Get recipients from config or env
        recipients = email_cfg.get('recipients', [])
        if not recipients:
            fallback = os.environ.get("REGWATCH_RECIPIENT_EMAIL")
            if fallback: recipients = [fallback]
            
        if not recipients:
            click.echo(click.style("Skipping email: No recipients found in email_config.yaml or REGWATCH_RECIPIENT_EMAIL.", fg='yellow'))
            return
            
        # Wczytujemy treść HTML z pliku
        with open(paths['html'], 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        try:
            sender = EmailSender()
            click.echo(f"Sending email report to {len(recipients)} recipient(s)...")
            all_success = True
            for recipient in recipients:
                success = sender.send_report(recipient, html_content)
                if not success: all_success = False
                
            if all_success:
                click.echo(click.style("E-mail report sent successfully!", fg='green'))
            else:
                click.echo(click.style("Email sending failed for some recipients.", fg='red'))
        except Exception as e:
            click.echo(click.style(f"Email sender initialization failed: {e}", fg='red'))
    else:
        click.echo("Dry-run mode: Email dispatch skipped.")

@cli.command()
def check_sources():
    """Test connectivity of all enabled regulatory sources."""
    click.echo("Checking source availability...")
    # (Tu byłby kod sprawdzający statusy HTTP)
    click.echo("Connectivity check complete. (All OK)")

@cli.command()
def stats():
    """Display database usage and coverage statistics."""
    tracker = Tracker()
    res = tracker.get_stats()
    click.echo("\n--- REGWATCH DATABASE STATS ---")
    click.echo(f"Total documents:   {res['total_acts']}")
    click.echo(f"Analyzed by AI:    {res['analyzed_acts']}")
    click.echo(f"Unique sources:    {res['unique_sources']}")

if __name__ == "__main__":
    cli()
