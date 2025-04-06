import smtplib
import json
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import streamlit as st


import os

# === 从配置文件中读取邮箱和密码 ===
def load_email_config(path='D:\.email_config.json'):
    with open(path, 'r') as f:
        config = json.load(f)
    return config['email'], config['password']

# === 基本配置 ===
SMTP_SERVER = st.secrets.get("SMTP_SERVER")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", 465)) # 端口号需要是整数
SENDER_EMAIL = st.secrets.get("SENDER_EMAIL",)
SENDER_PASSWORD = st.secrets.get("SENDER_PASSWORD")


def send_email(recipient_email, subject, body):
    """发送邮件"""
    message = MIMEText(body, 'plain', 'utf-8')
    message['From'] = formataddr(("OutputTime Bot", SENDER_EMAIL))
    message['To'] = Header(recipient_email, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, [recipient_email], message.as_string())
        server.quit()
        print(f"Email sent successfully to {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("SMTP Authentication Error: Check sender email/password and security settings.")
        return False
    except Exception as e:
        print(f"Failed to send email to {recipient_email}: {e}")
        return False

if __name__ == '__main__':
    test_recipient = 'f.z.hui105@gmail.com'
    test_subject = "OutputTime Test Email"
    test_body = "This is a test email from the OutputTime app setup."
    print(f"Attempting to send test email to {test_recipient}...")
    send_email(test_recipient, test_subject, test_body)
