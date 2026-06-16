"""Google Sheets via Apps Script doGet — no GCP / credentials needed."""

import logging

import requests

import config

logger = logging.getLogger(__name__)


def save_to_sheet(full_name: str, amount: int, username: str):
    url = getattr(config, "APPS_SCRIPT_URL", "")
    if not url:
        logger.info("APPS_SCRIPT_URL not configured — skipping.")
        return

    params = {
        "name":   full_name,
        "amount": amount,
        "user":   username if username and username != "N/A" else "unknown",
    }
    try:
        resp = requests.get(url, params=params, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok":
            logger.info("Sheet row added at row %s", data.get("row"))
        else:
            logger.error("Apps Script error: %s", data.get("message"))
    except Exception as e:
        logger.error("Sheets write failed: %s", e)
