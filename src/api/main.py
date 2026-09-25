import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

app = FastAPI(title=os.getenv("APP_NAME", "FinTrust Risk System"))