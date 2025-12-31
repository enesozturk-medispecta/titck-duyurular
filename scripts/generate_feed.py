#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/generate_feed.py

TİTCK duyurular sayfasından (ör. https://titck.gov.tr/duyuru?page=1) duyuruları çekip RSS (feed.xml) oluşturan betik.

Gereksinimler:
    pip install -r requirements.txt

Kullanım:
    python scripts/generate_feed.py
    python scripts/generate_feed.py --url "https://titck.gov.tr/duyuru?page=1" --output feed.xml --max-items 30
"""
from __future__ import annotations
import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from html import unescape
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from xml.etree import ElementTree as ET
from xml.dom import minidom
import email.utils

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
USER_AGENT = "titck-rss-generator/1.0 (+https://github.com/)"
DEFAULT_URL = "https://titck.gov.tr/duyuru?page=1"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

def fetch(url: str, timeout: int = 15) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text
    except Exception as e:
        logging.warning("İstek başarısız %s: %s", url, e)
        return None

def find_announcement_links(list_html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(list_html, "html.parser")

    links = []
    seen = set()

    # TİTCK list sayfasında duyuru linkleri genellikle belirli bir yapıdadır
    # Örnek: /duyuru/baslik-tarih-id
    # Ama bazıları farklı olabilir. Biz yine de geniş tarayıp sonra filtreleyelim.
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)

        if full in seen:
            continue

        # Filtreleme:
        # 1. 'duyuru' içermeli
        # 2. '?page=' (paginasyon) içermemeli
        # 3. 'duyuru?tab' gibi sekmeleri içermemeli
        # 4. javascript veya anchor olmamalı
        if "duyuru" in href.lower() or "/duyuru/" in href:
            if "?page=" in href or "javascript:" in href or href.startswith("#"):
                continue

            # Duyuru sayfaları genellikle /duyuru/ ile başlar ve devamında başlık gelir
            # Liste sayfası (/duyuru) ise filtrelenmeli
            path = urlparse(full).path
            if path == "/duyuru" or path == "/duyuru/":
                continue

            seen.add(full)
            links.append(full)

    logging.info("Bulunan gerçek duyuru sayısı: %d", len(links))
    return links

def clean_xml_string(s: str) -> str:
    """XML için geçersiz olan kontrol karakterlerini temizler."""
    if not s:
        return ""
    # XML 1.0 için yasal karakterler: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    # Kontrol karakterlerini (tab, newline, cr hariç) çıkaran regex
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)

def extract_from_announcement(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Başlık tespiti
    title = None
    title_el = soup.select_one(".page-content-title h1")
    if title_el:
        title = title_el.get_text(strip=True)
    
    if not title:
        for tag in ("h1", "h2", "h3"):
            t = soup.find(tag)
            if t and t.get_text(strip=True):
                title = t.get_text(strip=True)
                break
    
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        title = "Başlıksız duyuru"

    # Tarih tespiti
    pubdate = None
    date_el = soup.select_one(".content-text .date") or soup.select_one(".date")
    if date_el:
        pubdate = date_el.get_text(strip=True)
    
    if not pubdate:
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            pubdate = time_tag.get("datetime")
        elif time_tag and time_tag.get_text(strip=True):
            pubdate = time_tag.get_text(strip=True)

    if not pubdate:
        candidates = soup.find_all(attrs={"class": re.compile(r"(tarih|date|posted|time)", re.I)})
        candidates += soup.find_all(attrs={"id": re.compile(r"(tarih|date|posted|time)", re.I)})
        for c in candidates:
            txt = c.get_text(" ", strip=True)
            if txt and (re.search(r"\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}", txt) or re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", txt)):
                pubdate = txt
                break

    # İçerik tespiti
    content_html_tag = None
    selectors = [
        ".content-text",
        "article",
        "div.duyuru-content",
        "div.content",
        "div.icerik",
        "div#content",
        "div.panel-body",
        "#pageContent",
        "main"
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            content_html_tag = el
            break
    
    if not content_html_tag:
        content_html_tag = soup.body or soup

    # Çöpleri temizle (tarih divini içerikten çıkarabiliriz çünkü RSS'de zaten pubDate var)
    for bad in content_html_tag.select("script, style, nav, form, footer, header, .date"):
        bad.decompose()

    # İçeriği stringe çevir
    description = "".join(str(c) for c in content_html_tag.contents).strip()
    description = unescape(description)
    description = clean_xml_string(description)

    pubdate_rfc = ""
    if pubdate:
        try:
            # TİTCK bazen departman adını tarihin yanına yazıyor: "30.12.2025 - Denetim Hizmetleri"
            # Sadece tarih kısmını almaya çalışalım
            date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", pubdate)
            if date_match:
                dt_str = date_match.group(1)
                dt = datetime.strptime(dt_str, "%d.%m.%Y")
            else:
                dt = dateparser.parse(pubdate, dayfirst=True)
            
            if dt is not None:
                pubdate_rfc = email.utils.format_datetime(dt)
        except Exception:
            pubdate_rfc = ""

    return {
        "title": clean_xml_string(title),
        "link": page_url,
        "description": description,
        "pubDate": pubdate_rfc
    }

def build_rss(channel_title: str, channel_link: str, channel_desc: str, items: List[dict]) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = channel_link
    ET.SubElement(channel, "description").text = channel_desc
    ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(datetime.now(timezone.utc))

    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it.get("title") or ""
        ET.SubElement(item, "link").text = it.get("link") or ""
        ET.SubElement(item, "guid").text = it.get("link") or ""
        if it.get("pubDate"):
            ET.SubElement(item, "pubDate").text = it.get("pubDate")
        desc = ET.SubElement(item, "description")
        desc.text = it.get("description") or ""

    rough_string = ET.tostring(rss, "utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty = reparsed.toprettyxml(indent="  ", encoding="utf-8")
    return pretty.decode("utf-8")

def main():
    parser = argparse.ArgumentParser(description="Generate feed.xml from titck duyurular page")
    parser.add_argument("--url", "-u", default=DEFAULT_URL, help="Duyuru liste sayfası URL (default: %(default)s)")
    parser.add_argument("--output", "-o", default="feed.xml", help="Çıktı RSS dosyası (default: %(default)s)")
    parser.add_argument("--max-items", "-m", type=int, default=30, help="Maksimum çekilecek duyuru sayısı")
    args = parser.parse_args()

    list_html = fetch(args.url)
    if not list_html:
        logging.error("Liste sayfası alınamadı: %s", args.url)
        sys.exit(1)

    base_url = "{scheme}://{host}".format(scheme=urlparse(args.url).scheme, host=urlparse(args.url).netloc)
    links = find_announcement_links(list_html, base_url)
    if not links:
        logging.error("Duyuru linki bulunamadı. Site yapısı değişmiş olabilir.")
        sys.exit(1)

    items = []
    binary_extensions = (".pdf", ".docx", ".xlsx", ".xls", ".zip", ".jpg", ".png")
    
    for link in links[: args.max_items]:
        logging.info("İşleniyor: %s", link)
        
        # Eğer link bir dosya ise (pdf, xlsx vb), direkt link bilgisini alalım
        parsed_link = urlparse(link)
        if any(parsed_link.path.lower().endswith(ext) for ext in binary_extensions):
            filename = parsed_link.path.split("/")[-1]
            items.append({
                "title": f"Dosya: {filename}",
                "link": link,
                "description": f"Bu duyuru bir dosya bağlantısıdır: <a href='{link}'>{filename}</a>",
                "pubDate": email.utils.format_datetime(datetime.now(timezone.utc))
            })
            continue

        html = fetch(link)
        if not html:
            logging.warning("Duyuru sayfası alınamadı: %s", link)
            continue
        data = extract_from_announcement(html, link)
        items.append(data)

    channel_title = "TİTCK Duyurular (otomatik)"
    channel_link = args.url
    channel_desc = "T.C. Türkiye İlaç ve Tıbbi Cihaz Kurumu duyuruları (otomatik oluşturulmuş RSS)"
    rss_xml = build_rss(channel_title, channel_link, channel_desc, items)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(rss_xml)

    logging.info("RSS feed oluşturuldu: %s (öğe sayısı: %d)", args.output, len(items))

if __name__ == "__main__":
    main()
