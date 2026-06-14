#!/usr/bin/env python3
"""
Corgi 509 Dutch model watchdog.

Scans eBay and collector sites for the rare Corgi 509 (Dutch / Holland livery).
Skips auction-format listings and Marktplaats.
Sends an email digest when new listings appear.

Schedule weekly via cron, e.g.:
    0 9 * * 1  /usr/bin/python3 /home/signalbox/signalbox/watchdog_corgi509.py

Required env vars (put in ~/.bashrc or a .env file sourced by cron):
    WATCHDOG_EMAIL_FROM   Gmail address that sends the alert
    WATCHDOG_EMAIL_TO     Recipient (defaults to WATCHDOG_EMAIL_FROM)
    WATCHDOG_EMAIL_PASS   Gmail app-password (not your main password)
"""

import json
import os
import re
import smtplib
import sys
import time
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEARCH_TERMS = [
    "Corgi 509 Dutch",
    "Corgi 509 Holland",
    "Corgi 509 Politie",       # Dutch police livery
    "Corgi 509 Nederlandse",
]

EXCLUDED_DOMAINS = [
    "marktplaats.nl",
    "catawiki.com",             # auction house
    "invaluable.com",           # auction aggregator
    "liveauctioneers.com",
    "auction.com",
]

# Words in a listing title that suggest it's an auction we want to skip.
AUCTION_KEYWORDS = ["auction", "veiling", "bid", "bieder", "bieden", "lot"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9,nl;q=0.8",
}

STATE_FILE = Path(__file__).parent / ".corgi509_seen.json"
REQUEST_DELAY = 2   # seconds between HTTP requests

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_seen() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_seen(seen: set) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=2))


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def is_excluded(url: str, title: str) -> bool:
    url_lower = url.lower()
    title_lower = title.lower()
    if any(d in url_lower for d in EXCLUDED_DOMAINS):
        return True
    if any(kw in title_lower for kw in AUCTION_KEYWORDS):
        return True
    return False


# ---------------------------------------------------------------------------
# eBay scrapers  (Buy It Now only, .com / .co.uk / .nl)
# ---------------------------------------------------------------------------

def _ebay_search(base_url: str, query: str) -> list[dict]:
    """Scrape one eBay domain search results page (BIN listings only)."""
    results = []
    url = (
        f"{base_url}/sch/i.html"
        f"?_nkw={quote_plus(query)}"
        f"&LH_BIN=1"      # Buy It Now only
        f"&_sop=10"        # sort: newly listed
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  eBay fetch error ({base_url}): {e}", file=sys.stderr)
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    for item in soup.select("li.s-item"):
        a_tag = item.select_one("a.s-item__link")
        title_tag = item.select_one(".s-item__title")
        price_tag = item.select_one(".s-item__price")
        if not a_tag or not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        if title.lower().startswith("shop on ebay"):
            continue
        link = a_tag["href"].split("?")[0]  # strip tracking params
        price = price_tag.get_text(strip=True) if price_tag else ""
        if not is_excluded(link, title):
            results.append({"title": title, "url": link, "price": price, "source": base_url})
    return results


def search_ebay(query: str) -> list[dict]:
    results = []
    for domain in ["https://www.ebay.com", "https://www.ebay.co.uk", "https://www.ebay.nl"]:
        results.extend(_ebay_search(domain, query))
        time.sleep(REQUEST_DELAY)
    return results


# ---------------------------------------------------------------------------
# Google Shopping  (scrape the HTML results page)
# ---------------------------------------------------------------------------

def search_google_shopping(query: str) -> list[dict]:
    """Scrape Google Shopping results — no API key needed, but fragile."""
    results = []
    url = (
        f"https://www.google.com/search"
        f"?q={quote_plus(query)}"
        f"&tbm=shop"
        f"&hl=en"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Google Shopping fetch error: {e}", file=sys.stderr)
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    for item in soup.select("div.sh-dgr__grid-result, div.Qlx7of"):
        title_tag = item.select_one("h3, .tAxDx")
        link_tag = item.select_one("a[href]")
        price_tag = item.select_one(".a8Pemb, .OFFNJ")
        if not title_tag or not link_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = link_tag["href"]
        # Google Shopping links are /url?q=... or direct
        m = re.search(r"[?&]q=(https?://[^&]+)", href)
        link = m.group(1) if m else href
        price = price_tag.get_text(strip=True) if price_tag else ""
        if not is_excluded(link, title):
            results.append({"title": title, "url": link, "price": price, "source": "Google Shopping"})
    time.sleep(REQUEST_DELAY)
    return results


# ---------------------------------------------------------------------------
# Vectis / specialist diecast auction / retailer sites
# Checking a few known collector stores that list by fixed price
# ---------------------------------------------------------------------------

def search_diecastmoose(query: str) -> list[dict]:
    """Search diecastmoose.co.uk — fixed-price collector listings."""
    results = []
    url = f"https://www.diecastmoose.co.uk/search?q={quote_plus(query)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  DiecastMoose fetch error: {e}", file=sys.stderr)
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    for item in soup.select("div.product-item, li.product"):
        title_tag = item.select_one("h2, h3, .product-title, .product-item__title")
        link_tag = item.select_one("a[href]")
        price_tag = item.select_one(".price, .product-price")
        if not title_tag or not link_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = link_tag["href"]
        if not href.startswith("http"):
            href = "https://www.diecastmoose.co.uk" + href
        price = price_tag.get_text(strip=True) if price_tag else ""
        if not is_excluded(href, title):
            results.append({"title": title, "url": href, "price": price, "source": "DiecastMoose"})
    time.sleep(REQUEST_DELAY)
    return results


def search_corgi_classiques(query: str) -> list[dict]:
    """Check corgi.co.uk product search for fixed-price items."""
    results = []
    url = f"https://www.corgi.co.uk/search?q={quote_plus(query)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Corgi.co.uk fetch error: {e}", file=sys.stderr)
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    for item in soup.select("div.product-card, article.product"):
        title_tag = item.select_one("h2, h3, .product-name, .card__heading")
        link_tag = item.select_one("a[href]")
        price_tag = item.select_one(".price, .product__price")
        if not title_tag or not link_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = link_tag["href"]
        if not href.startswith("http"):
            href = "https://www.corgi.co.uk" + href
        price = price_tag.get_text(strip=True) if price_tag else ""
        if not is_excluded(href, title):
            results.append({"title": title, "url": href, "price": price, "source": "Corgi.co.uk"})
    time.sleep(REQUEST_DELAY)
    return results


# ---------------------------------------------------------------------------
# Master search
# ---------------------------------------------------------------------------

def run_all_searches() -> list[dict]:
    all_results = []
    for term in SEARCH_TERMS:
        print(f"Searching: {term!r}")
        all_results.extend(search_ebay(term))
        all_results.extend(search_google_shopping(term))
        all_results.extend(search_diecastmoose(term))
        all_results.extend(search_corgi_classiques(term))

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique.append(r)
    return unique


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

def send_email(new_listings: list[dict]) -> None:
    from_addr = os.environ.get("WATCHDOG_EMAIL_FROM", "")
    to_addr   = os.environ.get("WATCHDOG_EMAIL_TO", from_addr)
    password  = os.environ.get("WATCHDOG_EMAIL_PASS", "")

    if not from_addr or not password:
        print("Email not configured — set WATCHDOG_EMAIL_FROM / WATCHDOG_EMAIL_PASS.", file=sys.stderr)
        _print_results(new_listings)
        return

    lines = [
        f"Found {len(new_listings)} new listing(s) for Corgi 509 Dutch model:\n"
    ]
    for item in new_listings:
        lines.append(f"  [{item['source']}] {item['title']}")
        if item["price"]:
            lines.append(f"  Price : {item['price']}")
        lines.append(f"  URL   : {item['url']}")
        lines.append("")

    body = "\n".join(lines)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Corgi 509 Dutch — {len(new_listings)} new listing(s) found"
    msg["From"]    = from_addr
    msg["To"]      = to_addr

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(from_addr, password)
            smtp.sendmail(from_addr, to_addr, msg.as_string())
        print(f"Email sent to {to_addr}.")
    except Exception as e:
        print(f"Email error: {e}", file=sys.stderr)
        _print_results(new_listings)


def _print_results(listings: list[dict]) -> None:
    for item in listings:
        print(f"\n[{item['source']}] {item['title']}")
        if item["price"]:
            print(f"  Price: {item['price']}")
        print(f"  URL  : {item['url']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Corgi 509 Dutch watchdog starting…")
    seen = load_seen()
    all_listings = run_all_searches()

    new_listings = [r for r in all_listings if r["url"] not in seen]

    if new_listings:
        print(f"\n{len(new_listings)} NEW listing(s) found!")
        send_email(new_listings)
        seen.update(r["url"] for r in new_listings)
        save_seen(seen)
    else:
        print("No new listings found.")

    print("Done.")


if __name__ == "__main__":
    main()
