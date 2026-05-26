# backend/scrapers/master_scraper.py

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uuid
import re
import time
from datetime import datetime
from celery import shared_task

# Import your local ChromaDB instance
from app.utils.chroma_store import chroma_db

# ══════════════════════════════════════════════════════════════════════
# ALL 8 DATA SOURCES — ORGANIZED BY CATEGORY
# ══════════════════════════════════════════════════════════════════════

SOURCES = {
    "banking": {
        "urls": [
            ("https://www.bankbazaar.com/savings-account.html", "BankBazaar Savings"),
            ("https://www.bankbazaar.com/fixed-deposit-rate.html", "BankBazaar FD"),
            ("https://www.bankbazaar.com/recurring-deposit.html", "BankBazaar RD"),
            ("https://groww.in/fixed-deposit", "Groww FD"),
            ("https://groww.in/recurring-deposit", "Groww RD"),
            ("https://www.bankbazaar.com/credit-card.html", "BankBazaar Credit Cards"),
            ("https://www.bankbazaar.com/personal-loan.html", "BankBazaar Personal Loan"),
        ]
    },
    "stocks": {
        "urls": [
            ("https://www.moneycontrol.com/stocks/marketstats/nsegainer/index.html", "MC Top Gainers"),
            ("https://www.moneycontrol.com/stocks/marketstats/nseloser/index.html", "MC Top Losers"),
            ("https://www.screener.in/screens/71064/all-stocks/", "Screener All Stocks"),
        ]
    },
    "mutual_funds": {
        "urls": [
            ("https://groww.in/mutual-funds/top-mutual-funds", "Groww Top MF"),
            ("https://www.moneycontrol.com/mutual-funds/performance-tracker/returns/large-cap-fund.html", "MC Large Cap"),
            ("https://www.moneycontrol.com/mutual-funds/performance-tracker/returns/tax-saving-fund.html", "MC ELSS"),
        ]
    },
    "gold": {
        "urls": [
            ("https://www.goodreturns.in/gold-rates/", "GoodReturns Gold"),
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
            ("https://economictimes.indiatimes.com/wealth", "ET Wealth"),
            ("https://www.moneycontrol.com/news/business/personal-finance/", "MC Personal Finance"),
        ]
    },
}

# ══════════════════════════════════════════════════════════════════════
# NLP CHUNKING & EXTRACTION LOGIC
# ══════════════════════════════════════════════════════════════════════

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """Smart chunking with overlap to preserve context across splits"""
    text = re.sub(r'\s+', ' ', text).strip()
    words = text.split()
    chunks = []
    
    words_per_chunk = chunk_size // 5
    words_overlap = overlap // 5
    
    for i in range(0, len(words), words_per_chunk - words_overlap):
        chunk = " ".join(words[i:i + words_per_chunk])
        if len(chunk.strip()) > 50:  # Ignore tiny useless chunks
            chunks.append(chunk)
    
    return chunks

def scrape_url_playwright(url: str, source_name: str) -> str:
    """Uses a real headless browser to execute JS and extract dynamic tables"""
    print(f"[*] Booting headless browser for: {source_name}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # CRITICAL: Wait 3 seconds for React/JS tables to physically render
            page.wait_for_timeout(3000)
            
            html = page.content()
            browser.close()

            # Clean HTML with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                tag.extract()
            
            # Try to grab main content first to avoid sidebars
            main_content = soup.find('main') or soup.find('article') or soup.find(class_=re.compile('content|article|post|table'))
            
            if main_content:
                text = main_content.get_text(separator=' ')
            else:
                text = soup.get_text(separator=' ')
            
            text = re.sub(r'\s+', ' ', text).strip()
            return text
            
    except Exception as e:
        print(f"[!] Failed to scrape {url}: {e}")
        return ""

def store_in_chroma(category: str, url: str, source_name: str, text: str):
    """Chunks text and stores it in the correct ChromaDB collection"""
    if not text or len(text) < 100:
        print(f"[!] Skipping {source_name} — insufficient text")
        return
    
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    print(f"[+] {source_name}: Extracted {len(chunks)} real data chunks")
    
    documents = []
    for idx, chunk in enumerate(chunks):
        documents.append({
            "id": f"{source_name.replace(' ','_')}_{uuid.uuid4().hex[:8]}",
            "text": chunk,
            "metadata": {
                "category": category,
                "source": source_name,
                "url": url,
                "scraped_at": datetime.now().isoformat(),
            }
        })
    
    if documents:
        # Route the remaining categories into our 3 core ChromaDB collections
        collection_map = {
            "banking": "banking_data",
            "stocks": "investment_data",
            "mutual_funds": "investment_data",
            "gold": "investment_data",
            "retirement": "financial_tips",
            "financial_tips": "financial_tips",
        }
        
        collection_name = collection_map.get(category, "financial_tips")
        
        # Clear existing chunks for this specific source before inserting new ones to avoid duplicates/stale data
        try:
            collection = chroma_db._get_or_create_collection(collection_name)
            collection.delete(where={"source": source_name})
            print(f"[+] Cleaned up previous chunks for source: {source_name}")
        except Exception as e:
            print(f"[!] Failed to clean up previous chunks: {e}")

        docs_to_insert = [doc["text"] for doc in documents]
        ids_to_insert = [doc["id"] for doc in documents]
        metas_to_insert = [doc["metadata"] for doc in documents]
        
        docs_formatted = [
            {"id": ids_to_insert[i], "text": docs_to_insert[i], "metadata": metas_to_insert[i]}
            for i in range(len(docs_to_insert))
        ]
        
        chroma_db.add_documents(
            collection_name=collection_name,
            documents=docs_formatted
        )
        print(f"[+] Inserted into {collection_name}")

# ══════════════════════════════════════════════════════════════════════
# ORCHESTRATION & SCHEDULED TASKS
# ══════════════════════════════════════════════════════════════════════

def scrape_category(category: str):
    """Scrape all URLs within a specific category"""
    print(f"\n{'='*60}\nSCRAPING CATEGORY: {category.upper()}\n{'='*60}")
    category_data = SOURCES.get(category)
    
    if not category_data:
        return

    for url, source_name in category_data["urls"]:
        text = scrape_url_playwright(url, source_name)
        if text:
            store_in_chroma(category, url, source_name, text)
        
        # Wait between requests to avoid rate limits
        time.sleep(3)

def scrape_all():
    """Main function: scrape everything"""
    print("\n" + "="*60 + "\nFINASSIST HEADLESS BROWSER SCRAPER\n" + "="*60)
    for category in SOURCES.keys():
        scrape_category(category)
    print("\n" + "="*60 + "\nSCRAPING COMPLETE\n" + "="*60)


# CELERY TASKS FOR PRODUCTION SCHEDULING
@shared_task
def scheduled_weekly_scrape():
    """Run on Sunday 2 AM"""
    scrape_category("banking")

@shared_task
def scheduled_daily_morning_scrape():
    """Run Mon-Fri 9:15 AM"""
    scrape_category("stocks")

@shared_task
def scheduled_daily_evening_scrape():
    """Run Daily 6 PM"""
    scrape_category("mutual_funds")
    scrape_category("gold")
    scrape_category("financial_tips")

@shared_task
def scheduled_monthly_scrape():
    """Run 1st of month"""
    scrape_category("retirement")

# ══════════════════════════════════════════════════════════════════════
# MANUAL EXECUTION
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    scrape_all()