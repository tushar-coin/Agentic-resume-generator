from __future__ import annotations

import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


JOB_DESCRIPTION_SELECTORS = [
    "[data-testid='job-description']",
    "[class*='job-description']",
    "[class*='description']",
    "[id*='job-description']",
    "main",
    "section",
]


def scrape_job_description(url: str, wait_seconds: int = 4) -> str:
    """Scrape a job description with CSS selector fallbacks."""
    if not url:
        return ""

    print(f"DEBUG scraper: opening {url}")
    driver = None

    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        driver = webdriver.Chrome(options=options)
        driver.get(url)
        time.sleep(wait_seconds)

        for selector in JOB_DESCRIPTION_SELECTORS:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            text = "\n".join(
                element.text.strip()
                for element in elements
                if len(element.text.strip()) > 200
            )
            if text:
                print(f"DEBUG scraper: matched selector {selector}")
                return text

        print("DEBUG scraper: falling back to body text")
        return driver.find_element(By.TAG_NAME, "body").text

    except Exception as exc:
        print(f"DEBUG scraper: failed to scrape URL: {exc}")
        return ""

    finally:
        if driver:
            driver.quit()
