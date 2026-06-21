# backend/scrapers/master_scraper.py

from __future__ import annotations  # FIX: enables tuple[x, y] syntax on Python 3.9

import logging
import re
import time
import uuid
from datetime import datetime
from typing import Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from chroma_store import chroma_db

# ══════════════════════════════════════════════════════════════════════
# LOGGING  (replaces bare print() calls throughout)
# ══════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# CONSTANTS  (FIX: magic numbers were scattered inline; centralised here)
# ══════════════════════════════════════════════════════════════════════
SCRAPE_DELAY_SECONDS: int   = 3
MAX_RETRY_ATTEMPTS:   int   = 2
MIN_TEXT_LENGTH:      int   = 100   # chars — reject pages shorter than this
MIN_CHUNK_LENGTH:     int   = 50    # chars — discard tiny trailing chunks
MAX_CHUNK_WORDS:      int   = 160   # words per chunk (≈ 800 chars at 5 chars/word)
OVERLAP_WORDS:        int   = 20    # words carried forward from previous chunk


# ══════════════════════════════════════════════════════════════════════
# DATA SOURCES
# ══════════════════════════════════════════════════════════════════════
SOURCES: dict[str, dict] = {
    "banking": {
        "urls": [
            ("https://www.bankbazaar.com/savings-account.html",       "BankBazaar Savings"),
            ("https://www.bankbazaar.com/fixed-deposit-rate.html",    "BankBazaar FD"),
            ("https://www.bankbazaar.com/recurring-deposit.html",     "BankBazaar RD"),
            ("https://groww.in/fixed-deposit",                        "Groww FD"),
            ("https://groww.in/recurring-deposit",                    "Groww RD"),
            ("https://www.bankbazaar.com/credit-card.html",           "BankBazaar Credit Cards"),
            ("https://www.bankbazaar.com/personal-loan.html",         "BankBazaar Personal Loan"),
        ]
    },
    "stocks": {
        "urls": [
            ("https://www.moneycontrol.com/stocks/marketstats/nsegainer/index.html", "MC Top Gainers"),
            ("https://www.moneycontrol.com/stocks/marketstats/nseloser/index.html",  "MC Top Losers"),
            ("https://www.screener.in/screens/71064/all-stocks/",                    "Screener All Stocks"),
        ]
    },
    "mutual_funds": {
        "urls": [
            ("https://groww.in/mutual-funds/top-mutual-funds",                                                          "Groww Top MF"),
            ("https://www.moneycontrol.com/mutual-funds/performance-tracker/returns/large-cap-fund.html", "MC Large Cap"),
            ("https://www.moneycontrol.com/mutual-funds/performance-tracker/returns/tax-saving-fund.html","MC ELSS"),
        ]
    },
    "gold": {
        "urls": [
            ("https://www.goodreturns.in/gold-rates/",          "GoodReturns Gold"),
            ("https://www.bankbazaar.com/gold-rate-today.html", "BankBazaar Gold"),
        ]
    },
    "retirement": {
        "urls": [
            ("https://www.bankbazaar.com/ppf.html", "BankBazaar PPF"),
        ]
    },
    "financial_tips": {
        "urls": [
            ("https://economictimes.indiatimes.com/wealth",                       "ET Wealth"),
            ("https://www.moneycontrol.com/news/business/personal-finance/",     "MC Personal Finance"),
        ]
    },
}

# ══════════════════════════════════════════════════════════════════════
# RECURSIVE TEXT CHUNKING
# ══════════════════════════════════════════════════════════════════════

# Separator priority: coarsest boundary first, finest last.
# The splitter tries each in order and only descends to a finer level
# when a piece is still larger than MAX_CHUNK_WORDS.
_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", "! ", "? ", ", ", " ")


def _word_count(text: str) -> int:
    return len(text.split())


def _recursive_split(
    text: str,
    separators: tuple[str, ...],
    max_words: int,
) -> list[str]:
    """
    Internal recursive worker — no overlap, no public API.

    Algorithm
    ---------
    1. If the text already fits in max_words, return it as-is.
    2. Find the coarsest separator that exists in the text.
    3. Split on that separator and pack pieces into a running buffer.
       - If a piece is itself > max_words, flush the buffer and recurse
         into that piece with the next-finer separator.
       - If adding a piece would overflow the buffer, flush and start fresh.
    4. If no separator is found and text is still too long, hard-split on
       words as a last resort (rare — only for one giant unbroken string).
    """
    text = text.strip()
    if not text:
        return []

    if _word_count(text) <= max_words:
        return [text] if len(text) >= MIN_CHUNK_LENGTH else []

    sep = next((s for s in separators if s in text), None)

    if sep is None:
        # Last resort: word-level hard split
        words = text.split()
        return [
            " ".join(words[i : i + max_words])
            for i in range(0, len(words), max_words)
            if " ".join(words[i : i + max_words]).strip()
        ]

    finer = separators[separators.index(sep) + 1:]
    pieces = [p.strip() for p in text.split(sep) if p.strip()]

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_words: int  = 0

    for piece in pieces:
        piece_words = _word_count(piece)

        if piece_words > max_words:
            # Flush buffer, then recurse into the oversized piece
            if buffer:
                chunks.append(" ".join(buffer))
                buffer, buffer_words = [], 0
            chunks.extend(_recursive_split(piece, finer, max_words))
            continue

        if buffer_words + piece_words > max_words and buffer:
            chunks.append(" ".join(buffer))
            buffer, buffer_words = [], 0

        buffer.append(piece)
        buffer_words += piece_words

    if buffer:
        chunks.append(" ".join(buffer))

    return [c for c in chunks if len(c) >= MIN_CHUNK_LENGTH]


def recursive_chunk(
    text: str,
    max_words:     int = MAX_CHUNK_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> list[str]:
    """
    Split *text* on natural boundaries (paragraph → line → sentence →
    clause → word), then stitch adjacent chunks with an *overlap_words*-word
    tail from the previous chunk so retrieval context is never lost at a
    boundary.

    Parameters
    ----------
    text:          Scraped page text (newlines preserved from get_text).
    max_words:     Hard ceiling on words per chunk.
    overlap_words: Words from the end of chunk[i] prepended to chunk[i+1].

    Returns
    -------
    List of semantically coherent, overlapping text chunks.
    """
    if not text:
        return []

    # Collapse only horizontal whitespace — preserve \n so the separator
    # hierarchy (\n\n → \n → sentence) can actually do its job.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # normalise excessive blank lines
    text = text.strip()

    raw = _recursive_split(text, _SEPARATORS, max_words)

    if len(raw) <= 1 or overlap_words == 0:
        return raw

    # Stitch overlap: prepend the tail of chunk[i-1] to chunk[i]
    result: list[str] = [raw[0]]
    for i in range(1, len(raw)):
        tail = " ".join(raw[i - 1].split()[-overlap_words:])
        result.append(tail + " " + raw[i])

    return result


# ══════════════════════════════════════════════════════════════════════
# SCRAPING
# ══════════════════════════════════════════════════════════════════════
def scrape_url_playwright(
    url: str,
    source_name: str,
    retries: int = MAX_RETRY_ATTEMPTS,
) -> str:
    """
    Launch a headless Chromium browser, render the page (including JS/React
    dynamic tables), extract meaningful text, and return it.

    Retries up to *retries* times on failure.
    """
    for attempt in range(1, retries + 1):
        log.info("Scraping [%d/%d]: %s", attempt, retries, source_name)
        try:
            # FIX: BeautifulSoup parsing was inside the sync_playwright() block,
            # keeping the browser alive unnecessarily while parsing HTML.
            # Capture html first, close the browser, then parse.
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        viewport={"width": 1920, "height": 1080},
                    )
                    page = context.new_page()

                    # FIX: original used wait_until="domcontentloaded" + a fixed
                    # 3-second sleep — a race condition that fails on slow pages and
                    # wastes time on fast ones.
                    # "networkidle" waits until JS has finished fetching and rendering.
                    page.goto(url, wait_until="networkidle", timeout=45_000)

                    html = page.content()
                finally:
                    # FIX: browser.close() was after page.content() with no finally
                    # guard — an exception would leak the browser process.
                    # sync_playwright()'s __exit__ also kills browsers, but explicit
                    # close() is faster and more intentional.
                    browser.close()

            # ── HTML → plain text (browser is now closed) ─────────────────
            soup = BeautifulSoup(html, "html.parser")

            # FIX: tag.extract() detaches but keeps the subtree allocated;
            # tag.decompose() destroys it and frees memory.
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                tag.decompose()

            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find(class_=re.compile(r"content|article|post|table", re.I))
            )
            text = (main_content or soup).get_text(separator="\n")
            # Collapse horizontal whitespace only — preserve \n for the chunker
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.strip()

            if len(text) >= MIN_TEXT_LENGTH:
                return text

            log.warning(
                "Text too short for '%s' (%d chars) on attempt %d",
                source_name, len(text), attempt,
            )

        except Exception as exc:
            log.error("Attempt %d/%d failed for '%s': %s", attempt, retries, source_name, exc)

        if attempt < retries:
            time.sleep(SCRAPE_DELAY_SECONDS)

    log.error("All %d attempts exhausted for '%s' — skipping", retries, source_name)
    return ""


# ══════════════════════════════════════════════════════════════════════
# CHROMADB STORAGE
# ══════════════════════════════════════════════════════════════════════
def store_in_chroma(category: str, url: str, source_name: str, text: str) -> None:
    """Chunk *text* and upsert into the single ChromaDB collection."""
    if not text or len(text) < MIN_TEXT_LENGTH:
        log.warning(
            "Skipping '%s' — insufficient text (%d chars)",
            source_name, len(text) if text else 0,
        )
        return

    chunks = recursive_chunk(text)
    if not chunks:
        log.warning("No valid chunks produced for '%s'", source_name)
        return

    log.info("'%s' → %d chunks", source_name, len(chunks))

    collection_name = "finassist_knowledge"
    now = datetime.now().isoformat()

    # FIX: original built a list[dict], unpacked it into 3 separate lists,
    # then zipped them back into the same list[dict] — a completely circular
    # triple transformation that produced an identical structure.
    # Just build the final list once.
    documents = [
        {
            "id":   f"{source_name.replace(' ', '_')}_{uuid.uuid4().hex[:8]}",
            "text": chunk,
            "metadata": {
                "category":   category,
                "source":     source_name,
                "url":        url,
                "scraped_at": now,
            },
        }
        for chunk in chunks
    ]

    # Evict stale chunks for this source before inserting fresh ones
    try:
        # FIX: original called chroma_db._get_or_create_collection() — a private
        # internal method.  Use the public interface instead.
        collection = chroma_db.get_or_create_collection(collection_name)
        collection.delete(where={"source": source_name})
        log.info("Evicted stale chunks for source '%s'", source_name)
    except Exception as exc:
        log.warning("Could not evict stale chunks for '%s': %s", source_name, exc)

    chroma_db.add_documents(collection_name=collection_name, documents=documents)
    log.info("Inserted %d chunks into '%s'", len(documents), collection_name)


# ══════════════════════════════════════════════════════════════════════
# LIVE WEB SEARCH  (on-demand, optional dependency)
# ══════════════════════════════════════════════════════════════════════
def live_web_search_and_scrape(query: str, max_results: int = 1) -> tuple[str, str]:
    """
    Search DuckDuckGo for *query*, scrape the top result, and return
    ``(combined_text, source_url)``.  Returns ``("", "")`` on failure.
    """
    try:
        # FIX: original imported from "ddgs" which does not exist as a package.
        # The correct package is "duckduckgo_search"; import kept lazy since it
        # is an optional runtime dependency.
        from duckduckgo_search import DDGS  # pip install duckduckgo-search

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            log.warning("No DDG results for query: '%s'", query)
            return "", ""

        top      = results[0]
        top_url  = top.get("href", "")
        snippet  = top.get("body",  "")
        title    = top.get("title", "Live Web Search")

        if not top_url:
            log.warning("Top result had no URL for query: '%s'", query)
            return "", ""

        scraped_text = scrape_url_playwright(top_url, f"Live Search: {title}")
        combined = f"Search Summary: {snippet}\n\nWebsite Content: {scraped_text}"
        return combined, top_url

    except Exception as exc:
        log.error("Live web search failed for '%s': %s", query, exc)
        return "", ""


# ══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════
def scrape_category(category: str) -> None:
    """Scrape every URL registered under *category*."""
    category_data = SOURCES.get(category)
    if not category_data:
        log.error("Unknown category: '%s'", category)
        return

    urls = category_data["urls"]
    log.info("══ Scraping category: %s (%d URLs) ══", category.upper(), len(urls))

    for url, source_name in urls:
        text = scrape_url_playwright(url, source_name)
        if text:
            store_in_chroma(category, url, source_name, text)
        time.sleep(SCRAPE_DELAY_SECONDS)


def scrape_all() -> None:
    """Entry-point: scrape every registered source across all categories."""
    log.info("══════════ FinAssist Headless Scraper — START ══════════")
    for category in SOURCES:
        scrape_category(category)
    log.info("══════════ FinAssist Headless Scraper — DONE  ══════════")


if __name__ == "__main__":
    scrape_all()