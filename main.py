from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd
import re
import io
import json
import os
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
url: str = os.environ.get("SUPABASE_URL", "https://vnzrewcbnoqbqvzckome.supabase.co")
key: str = os.environ.get("SUPABASE_KEY", "sb_publishable_Sq9txbu-PmKdbxETSx2cjw_WqWEFBPO")
supabase: Client = create_client(url, key) if url and key else None

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
        
        raw_names = [str(row.get('Produttore/Fornitore', '')).strip().upper() for row in all_data]
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)