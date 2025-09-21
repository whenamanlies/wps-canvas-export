import os
import smtplib
from email.message import EmailMessage

def send_email_to_self(subject, body):
    user = os.environ['GMAIL_USER']
    app_pass = os.environ['GMAIL_APP_PASS']

    msg = EmailMessage()
    msg['From'] = user
    msg['To'] = user
    msg['Subject'] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(user, app_pass)
            s.send_message(msg)
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    send_email_to_self("Test Email From GitHub", "Hello World")