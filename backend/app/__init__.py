from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before any module reads configuration; real environment variables take precedence.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
