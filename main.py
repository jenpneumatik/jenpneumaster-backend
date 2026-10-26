from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import re
import urllib.parse
from bs4 import BeautifulSoup

app = FastAPI(title="JENPNEUMASTER Force-Calculator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryModel(BaseModel):
    query: str

@app.post("/api/analyze")
async def analyze_component(data: QueryModel):
    artikel = data.query.strip()
    if not artikel:
        raise HTTPException(status_code=400, detail="Keine Artikelnummer angegeben.")
    
    encoded_query = urllib.parse.quote(artikel)
    upper_art = artikel.upper()
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}+Pneumatik+Hydraulik+Datenblatt"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Standardwerte (Anti-Halluzination: Standard ist "Keine Angaben")
    detected_mfg = "Keine Angaben"
    detected_type = "Unbekannte Komponente"
    is_cylinder = False
    is_hydraulic = "HYD" in upper_art or "ENERPAC" in upper_art
    
    kolben_d = None
    stange_d = None
    hub_val = "Keine Angaben"

    try:
        resp = requests.get(search_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            snippets = soup.find_all('a', class_='result__snippet')
            page_text = " ".join([s.get_text() for s in snippets]).upper()
            
            if "AIRTEC" in page_text: detected_mfg = "Airtec"
            elif "FESTO" in page_text: detected_mfg = "Festo"
            elif "SMC" in page_text: detected_mfg = "SMC"
            elif "LANDEFELD" in page_text: detected_mfg = "Landefeld (Gelistet)"

            if "ZYLINDER" in page_text or "DSW" in upper_art or "DSBC" in upper_art:
                detected_type = "Pneumatik-Zylinder" if not is_hydraulic else "Hydraulik-Zylinder"
                is_cylinder = True
            elif "VENTIL" in page_text or "VALVE" in page_text:
                detected_type = "Pneumatik-Ventil"
    except Exception as e:
        print(f"Suchfehler: {e}")

    # Fallback-Erkennung für Zylinder anhand der Artikelbezeichnung (z.B. DSWPM 32/10)
    if "DSW" in upper_art or "DSBC" in upper_art or "DNC" in upper_art or "ADN" in upper_art:
        is_cylinder = True
        detected_type = "Pneumatik-Zylinder (ISO)"

    # Extraktion von Kolben-Ø und Hub aus der Artikelnummer, falls vorhanden
    dia_match = re.search(r'\b(12|16|20|25|32|40|50|63|80|100|125|160|200)\b', upper_art)
    if dia_match:
        kolben_d = float(dia_match.group(1))
        # ISO Stangendurchmesser Zuordnung
        stange_d = 6.0 if kolben_d <= 12 else (8.0 if kolben_d == 16 else (10.0 if kolben_d == 20 else (12.0 if kolben_d == 32 else (16.0 if kolben_d == 40 else 20.0))))

    stroke_match = re.search(r'[/\-](\d{1,4})\b', upper_art)
    if stroke_match:
        hub_val = stroke_match.group(1) + " mm"

    # Spezifikationen aufbauen
    specs = {
        "Hersteller": detected_mfg,
        "Komponententyp": detected_type,
        "Kolben-Durchmesser": f"{int(kolben_d)} mm" if kolben_d else "Keine Angaben",
        "Hublänge": hub_val,
        "Stangendurchmesser": f"{int(stange_d)} mm" if stange_d else "Keine Angaben",
        "Betriebsdruck max.": "10 bar (Pneumatik)" if not is_hydraulic else "210 bar (Hydraulik)"
    }

    spare_parts = [
        {
            "bezeichnung": f"Dichtsatz für Kolben-Ø {int(kolben_d)} mm" if kolben_d else "Standard Dichtsatz",
            "verwendung": "Verschleißteil-Kit",
            "artikelnummer": f"DS-{artikel.replace(' ', '-')}",
            "preis": "Auf Anfrage / Im Shop prüfen"
        }
    ]

    merchants = [
        {
            "name": "jenpneumatik Shop",
            "subtitle": "Hauseigener Fachvertrieb",
            "price": "Prüfung ausstehend",
            "delivery": "Auf Anfrage",
            "link": f"https://www.google.com/search?q=site:jenpneumatik.de+{encoded_query}"
        },
        {
            "name": "Landefeld Shop",
            "subtitle": "Partner für Pneumatik & Hydraulik",
            "price": "Im Shop prüfen",
            "delivery": "Live-Prüfung",
            "link": f"https://www.landefeld.de/gruppe/de/?q={encoded_query}"
        },
        {
            "name": "RS Components",
            "subtitle": "B2B-Katalog",
            "price": "Direkt im Shop",
            "delivery": "Katalogprüfung",
            "link": f"https://de.rs-online.com/web/c/?searchTerm={encoded_query}"
        }
    ]

    return {
        "query": artikel,
        "kategorie": detected_type,
        "hersteller": detected_mfg,
        "is_cylinder": is_cylinder,
        "is_hydraulic": is_hydraulic,
        "kolben_mm": kolben_d,
        "stange_mm": stange_d,
        "datenblatt_pdf": f"https://www.google.com/search?q={encoded_query}+Datenblatt+filetype:pdf",
        "spezifikationen": specs,
        "ersatzteile": spare_parts,
        "haendler": merchants
    }