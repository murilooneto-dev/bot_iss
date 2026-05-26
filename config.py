import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "bot_iss.db")
FISCAL_DB_PATH = os.getenv(
    "FISCAL_DB_PATH",
    r"C:\Users\Client\Documents\Sistemas\sistemafiscal\Fiscal\fiscal-system\data\fiscal-system.sqlite",
)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
