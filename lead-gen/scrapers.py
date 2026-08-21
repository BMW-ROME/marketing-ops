"""
lead-gen/scrapers.py

Playwright + Requests-based web scraper to replace Bright Data.
Returns the same record format as Bright Data so it's a drop-in replacement.

Hybrid approach:
  1. Try fast requests first (static HTML)
  2. Detect JS-heavy indicators
  3. Fall back to Playwright for dynamic sites
  4. Extract structured lead signals (company, emails, phone, etc.)
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Detection: if page loads more content after initial render, use Playwright
JS_HEAVY_INDICATORS = [
    "loading", "spinner", "skeleton", "data-react", "data-vue",
    "data-ng"  # Angular, React, Vue frameworks
]

# Optional: only import Playwright if available (graceful degradation)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Install via: pip install playwright && playwright install chromium")


async def scrape_with_playwright(url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Scrape JS-heavy sites using headless browser.
    Waits for network idle and common loader patterns to clear.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "url": url,
            "status": "error",
            "error": "Playwright not installed",
            "method": "playwright"
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate and wait for network idle (page + resources loaded)
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            
            # Wait for common loaders to disappear (optional, best effort)
            try:
                await page.wait_for_function(
                    "() => !document.querySelector('[class*=loading], [class*=spinner]')",
                    timeout=5000
                )
            except:
                pass  # Not all pages have loaders; that's fine
            
            content = await page.content()
            
            return {
                "url": url,
                "html": content,
                "status": "success",
                "method": "playwright"
            }
        except Exception as e:
            logger.warning(f"Playwright failed for {url}: {e}")
            return {
                "url": url,
                "status": "error",
                "error": str(e),
                "method": "playwright"
            }
        finally:
            await browser.close()


def scrape_with_requests(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Fast fallback for static sites (no JS rendering needed).
    Sets a realistic User-Agent to avoid blocking.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        
        return {
            "url": url,
            "html": resp.text,
            "status": "success",
            "method": "requests"
        }
    except requests.RequestException as e:
        logger.warning(f"Requests failed for {url}: {e}")
        return {
            "url": url,
            "status": "error",
            "error": str(e),
            "method": "requests"
        }


def is_js_heavy(html: str) -> bool:
    """
    Detect if page likely needs JS rendering.
    Looks for common JS framework markers and loading/placeholder patterns.
    """
    html_lower = html.lower()
    return any(indicator in html_lower for indicator in JS_HEAVY_INDICATORS)


def extract_meta_description(soup: BeautifulSoup) -> str:
    """Extract meta description."""
    meta = soup.find("meta", attrs={"name": "description"})
    return meta.get("content", "").strip() if meta else ""


def extract_company_name(soup: BeautifulSoup) -> str:
    """
    Extract company name from common patterns.
    Checks: og:site_name, h1, title, and h1 text.
    """
    # Check og:site_name
    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content", "").strip():
        return og_site.get("content", "").strip()
    
    # Check h1
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text().strip()
        if text:
            return text
    
    # Fallback: title tag
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    
    return ""


def extract_emails(soup: BeautifulSoup) -> List[str]:
    """Extract unique email addresses from page text."""
    text = soup.get_text()
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    return list(set(emails))  # Dedupe


def extract_phone(soup: BeautifulSoup) -> str:
    """
    Extract first phone number found (US/intl format).
    Pattern matches +1-234-567-8900, (234) 567-8900, 234.567.8900, etc.
    """
    text = soup.get_text()
    # Flexible phone pattern
    phone_pattern = r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}'
    match = re.search(phone_pattern, text)
    return match.group(0).strip() if match else ""


def parse_scraped_html(url: str, html: str) -> Dict[str, Any]:
    """
    Parse HTML into a structured lead record.
    Compatible with Bright Data record format.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove script/style noise
        for tag in soup(["script", "style"]):
            tag.decompose()
        
        record = {
            "url": url,
            "title": (soup.title.string if soup.title else "").strip(),
            "description": extract_meta_description(soup),
            "company_name": extract_company_name(soup),
            "emails": extract_emails(soup),
            "phone": extract_phone(soup),
            "text": soup.get_text()[:3000].strip(),  # First 3k chars of clean text
            "status": "success",
        }
        return record
    except Exception as e:
        logger.error(f"Error parsing HTML from {url}: {e}")
        return {
            "url": url,
            "status": "error",
            "error": f"Parse error: {str(e)}",
        }


async def scrape_urls(urls: List[str], use_playwright: bool = True, respectful_delay: float = 0.5) -> List[Dict[str, Any]]:
    """
    Main async scraper: tries requests first (fast), falls back to Playwright for JS-heavy sites.
    Returns records compatible with Bright Data format.
    
    Args:
        urls: List of URLs to scrape
        use_playwright: If True, uses Playwright for detected JS-heavy sites
        respectful_delay: Seconds to sleep between requests (be respectful to servers)
    
    Returns:
        List of structured lead records
    """
    records = []
    
    for i, url in enumerate(urls):
        logger.info(f"Scraping [{i+1}/{len(urls)}] {url}")
        
        # Try fast method first
        result = scrape_with_requests(url)
        
        # If successful and Playwright enabled, check if we need JS rendering
        if result["status"] == "success" and use_playwright and PLAYWRIGHT_AVAILABLE:
            if is_js_heavy(result["html"]):
                logger.info(f"  → JS detected, retrying with Playwright...")
                result = await scrape_with_playwright(url)
        
        # Parse HTML and extract structured fields
        if result["status"] == "success":
            record = parse_scraped_html(url, result.get("html", ""))
            record["scrape_method"] = result["method"]
        else:
            record = {
                "url": url,
                "status": "error",
                "error": result.get("error", "Unknown error"),
                "scrape_method": result["method"]
            }
        
        records.append(record)
        
        # Be respectful to servers
        if i < len(urls) - 1:
            await asyncio.sleep(respectful_delay)
    
    return records


def scrape_urls_sync(urls: List[str], use_playwright: bool = True) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for the async scraper.
    Use this from your sync code (e.g., Streamlit).
    """
    return asyncio.run(scrape_urls(urls, use_playwright=use_playwright))
