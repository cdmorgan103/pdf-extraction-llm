"""
config.py - settings that change between machines (this PC now, a GPU server later).

Every setting can be overridden with an environment variable, so moving the pipeline
to another machine or database means changing environment variables, not code.

    OLLAMA_URL   where the Ollama server is            (default: this PC)
    OCR_DB_URL   SQLAlchemy URL of the results database (default: none = no database)

Examples (PowerShell):
    $env:OCR_DB_URL = "mssql+pyodbc://@localhost/ocr_pipeline?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes"
    $env:OLLAMA_URL = "http://gpu-server:11434/api/chat"
"""

from __future__ import annotations

import os

# Ollama's chat endpoint. On a separate GPU server this becomes e.g. http://gpu-server:11434/api/chat
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

# Results database. Empty = results are only written as JSON/CSV files.
# SQL Server (local, Windows login):
#   mssql+pyodbc://@localhost/ocr_pipeline?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes
# A SQLite file also works (handy for tests): sqlite:///runs/test.db
DB_URL = os.environ.get("OCR_DB_URL", "")

# --- Monitoring thresholds (see monitor.py) ---
OUTLIER_Z = float(os.environ.get("OCR_OUTLIER_Z", 4.0))       # robust z-score above which a value is an outlier
DRIFT_PSI_ALERT = float(os.environ.get("OCR_DRIFT_PSI", 0.25))  # PSI above which a batch has drifted
AUDIT_SAMPLE_RATE = float(os.environ.get("OCR_AUDIT_RATE", 0.05))  # share of unflagged docs sent for review
ALLOWED_CURRENCIES = os.environ.get("OCR_CURRENCIES", "USD,GBP,EUR").split(",")
