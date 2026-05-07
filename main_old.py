# ================================
# LOCAL RAG PIPELINE (OLLAMA + QWEN)
# ================================

# Requirements:
# pip install -r requirements.txt

import os
import ollama
import chromadb
from sentence_transformers import SentenceTransformer
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# ================================
# STEP 1 — EMBEDDING FUNCTION
# ================================
def get_embedding(text: str, model: SentenceTransformer):
    return model.encode(text).tolist()

# ================================
# STEP 2 — VECTOR DB SETUP
# ================================
client = chromadb.Client()
collection = client.get_or_create_collection(name="knowledge_base")

def add_document(doc_id, text, embedding):
    collection.add(
        ids=[doc_id],
        documents=[text],
        embeddings=[embedding]
    )

def query_vector_db(query_embedding, k=3):
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k
    )
    return results["documents"][0]

# ================================
# STEP 3 — CHUNKING
# ================================
def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i+chunk_size])
    return chunks

# ================================
# STEP 4 — INGESTION
# ================================
# ================================
# STEP 4.1 — SCRAPE JOB DESCRIPTION (OPTIONAL)
# ================================
def scrape_job_description(url: str):
    if not url:
        return None

    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(5)

        possible_selectors = [
            "div[data-testid='job-description']",
            "div[class*='job-description']",
            "section"
        ]

        for selector in possible_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                text = "\n".join([el.text for el in elements if len(el.text) > 200])
                if text:
                    return text

        # fallback
        return driver.find_element(By.TAG_NAME, "body").text

    except Exception as e:
        print(f"Error scraping URL: {e}")
        return None

    finally:
        try:
            driver.quit()
        except:
            pass

def clean_text(text: str):
    junk_keywords = [
        "Sign Up", "Job Alerts", "Blog", "Career Tips",
        "Saved Jobs", "Apply Now", "Search Jobs"
    ]

    lines = []
    for line in text.split("\n"):
        line = line.strip()

        if len(line) < 40:
            continue

        if any(junk in line for junk in junk_keywords):
            continue

        lines.append(line)

    return "\n".join(lines)

def ingest_text(source_id, text, model):
    chunks = chunk_text(text)

    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk, model)
        add_document(f"{source_id}_{i}", chunk, embedding)

    print(f"Ingested {len(chunks)} chunks from {source_id}")

def ingest_file(filepath, model):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    ingest_text(filepath, text, model)

# ================================
# STEP 5 — QUERY PIPELINE
# ================================
def ask(query: str, model: SentenceTransformer):
    query_embedding = get_embedding(query, model)

    docs = query_vector_db(query_embedding, k=3)
    print("DEBUG: Retrieved context:", docs)
    context = "\n\n".join(docs)

    prompt = f"""
You are a helpful assistant.

Answer ONLY from the context below.
If the answer is not present, say "I don't know".

Context:
{context}

Question:
{query}
"""

    response = ollama.chat(
        model="mistral:7b",
        messages=[{"role": "user", "content": prompt}]
    )
    print("DEBUG: Full response:", response)  # Debugging line
    return response["message"]["content"]

# ================================
# STEP 6 — MAIN LOOP
# ================================
if __name__ == "__main__":
    # Make sure you have a file at data/sample.txt
    data_path = "data/sample.txt"
    url = "https://jobs.intuit.com/job/bengaluru/senior-accountant-fixed-assets/27595/94325217600?_gl=1*mwfukc*_gcl_au*MjY1NTcxMTUyLjE3Nzc2ODIzMzc.*_ga*Mzk0NzMyMzA2LjE3NjMwNjAwNDc.*_ga_B0XHEYG9RN*czE3Nzc2ODIzMzckbzEkZzAkdDE3Nzc2ODIzMzckajYwJGwwJGgw&cid=seo_google"  # Put a job URL here only when you want to add scraped context.
    model = SentenceTransformer("BAAI/bge-small-en-v1.5")

    ingest_file(data_path, model)

    # Optional: scrape job description
    scraped_text = scrape_job_description(url)

    if scraped_text:
        print("Ingesting scraped job description...")

        cleaned = clean_text(scraped_text)

        print("DEBUG CLEANED TEXT PREVIEW:\n", cleaned[:5000])

        ingest_text("url", cleaned, model)

    # Interactive loop
    print("\nRAG system ready. Ask questions (type 'exit' to quit):\n")

    while True:
        q = input(">> ")
        if q.lower() in ["exit", "quit"]:
            break

        answer = ask(q, model)
        print("\n", answer, "\n")
