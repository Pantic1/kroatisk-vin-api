import datetime
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()
username = os.environ.get('SMTP_USERNAME')
password = os.environ.get('SMTP_PASSWORD')
host = os.environ.get('SMTP_HOST')
port = os.environ.get('SMTP_PORT')


def send_email(subject, recipient, body):
    email = EmailMessage()
    email["From"] = username
    email["To"] = recipient
    email["Subject"] = subject
    email.add_alternative(body, subtype="html")

    try:
        with smtplib.SMTP_SSL(host, port) as smtp:
            smtp.login(username, password)
            smtp.send_message(email)
        print(f"✅ Email sendt til {recipient}")

    except smtplib.SMTPDataError as e:
        # Hostinger har slået afsendelse fra
        if e.smtp_code == 554 and b"Disabled by user" in e.smtp_error:
            print("🚫 Email-afsendelse er slået fra i hPanel! (554 Disabled by user)")
        else:
            print(f"⚠️ SMTP-fejl ({e.smtp_code}): {e.smtp_error}")

    except Exception as e:
        print(f"❌ Ukendt fejl ved afsendelse: {e}")