from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import re
import io
import json
import os
import httpx
from datetime import datetime
from google.cloud import vision
from pydantic import BaseModel
from typing import List, Optional
from supabase import create_client, Client

app = FastAPI(title="API Arrivi Merce")

# Configurazione CORS per permettere al Frontend di comunicare con il Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In produzione, sostituisci con l'URL del tuo frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurazione Google Vision (ereditata da app.py)
if os.path.exists("chiave_google.json"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "chiave_google.json"
elif "GOOGLE_CREDENTIALS_JSON" in os.environ:
    # Se siamo in produzione (es. Render, Railway), creiamo un file temporaneo dai segreti
    with open("google_key_temp.json", "w") as f:
        f.write(os.environ["GOOGLE_CREDENTIALS_JSON"])
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_key_temp.json"

# Inizializzazione client Supabase (usando variabili d'ambiente)
url: str = os.environ.get("SUPABASE_URL", "...fallback...")
key: str = os.environ.get("SUPABASE_KEY", "")
supabase = None
if url and key:
    try:
        supabase = create_client(url, key)
    except Exception as e:
        print(f"Supabase client init failed, continuerò senza DB: {e}")
        supabase = None

def estrai_dati_chirurgica(testo_ocr: str):
    """Estrae dati dall'OCR - Focalizzato su Barcode, Peso e MQ"""
    righe = [r.strip().upper() for r in testo_ocr.split('\n') if r.strip()]
    t_completo = " ".join(righe)
    dati = {"barcode": "", "peso": 0, "mq": 0.0, "codice": "", "spessore": 0.0, "larghezza": 0}
    
    for i, riga in enumerate(righe):
        # Barcode (Pattern S + 9/10 cifre)
        if 'S' in riga:
            bc_match = re.search(r'S\s*(\d\s*){9,10}', riga)
            if bc_match: dati["barcode"] = re.sub(r'\s+', '', bc_match.group(0))
        
        # Peso
        if "NET" in riga or "KG" in riga:
            val_peso = re.findall(r'\b\d{4}\b', riga + " " + (righe[i+1] if i+1 < len(righe) else ""))
            for p in val_peso:
                if 500 < int(p) < 8000: dati["peso"] = int(p)

        # MQ
        if any(x in riga for x in ["MQ", "M2", "M²"]):
            val_mq = re.search(r'(\d+[.,]\d{1,3})', riga + " " + (righe[i+1] if i+1 < len(righe) else ""))
            if val_mq: dati["mq"] = float(val_mq.group(1).replace(',', '.'))
            
    return dati

@app.post("/api/analyze")
async def analyze_image(file: UploadFile = File(...)):
    """Riceve una foto e restituisce i dati estratti"""
    try:
        content = await file.read()
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        
        testo = response.text_annotations[0].description if response.text_annotations else ""
        dati = estrai_dati_chirurgica(testo)
        dati["nome_foto"] = file.filename
        return dati
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class NewSupplier(BaseModel):
    name: str

@app.get("/api/suppliers")
async def get_suppliers():
    if not supabase:
        return []
    
    all_data = []
    page = 0
    page_size = 1000
    
    try:
        while True:
            start = page * page_size
            end = start + page_size - 1
            response = supabase.table("db_mp_arrivi").select("Produttore/Fornitore").range(start, end).execute()
            
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < page_size:
                break
            page += 1
        
        # Pulizia avanzata: rimuove spazi multipli e converte in maiuscolo
        raw_names = [
            re.sub(r'\s+', ' ', str(row.get('Produttore/Fornitore', '') or '')).strip().upper() 
            for row in all_data
        ]
        return sorted(list(set([n for n in raw_names if n])))
    except Exception as e:
        print(f"Errore query Supabase: {e}")
        return []

@app.post("/api/suppliers")
async def add_supplier(supplier: NewSupplier):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase non configurato")
    
    name = supplier.name.strip().upper()
    if name:
        try:
            # Inserimento nella tabella db_mp_arrivi come richiesto
            supabase.table("db_mp_arrivi").insert({"Produttore/Fornitore": name}).execute()
        except Exception as e:
            print(f"Nota: Errore inserimento fornitore: {e}")
            
    return await get_suppliers()

class PrintPayload(BaseModel):
    zpl: str
    printer_ip: Optional[str] = "192.168.68.162"

@app.post("/api/print")
async def print_zebra(data: PrintPayload):
    """Proxy per inviare comandi ZPL alla stampante Zebra (risolve Mixed Content)"""
    printer_url = f"http://{data.printer_ip}/pstprnt"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                printer_url,
                content=data.zpl.encode("utf-8"),
                headers={"Content-Type": "text/plain"}
            )
            return {"ok": response.status_code == 200, "status": response.status_code}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Stampante {data.printer_ip} non raggiungibile")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class Collo(BaseModel):
    barcode: str
    peso: int
    mq: float
    nome_foto: str

class PayloadExport(BaseModel):
    fornitore: str
    spessore: float
    larghezza: int
    colore: str
    descrizione: str
    data_arrivo: str
    terminato: Optional[str] = ""
    linea: Optional[str] = ""
    colli: List[Collo]

@app.post("/api/export")
async def export_excel(data: PayloadExport):
    """Genera il file Excel finale con i parametri condivisi e i dettagli colli"""
    rows = []
    for c in data.colli:
        rows.append({
            'Codice a barre': c.barcode,
            'Produttore/Fornitore': data.fornitore,
            'Spessore dichiarato': data.spessore,
            'Arrivo': data.data_arrivo,
            'Descrizione': data.descrizione,
            'Codice Colore': data.colore,
            'Peso': c.peso,
            'Metri Quadri': c.mq,
            'Terminato': data.terminato,
            'Linea': data.linea,
            'Larghezza': data.larghezza,
            'Foto Originale': c.nome_foto
        })
    
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Arrivi')
    
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=arrivi_{datetime.now().strftime('%Y%m%d')}.xlsx"}
    )

# Servizio file statici (index.html, immagini, ecc.)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/{file_path:path}")
async def serve_static(file_path: str):
    full_path = os.path.join(BASE_DIR, file_path)
    if os.path.isfile(full_path):
        return FileResponse(full_path)
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)