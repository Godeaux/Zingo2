from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL = timedelta(hours=24)
_memory_cache: dict[str, tuple[datetime, list[dict]]] = {}


def fetch_dividends(ticker: str) -> list[dict]:
    ticker = ticker.upper()
    now = datetime.utcnow()
    # in-memory cache
    if ticker in _memory_cache:
        ts, data = _memory_cache[ticker]
        if now - ts < CACHE_TTL:
            return data
    path = CACHE_DIR / f"{ticker}.json"
    if path.exists():
        with open(path) as f:
            obj = json.load(f)
        ts = datetime.fromisoformat(obj["timestamp"])
        if now - ts < CACHE_TTL:
            data = obj["data"]
            _memory_cache[ticker] = (ts, data)
            return data
    series = yf.Ticker(ticker).dividends
    one_year_ago = now - timedelta(days=365)
    recent = series[series.index >= one_year_ago]
    data = [
        {"date": d.strftime("%Y-%m-%d"), "amount": float(v)}
        for d, v in recent.items()
    ]
    obj = {"timestamp": now.isoformat(), "data": data}
    with open(path, "w") as f:
        json.dump(obj, f)
    _memory_cache[ticker] = (now, data)
    return data


def detect_change(data: list[dict]) -> dict:
    if not data:
        return {"status": "suspension", "last": None, "previous": None, "date": None}
    last = data[-1]
    if len(data) == 1:
        return {
            "status": "no_change",
            "last": last["amount"],
            "previous": None,
            "date": last["date"],
        }
    prev = data[-2]
    status = "no_change"
    if last["amount"] > prev["amount"]:
        status = "increase"
    elif last["amount"] < prev["amount"]:
        status = "cut"
    return {
        "status": status,
        "last": last["amount"],
        "previous": prev["amount"],
        "date": last["date"],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dividends", methods=["POST"])
def dividends():
    tickers_raw = request.json.get("tickers", "")
    tickers = [t.strip().upper() for t in re.split(r"[\s,]+", tickers_raw) if t.strip()]
    result = {"series": [], "changes": []}
    for t in tickers:
        data = fetch_dividends(t)
        result["series"].append({"ticker": t, "data": data})
        change = detect_change(data)
        change["ticker"] = t
        result["changes"].append(change)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
