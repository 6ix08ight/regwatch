import smtplib
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

class EmailSender:
    """
    Moduł wysyłki raportów drogą e-mail (SMTP).
    Wykorzystuje bezpieczne połączenie TLS (port 587).
    """
    def __init__(self):
        import yaml
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, 'config', 'email_config.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f).get('smtp', {})
        except Exception as e:
            config = {}
            logging.warning(f"Brak pliku email_config.yaml, polegamy na zmiennych środowiskowych: {e}")

        # Pobieranie danych logowania z configa lub zmiennych środowiskowych (fallback)
        self.smtp_server = config.get('server', "smtp.gmail.com")
        self.smtp_port = config.get('port', 587)
        self.sender_email = os.environ.get("REGWATCH_SENDER_EMAIL") or config.get('sender_email')
        self.sender_pass = os.environ.get("REGWATCH_EMAIL_PASS") or config.get('app_password')

        if not self.sender_email or not self.sender_pass:
            logging.error("Email credentials missing in config and ENV.")
            raise ValueError("Brak danych logowania e-mail.")

    def send_report(self, to_email, html_content, subject=None):
        """Wysyła raport HTML na wskazany adres e-mail."""
        if not subject:
            subject = f"🏛️ RegWatch: Regulatory Report — {datetime.now().strftime('%Y-%m-%d')}"

        # Budowa wiadomości e-mail
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.sender_email
        message["To"] = to_email

        # Dołączanie treści HTML
        part_html = MIMEText(html_content, "html")
        message.attach(part_html)

        try:
            # Nawiązywanie połączenia z serwerem Gmail
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls() # Szyfrowanie połączenia
            server.login(self.sender_email, self.sender_pass)
            server.sendmail(self.sender_email, to_email, message.as_string())
            server.quit()
            
            logging.info(f"E-mail wysłany pomyślnie na adres: {to_email}")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas wysyłki e-maila: {e}")
            return False

# --- BLOK TESTOWY ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Przykładowy test (wyśle e-maila na Twój własny adres)
    sender_mail = os.environ.get("REGWATCH_SENDER_EMAIL")
    
    if sender_mail:
        print(f"Próba wysłania testowego e-maila z: {sender_mail}")
        sender = EmailSender()
        test_html = "<h1>Test RegWatch</h1><p>To jest automatyczna wiadomość testowa.</p>"
        sender.send_report(sender_mail, test_html, "🧪 RegWatch: Test Połączenia e-mail")
    else:
        print("\nBŁĄD: Musisz najpierw ustawić zmienne środowiskowe:")
        print("export REGWATCH_SENDER_EMAIL='twój-mail@gmail.com'")
        print("export REGWATCH_EMAIL_PASS='twoje-hasło-aplikacji'")
