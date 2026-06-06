"""Static config for the Profound snapshot pull."""
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.environ["PROFOUND_API_KEY"]          # from .env
BASE_URL = "https://api.tryprofound.com"

ORG_ID      = "1680a859-ec50-451a-a781-995de61d9a40"   # Profound Marketing Engineer Hackathon
CATEGORY_ID = "7943f355-67f3-4792-b172-981db56ef33c"   # Frontier Models

# Snapshot window (REST end is inclusive). Last 7 days as of 2026-06-06.
START_DATE = "2026-05-30"
END_DATE   = "2026-06-06"

OWNED_BRAND = "ChatGPT"                              # prompt-view asset filter

DB_PATH = os.path.join(os.path.dirname(__file__), "profound.db")
