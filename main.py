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

def estrai_dati_chirurgica(testo_ocr: str):
    """La logica di estrazione che abbiamo affinato nel prototipo"""
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
    colli: List[Collo]

@app.post("/api/export")
async def export_excel(data: PayloadExport):
    """Genera il file Excel finale con i parametri condivisi e i dettagli colli"""
    rows = []
    for c in data.colli:
        rows.append({
            'Data Arrivo': data.data_arrivo,
            'Fornitore': data.fornitore,
            'Descrizione': data.descrizione,
            'Spessore (mm)': data.spessore,
            'Larghezza (mm)': data.larghezza,
            'Colore': data.colore,
            'Codice Lotto / Barcode': c.barcode,
            'Peso (KG)': c.peso,
            'MQ': c.mq,
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