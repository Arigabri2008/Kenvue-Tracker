"""
Kenvue Price Tracker — Scraper
================================
Extrae precios de productos Kenvue en retailers españoles y actualiza prices.json.
El dashboard HTML carga ese JSON automáticamente en cada visita.

Instalación:
    pip install playwright httpx beautifulsoup4 lxml
    playwright install chromium

Uso:
    python scraper.py                 # scraping completo
    python scraper.py --retailer primor   # solo un retailer
    python scraper.py --dry-run       # muestra URLs sin raspar

Automatización (GitHub Actions o cron):
    # crontab -e → ejecutar cada lunes a las 6:00 AM
    0 6 * * 1 cd /ruta/proyecto && python scraper.py >> logs/scraper.log 2>&1
"""

import asyncio
import json
import re
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import argparse

# ── Dependencias ──────────────────────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    print("Faltan dependencias. Ejecuta:\n  pip install playwright httpx beautifulsoup4 lxml\n  playwright install chromium")
    raise SystemExit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("kenvue")

# ── Constantes ────────────────────────────────────────────────────────────────
OUTPUT_FILE = Path(__file__).parent / "prices.json"
TIMEOUT_MS  = 25_000
MAX_RETRIES = 2

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ── Modelo de datos ───────────────────────────────────────────────────────────
@dataclass
class PriceRecord:
    group_key:  str
    product:    str
    brand:      str
    category:   str
    retailer:   str
    pvp:        Optional[float]   # precio actual
    pvr:        Optional[float]   # precio tachado / PVR
    volume_ml:  Optional[int]
    url:        str
    scraped_at: str               # ISO-8601
    ok:         bool              # True = precio extraído con éxito

# ── Catálogo de URLs por producto×retailer ────────────────────────────────────
# Estructura: (group_key, product_name, brand, category, volume_ml, retailer, url)
# Añade o elimina filas según tu surtido real.
CATALOG = [

    # ── JOHNSON'S ─────────────────────────────────────────────────────────────
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Primor",          "https://www.primor.eu/es_es/johnsons-baby-champu-clasico-gold-300ml.html"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Druni",           "https://www.druni.es/johnsons-baby-champu-clasico-gold-300ml"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Marvimundo",      "https://www.marvimundo.com/johnsons-baby-champu-clasico-gold-300ml"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Alcampo",         "https://www.alcampo.es/compra-online/higiene-y-belleza/higiene-bebe/champu-bebe/johnsons-baby-champu-clasico-300ml"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Carrefour",       "https://www.carrefour.es/supermercado/champu-clasico-para-pelo-suave-brillante-e-hidratado-johnsons-baby-300-ml/R-prod1120668/p"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "El Corte Inglés", "https://www.elcorteingles.es/supermercado/A40266756-johnson-s-baby-champu-clasico-gold-300-ml/"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Eroski",          "https://supermercado.eroski.es/es/alimentacion/johnsons-baby-champu-clasico-300ml/"),
    ("jb-champu-clasico-300", "Champú Clásico Gold 300ml", "Johnson's", "Bebé", 300,
     "Amazon ES",       "https://www.amazon.es/dp/B07H9H5GLP"),

    ("jb-champu-clasico-750", "Champú Clásico Gold 750ml", "Johnson's", "Bebé", 750,
     "Primor",          "https://www.primor.eu/es_es/johnsons-baby-champu-clasico-gold-750ml.html"),
    ("jb-champu-clasico-750", "Champú Clásico Gold 750ml", "Johnson's", "Bebé", 750,
     "Druni",           "https://www.druni.es/johnsons-baby-champu-clasico-gold-750ml"),
    ("jb-champu-clasico-750", "Champú Clásico Gold 750ml", "Johnson's", "Bebé", 750,
     "Carrefour",       "https://www.carrefour.es/supermercado/champu-clasico-para-pelo-suave-brillante-e-hidratado-johnsons-baby-750-ml/R-prod1120669/p"),
    ("jb-champu-clasico-750", "Champú Clásico Gold 750ml", "Johnson's", "Bebé", 750,
     "Amazon ES",       "https://www.amazon.es/dp/B07HBFNLPQ"),

    ("jb-gel-bano-500", "Gel de Baño Dulces Sueños 500ml", "Johnson's", "Bebé", 500,
     "Primor",          "https://www.primor.eu/es_es/johnsons-baby-gel-de-bano-dulces-suenos-500ml.html"),
    ("jb-gel-bano-500", "Gel de Baño Dulces Sueños 500ml", "Johnson's", "Bebé", 500,
     "Carrefour",       "https://www.carrefour.es/supermercado/gel-de-bano-dulces-suenos-johnsons-baby-500-ml/R-prod1068218/p"),
    ("jb-gel-bano-500", "Gel de Baño Dulces Sueños 500ml", "Johnson's", "Bebé", 500,
     "Amazon ES",       "https://www.amazon.es/dp/B07BF1TJC7"),

    ("jb-locion-500", "Loción Hidratante Bebé 500ml", "Johnson's", "Bebé", 500,
     "Primor",          "https://www.primor.eu/es_es/johnsons-baby-locion-hidratante-500ml.html"),
    ("jb-locion-500", "Loción Hidratante Bebé 500ml", "Johnson's", "Bebé", 500,
     "Carrefour",       "https://www.carrefour.es/supermercado/locion-hidratante-johnsons-baby-500-ml/R-prod1068220/p"),
    ("jb-locion-500", "Loción Hidratante Bebé 500ml", "Johnson's", "Bebé", 500,
     "Amazon ES",       "https://www.amazon.es/dp/B00BYAENDK"),

    # ── LE PETIT MARSEILLAIS ──────────────────────────────────────────────────
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Primor",          "https://www.primor.eu/es_es/le-petit-marseillais-gel-de-ducha-melocoton-400ml.html"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Druni",           "https://www.druni.es/le-petit-marseillais-gel-ducha-melocoton-400ml"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Alcampo",         "https://www.alcampo.es/compra-online/higiene-y-belleza/gel-de-ducha/le-petit-marseillais-gel-ducha-melocoton-400ml"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Carrefour",       "https://www.carrefour.es/supermercado/gel-de-bano-melocoton-le-petit-marseillais-400-ml/R-prod440186/p"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Mercadona",       "https://tienda.mercadona.es/product/77236/le-petit-marseillais-gel-ducha-melocoton"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "DIA",             "https://www.dia.es/compra/higiene-y-salud/higiene-corporal/geles-de-bano-y-ducha/gel-ducha-melocoton-le-petit-marseillais-400ml"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Amazon ES",       "https://www.amazon.es/dp/B00R7CLMFW"),
    ("lpm-gel-melocoton-400", "Gel Ducha Melocotón 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Eroski",          "https://supermercado.eroski.es/es/alimentacion/le-petit-marseillais-gel-ducha-melocoton-400ml/"),

    ("lpm-locion-karite", "Loción Hidratante Karité 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Carrefour",       "https://www.carrefour.es/supermercado/crema-corporal-karite-le-petit-marseillais-400-ml/R-prod440187/p"),
    ("lpm-locion-karite", "Loción Hidratante Karité 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Mercadona",       "https://tienda.mercadona.es/product/77237/le-petit-marseillais-crema-corporal-karite"),
    ("lpm-locion-karite", "Loción Hidratante Karité 400ml", "Le Petit Marseillais", "Cuidado corporal", 400,
     "Amazon ES",       "https://www.amazon.es/dp/B00S4JO2IC"),

    ("lpm-crema-manos-karite", "Crema de Manos Karité 75ml", "Le Petit Marseillais", "Manos", 75,
     "Carrefour",       "https://www.carrefour.es/supermercado/crema-de-manos-karite-le-petit-marseillais-75-ml/R-prod440189/p"),
    ("lpm-crema-manos-karite", "Crema de Manos Karité 75ml", "Le Petit Marseillais", "Manos", 75,
     "Mercadona",       "https://tienda.mercadona.es/product/77240/le-petit-marseillais-crema-manos-karite"),
    ("lpm-crema-manos-karite", "Crema de Manos Karité 75ml", "Le Petit Marseillais", "Manos", 75,
     "DIA",             "https://www.dia.es/compra/higiene-y-salud/higiene-corporal/cremas-de-manos/crema-manos-karite-le-petit-marseillais-75ml"),

    # ── OGX ──────────────────────────────────────────────────────────────────
    ("ogx-champu-argan-385", "Champú Argán Oil of Morocco 385ml", "OGX", "Cuidado capilar", 385,
     "Primor",          "https://www.primor.eu/es_es/ogx-champu-argan-oil-of-morocco-385ml.html"),
    ("ogx-champu-argan-385", "Champú Argán Oil of Morocco 385ml", "OGX", "Cuidado capilar", 385,
     "Druni",           "https://www.druni.es/ogx-champu-argan-oil-of-morocco-385ml"),
    ("ogx-champu-argan-385", "Champú Argán Oil of Morocco 385ml", "OGX", "Cuidado capilar", 385,
     "Marvimundo",      "https://www.marvimundo.com/ogx-champu-argan-oil-of-morocco-385ml"),
    ("ogx-champu-argan-385", "Champú Argán Oil of Morocco 385ml", "OGX", "Cuidado capilar", 385,
     "Alcampo",         "https://www.alcampo.es/compra-online/higiene-y-belleza/champu/ogx-champu-argan-oil-morocco-385ml"),
    ("ogx-champu-argan-385", "Champú Argán Oil of Morocco 385ml", "OGX", "Cuidado capilar", 385,
     "El Corte Inglés", "https://www.elcorteingles.es/supermercado/A40000001-ogx-champu-argan-oil-of-morocco-385ml/"),
    ("ogx-champu-argan-385", "Champú Argán Oil of Morocco 385ml", "OGX", "Cuidado capilar", 385,
     "Amazon ES",       "https://www.amazon.es/dp/B07C59VFGT"),

    ("ogx-champu-biotin-385", "Champú Biotin & Collagen 385ml", "OGX", "Cuidado capilar", 385,
     "Primor",          "https://www.primor.eu/es_es/ogx-champu-biotin-collagen-385ml.html"),
    ("ogx-champu-biotin-385", "Champú Biotin & Collagen 385ml", "OGX", "Cuidado capilar", 385,
     "Druni",           "https://www.druni.es/ogx-champu-biotin-collagen-385ml"),
    ("ogx-champu-biotin-385", "Champú Biotin & Collagen 385ml", "OGX", "Cuidado capilar", 385,
     "Amazon ES",       "https://www.amazon.es/dp/B07C5H4DKB"),

    ("ogx-cond-argan-385", "Acondicionador Argán Oil 385ml", "OGX", "Cuidado capilar", 385,
     "Primor",          "https://www.primor.eu/es_es/ogx-acondicionador-argan-oil-of-morocco-385ml.html"),
    ("ogx-cond-argan-385", "Acondicionador Argán Oil 385ml", "OGX", "Cuidado capilar", 385,
     "Amazon ES",       "https://www.amazon.es/dp/B07C5HFNX8"),

    # ── CAREFREE ─────────────────────────────────────────────────────────────
    ("cf-cotton-x30", "Protegeslip Cotton Feel x30", "Carefree", "Higiene femenina", None,
     "Primor",          "https://www.primor.eu/es_es/carefree-cotton-feel-protegeslip-30u.html"),
    ("cf-cotton-x30", "Protegeslip Cotton Feel x30", "Carefree", "Higiene femenina", None,
     "Carrefour",       "https://www.carrefour.es/supermercado/protege-slips-carefree-cotton-feel-30-ud/R-prod355174/p"),
    ("cf-cotton-x30", "Protegeslip Cotton Feel x30", "Carefree", "Higiene femenina", None,
     "Alcampo",         "https://www.alcampo.es/compra-online/higiene-y-belleza/higiene-femenina/protegeslips/carefree-cotton-feel-30ud"),
    ("cf-cotton-x30", "Protegeslip Cotton Feel x30", "Carefree", "Higiene femenina", None,
     "DIA",             "https://www.dia.es/compra/higiene-y-salud/higiene-femenina/protegeslips/carefree-cotton-feel-30ud"),
    ("cf-cotton-x30", "Protegeslip Cotton Feel x30", "Carefree", "Higiene femenina", None,
     "Amazon ES",       "https://www.amazon.es/dp/B00E6LDPZ8"),

    ("cf-ultrafine-x58", "Protegeslip Ultrafine x58", "Carefree", "Higiene femenina", None,
     "Primor",          "https://www.primor.eu/es_es/carefree-protegeslip-ultrafine-58u.html"),
    ("cf-ultrafine-x58", "Protegeslip Ultrafine x58", "Carefree", "Higiene femenina", None,
     "Carrefour",       "https://www.carrefour.es/supermercado/protege-slips-carefree-ultrafine-58-ud/R-prod355175/p"),
    ("cf-ultrafine-x58", "Protegeslip Ultrafine x58", "Carefree", "Higiene femenina", None,
     "DIA",             "https://www.dia.es/compra/higiene-y-salud/higiene-femenina/protegeslips/carefree-ultrafine-58ud"),
    ("cf-ultrafine-x58", "Protegeslip Ultrafine x58", "Carefree", "Higiene femenina", None,
     "Amazon ES",       "https://www.amazon.es/dp/B07K3P7GVQ"),

    # ── O.B. ─────────────────────────────────────────────────────────────────
    ("ob-digital-normal", "Tampones Digital Normal x16", "o.b.", "Higiene femenina", None,
     "Primor",          "https://www.primor.eu/es_es/ob-tampones-digital-normal-16u.html"),
    ("ob-digital-normal", "Tampones Digital Normal x16", "o.b.", "Higiene femenina", None,
     "Carrefour",       "https://www.carrefour.es/supermercado/tampones-digital-ob-normal-16-ud/R-prod355180/p"),
    ("ob-digital-normal", "Tampones Digital Normal x16", "o.b.", "Higiene femenina", None,
     "Alcampo",         "https://www.alcampo.es/compra-online/higiene-y-belleza/higiene-femenina/tampones/ob-tampones-digital-normal-16ud"),
    ("ob-digital-normal", "Tampones Digital Normal x16", "o.b.", "Higiene femenina", None,
     "DIA",             "https://www.dia.es/compra/higiene-y-salud/higiene-femenina/tampones/ob-digital-normal-16ud"),
    ("ob-digital-normal", "Tampones Digital Normal x16", "o.b.", "Higiene femenina", None,
     "Amazon ES",       "https://www.amazon.es/dp/B008UIMNM8"),

    ("ob-procomfort-normal", "Tampones ProComfort Normal x16", "o.b.", "Higiene femenina", None,
     "Primor",          "https://www.primor.eu/es_es/ob-tampones-procomfort-normal-16u.html"),
    ("ob-procomfort-normal", "Tampones ProComfort Normal x16", "o.b.", "Higiene femenina", None,
     "Carrefour",       "https://www.carrefour.es/supermercado/tampones-procomfort-ob-normal-16-ud/R-prod355181/p"),
    ("ob-procomfort-normal", "Tampones ProComfort Normal x16", "o.b.", "Higiene femenina", None,
     "Amazon ES",       "https://www.amazon.es/dp/B008UIN3YC"),
]

# ── Extractores por retailer ───────────────────────────────────────────────────
# Cada función recibe el HTML de la página y devuelve (pvp, pvr) o (None, None).

def _clean_price(text: str) -> Optional[float]:
    """'12,99 €' → 12.99   '  9.95€  ' → 9.95   '' → None"""
    if not text:
        return None
    text = re.sub(r"[^\d,\.]", "", text.strip())
    text = text.replace(",", ".")
    try:
        val = float(text)
        return round(val, 2) if 0.10 < val < 500 else None
    except ValueError:
        return None


def extract_primor(html: str):
    soup = BeautifulSoup(html, "lxml")
    # PVP: .product-price .value, or [data-price-amount]
    pvp_tag = (soup.select_one(".product-info-price .special-price .price") or
               soup.select_one(".product-info-price .price"))
    pvr_tag = soup.select_one(".old-price .price")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), \
           _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_druni(html: str):
    soup = BeautifulSoup(html, "lxml")
    pvp_tag = (soup.select_one(".product-info-price .special-price .price") or
               soup.select_one("[itemprop='price']"))
    pvr_tag = soup.select_one(".old-price .price")
    pvp = _clean_price(pvp_tag.get("content", pvp_tag.get_text()) if pvp_tag else "")
    pvr = _clean_price(pvr_tag.get_text() if pvr_tag else "")
    return pvp, pvr


def extract_marvimundo(html: str):
    soup = BeautifulSoup(html, "lxml")
    pvp_tag = soup.select_one(".price-box .price, [data-price-type='finalPrice'] .price")
    pvr_tag = soup.select_one("[data-price-type='oldPrice'] .price")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), \
           _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_carrefour(html: str):
    soup = BeautifulSoup(html, "lxml")
    # Carrefour usa data-testid y también JSON-LD
    pvp_tag = soup.select_one("[data-testid='product-price'] .buyable-product-price__integer, .product-price__integer")
    pvp_dec  = soup.select_one("[data-testid='product-price'] .buyable-product-price__decimal, .product-price__decimal")
    pvr_tag = soup.select_one(".previous-price, .product-price--previous .product-price__integer")
    if pvp_tag and pvp_dec:
        try:
            pvp = float(f"{pvp_tag.get_text().strip()}.{pvp_dec.get_text().strip()}")
        except Exception:
            pvp = _clean_price(pvp_tag.get_text())
    else:
        # fallback: JSON-LD
        ld = soup.find("script", {"type": "application/ld+json"})
        pvp = None
        if ld:
            try:
                data = json.loads(ld.string or "")
                offers = data.get("offers", {})
                pvp = _clean_price(str(offers.get("price", "")))
            except Exception:
                pass
    return pvp, _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_eci(html: str):
    soup = BeautifulSoup(html, "lxml")
    pvp_tag = soup.select_one(".now-price, .price-sales, [data-testid='price-sales']")
    pvr_tag = soup.select_one(".was-price, .price-standard, [data-testid='price-standard']")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), \
           _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_mercadona(html: str):
    # Mercadona usa una SPA React — el precio está en __NEXT_DATA__ o window.__remixContext
    soup = BeautifulSoup(html, "lxml")
    # Intento 1: JSON embebido
    for script in soup.find_all("script", {"id": "__NEXT_DATA__"}):
        try:
            data = json.loads(script.string)
            price_str = str(data).lower()
            # Buscar patrón "price":X.XX
            match = re.search(r'"price"\s*:\s*([\d.]+)', price_str)
            if match:
                return float(match.group(1)), None
        except Exception:
            pass
    # Intento 2: selector visual
    pvp_tag = soup.select_one(".product-cell__price-current, [data-testid='product-price']")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), None


def extract_dia(html: str):
    soup = BeautifulSoup(html, "lxml")
    pvp_tag = soup.select_one(".product-price__value, .pdp-price__value, [data-qa='product-price']")
    pvr_tag = soup.select_one(".product-price__previous, .pdp-price__previous")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), \
           _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_amazon(html: str):
    soup = BeautifulSoup(html, "lxml")
    # Amazon: .a-price-whole + .a-price-fraction
    whole = soup.select_one(".a-price.priceToPay .a-price-whole, #priceblock_ourprice .a-price-whole")
    frac  = soup.select_one(".a-price.priceToPay .a-price-fraction, #priceblock_ourprice .a-price-fraction")
    pvr_tag = soup.select_one(".a-price.a-text-price .a-offscreen, #priceblock_dealprice")
    pvp = None
    if whole:
        w = re.sub(r"\D", "", whole.get_text())
        f = re.sub(r"\D", "", frac.get_text()) if frac else "00"
        try:
            pvp = float(f"{w}.{f[:2]}")
        except Exception:
            pass
    return pvp, _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_alcampo(html: str):
    soup = BeautifulSoup(html, "lxml")
    pvp_tag = soup.select_one(".product-price__value, .price__integer, [data-qa='price']")
    pvr_tag = soup.select_one(".product-price__previous, .price-previous")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), \
           _clean_price(pvr_tag.get_text() if pvr_tag else "")


def extract_eroski(html: str):
    soup = BeautifulSoup(html, "lxml")
    pvp_tag = soup.select_one(".product-price, .price-main, [data-testid='product-price']")
    pvr_tag = soup.select_one(".product-price--previous, .price-previous")
    return _clean_price(pvp_tag.get_text() if pvp_tag else ""), \
           _clean_price(pvr_tag.get_text() if pvr_tag else "")


EXTRACTORS = {
    "Primor":          extract_primor,
    "Druni":           extract_druni,
    "Marvimundo":      extract_marvimundo,
    "Carrefour":       extract_carrefour,
    "El Corte Inglés": extract_eci,
    "Mercadona":       extract_mercadona,
    "DIA":             extract_dia,
    "Amazon ES":       extract_amazon,
    "Alcampo":         extract_alcampo,
    "Eroski":          extract_eroski,
}

# ── Motor de scraping ─────────────────────────────────────────────────────────

async def scrape_page(browser, entry: tuple, dry_run: bool = False) -> PriceRecord:
    group_key, product, brand, category, volume_ml, retailer, url = entry
    now = datetime.now(timezone.utc).isoformat()

    if dry_run:
        log.info(f"[DRY] {retailer:20s} {product[:40]}")
        return PriceRecord(group_key, product, brand, category, retailer,
                           None, None, volume_ml, url, now, False)

    extractor = EXTRACTORS.get(retailer)
    if not extractor:
        log.warning(f"Sin extractor para {retailer}")
        return PriceRecord(group_key, product, brand, category, retailer,
                           None, None, volume_ml, url, now, False)

    for attempt in range(1, MAX_RETRIES + 1):
        page = None
        try:
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 800},
                locale="es-ES",
                extra_http_headers={"Accept-Language": "es-ES,es;q=0.9"},
            )
            page = await context.new_page()
            # Bloquear assets pesados para ir más rápido
            await page.route("**/*.{png,jpg,jpeg,webp,gif,svg,woff2,woff,ttf}", lambda r: r.abort())

            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            await page.wait_for_timeout(random.randint(800, 1600))  # anti-bot delay

            html = await page.content()
            pvp, pvr = extractor(html)

            if pvp:
                log.info(f"✓ {retailer:20s} {product[:35]:35s} → {pvp:.2f}€" +
                         (f" (pvr {pvr:.2f}€)" if pvr else ""))
                return PriceRecord(group_key, product, brand, category, retailer,
                                   pvp, pvr, volume_ml, url, now, True)
            else:
                log.warning(f"✗ {retailer:20s} {product[:35]:35s} → precio no encontrado (intento {attempt})")

        except PWTimeout:
            log.warning(f"Timeout {retailer} — {url} (intento {attempt})")
        except Exception as e:
            log.warning(f"Error {retailer} — {e} (intento {attempt})")
        finally:
            if page:
                try:
                    await page.close()
                    await context.close()
                except Exception:
                    pass

        if attempt < MAX_RETRIES:
            await asyncio.sleep(random.uniform(2, 5))

    return PriceRecord(group_key, product, brand, category, retailer,
                       None, None, volume_ml, url, now, False)


async def run(retailer_filter: Optional[str] = None, dry_run: bool = False):
    entries = CATALOG
    if retailer_filter:
        rf = retailer_filter.lower()
        entries = [e for e in entries if rf in e[5].lower()]
        log.info(f"Filtrando por retailer '{retailer_filter}': {len(entries)} URLs")

    log.info(f"Iniciando scraping de {len(entries)} URLs…")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        # Procesar de 3 en 3 para no saturar
        semaphore = asyncio.Semaphore(3)

        async def bounded(entry):
            async with semaphore:
                return await scrape_page(browser, entry, dry_run)

        results = await asyncio.gather(*[bounded(e) for e in entries])
        await browser.close()

    # ── Serializar a JSON ──────────────────────────────────────────────────────
    ok_count  = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count

    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "ok": ok_count,
            "failed": fail_count,
        },
        "records": [asdict(r) for r in results],
    }

    if not dry_run:
        OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"\n{'─'*50}")
        log.info(f"✓ {ok_count} precios extraídos  ✗ {fail_count} fallidos")
        log.info(f"Guardado en {OUTPUT_FILE}")
    else:
        log.info(f"\nDry-run completado. Se procesarían {len(entries)} URLs.")

    return output


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kenvue Price Scraper")
    parser.add_argument("--retailer", help="Filtrar por nombre de retailer (ej: primor, amazon)")
    parser.add_argument("--dry-run", action="store_true", help="Muestra URLs sin hacer scraping")
    args = parser.parse_args()

    asyncio.run(run(
        retailer_filter=args.retailer,
        dry_run=args.dry_run,
    ))
