#!/usr/bin/env python3
"""
update.py
Mengambil data pasar (USDIDR, CDS Indonesia 5Y, Bond Indonesia 1Y/5Y, IHSG, Crude Oil)
dari sumber GRATIS (tanpa API key) lalu menyimpannya ke data.json.

Sumber data:
- USDIDR              : Frankfurter API (https://frankfurter.dev)
- IHSG (^JKSE)        : Yahoo Finance chart API (unofficial)
- Crude Oil (WTI CL=F): Yahoo Finance chart API (unofficial)
- CDS Indonesia 5Y    : scraping worldgovernmentbonds.com
- Bond Indonesia 1Y/5Y: scraping worldgovernmentbonds.com

Prinsip desain:
- Kalau salah satu sumber gagal diambil (situs down / struktur berubah / rate limit),
  script TIDAK crash. Nilai lama di data.json tetap dipertahankan, dan field
  "status" akan menandai sumber mana yang gagal, supaya kamu bisa cek lewat GitHub
  Actions log tanpa mematikan seluruh pipeline.
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

DATA_FILE = "data.json"
WIB = timezone(timedelta(hours=7))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
TIMEOUT = 15


def load_existing():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def safe_get(url, **kwargs):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------------------
# 1. USDIDR - Frankfurter API (gratis, tanpa API key)
# ---------------------------------------------------------------------------
def fetch_usdidr():
    url = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=IDR"
    r = safe_get(url)
    data = r.json()
    rate = data["rates"]["IDR"]
    return {
        "value": round(rate, 2),
        "unit": "IDR",
        "date": data.get("date"),
        "source": "frankfurter.dev",
    }


# ---------------------------------------------------------------------------
# 2 & 3. IHSG dan Crude Oil (WTI) - Yahoo Finance chart API (unofficial, gratis)
# ---------------------------------------------------------------------------
def fetch_yahoo_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = safe_get(url, params={"interval": "1d", "range": "5d"})
    data = r.json()
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
    change_pct = None
    if price is not None and prev_close:
        change_pct = round((price - prev_close) / prev_close * 100, 2)
    return {
        "value": round(price, 2) if price is not None else None,
        "previous_close": prev_close,
        "change_pct": change_pct,
        "currency": meta.get("currency"),
        "source": "yahoo_finance",
    }


def fetch_ihsg():
    return fetch_yahoo_quote("%5EJKSE")  # ^JKSE


def fetch_crude_oil():
    # CL=F = WTI Crude Oil Futures (NYMEX)
    quote = fetch_yahoo_quote("CL=F")
    quote["type"] = "WTI Crude Oil Futures"
    quote["unit"] = "USD/barrel"
    return quote


# ---------------------------------------------------------------------------
# 4. CDS Indonesia 5Y - scraping worldgovernmentbonds.com
# ---------------------------------------------------------------------------
def fetch_cds_5y():
    url = "https://www.worldgovernmentbonds.com/cds-country/indonesia/"
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Pola kalimat di halaman: "...Credit Default Swap (CDS) value stands at 75.32 basis points"
    m = re.search(
        r"stands at\s*([\d.,]+)\s*basis points", text, flags=re.IGNORECASE
    )
    if not m:
        # fallback: cari di elemen berlabel "value" pada tabel ringkasan
        m = re.search(r"([\d.,]+)\s*bps", text, flags=re.IGNORECASE)
    if not m:
        raise ValueError("Tidak menemukan angka CDS 5Y di halaman (struktur mungkin berubah)")

    value = float(m.group(1).replace(",", ""))
    return {"value": value, "unit": "bps", "source": "worldgovernmentbonds.com"}


# ---------------------------------------------------------------------------
# 5 & 6. Bond Indonesia 1Y & 5Y - scraping worldgovernmentbonds.com
# (halaman yield curve negara berisi tabel semua tenor)
# ---------------------------------------------------------------------------
def fetch_bond_yields():
    url = "https://www.worldgovernmentbonds.com/country/indonesia/"
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    results = {}
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            label = cells[0]
            # Cocokkan baris "1 Year" atau "5 Years"
            if re.fullmatch(r"1\s*Year", label, flags=re.IGNORECASE):
                val = _extract_percent(cells)
                if val is not None:
                    results["1Y"] = val
            elif re.fullmatch(r"5\s*Years?", label, flags=re.IGNORECASE):
                val = _extract_percent(cells)
                if val is not None:
                    results["5Y"] = val

    if "1Y" not in results and "5Y" not in results:
        raise ValueError("Tidak menemukan baris yield 1Y/5Y (struktur tabel mungkin berubah)")

    return results


def _extract_percent(cells):
    for c in cells[1:]:
        m = re.search(r"(-?[\d.,]+)\s*%", c)
        if m:
            return float(m.group(1).replace(",", ""))
    # kadang persennya tanpa simbol %, ambil angka desimal pertama
    for c in cells[1:]:
        m = re.fullmatch(r"-?[\d.,]+", c)
        if m:
            try:
                return float(c.replace(",", ""))
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    existing = load_existing()
    result = dict(existing)  # mulai dari data lama, supaya field yg gagal tetap ada
    status = {}

    fetchers = {
        "usdidr": fetch_usdidr,
        "ihsg": fetch_ihsg,
        "crude_oil": fetch_crude_oil,
        "cds_5y": fetch_cds_5y,
    }

    for key, fn in fetchers.items():
        try:
            result[key] = fn()
            status[key] = "ok"
        except Exception as e:
            status[key] = f"error: {e}"
            print(f"[WARN] Gagal mengambil {key}: {e}", file=sys.stderr)

    try:
        bonds = fetch_bond_yields()
        if "1Y" in bonds:
            result["bond_1y"] = {"value": bonds["1Y"], "unit": "%", "source": "worldgovernmentbonds.com"}
            status["bond_1y"] = "ok"
        else:
            status["bond_1y"] = "error: not found"
        if "5Y" in bonds:
            result["bond_5y"] = {"value": bonds["5Y"], "unit": "%", "source": "worldgovernmentbonds.com"}
            status["bond_5y"] = "ok"
        else:
            status["bond_5y"] = "error: not found"
    except Exception as e:
        status["bond_1y"] = f"error: {e}"
        status["bond_5y"] = f"error: {e}"
        print(f"[WARN] Gagal mengambil bond yields: {e}", file=sys.stderr)

    result["last_updated"] = datetime.now(WIB).isoformat()
    result["last_run_status"] = status

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
