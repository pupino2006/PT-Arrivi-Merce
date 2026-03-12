import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- 1. CONFIGURAZIONE PAGINA E STYLE (LR TRAINING STYLE) ---
st.set_page_config(page_title="SB Arrivi Pro", layout="wide", page_icon="🏗️")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800;900&display=swap');
    
    /* Global Styles */
    .stApp { background-color: #0f172a; color: #f8fafc; font-family: 'Inter', sans-serif; }
    
    /* Glass Card Style */
    .glass-card { 
        background: rgba(30, 41, 59, 0.7); 
        backdrop-filter: blur(12px); 
        border: 1px solid rgba(255,255,255,0.1); 
        padding: 25px; 
        border-radius: 24px;
        margin-bottom: 20px;
    }
    
    /* Headers */
    h1, h2, h3 { 
        font-weight: 900 !important; 
        text-transform: uppercase; 
        font-style: italic; 
        letter-spacing: -1px; 
    }
    .main-title { font-size: 40px; color: #f8fafc; margin-bottom: 0px; }
    .orange-text { color: #f97316; }
    
    /* Inputs & Buttons */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #475569 !important;
        border-radius: 12px !important;
    }
    
    .stButton>button {
        background: #f97316 !important;
        color: white !important;
        border-radius: 15px !important;
        font-weight: 800 !important;
        text-transform: uppercase !important;
        border: none !important;
        height: 3.5em !important;
        transition: all 0.3s;
    }
    .stButton>button:hover { transform: scale(1.02); box-shadow: 0 10px 15px -3px rgba(249, 115, 22, 0.4); }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; }
    .stTabs [data-baseweb="tab"] { color: #94a3b8; font-weight: 800; }
    .stTabs [aria-selected="true"] { color: #f97316 !important; border-bottom-color: #f97316 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. LOGICA ESTRAZIONE DATI ---

def analizza_con_google(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        # Chiediamo sia la lettura testo (OCR) che i codici a barre
        response = client.text_detection(image=image)
        raw_text = response.text_annotations[0].description if response.text_annotations else ""
        return raw_text
    except Exception:
        return ""

def estrai_barcode_dedicato(image_bytes):
    """Tenta di leggere specificamente QR o Barcode usando Google Vision"""
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        # Nota: In alcune regioni Vision API rileva i codici durante l'OCR
        # Se disponibile, usiamo la funzione di rilevamento simboli
        response = client.text_detection(image=image)
        testo = response.text_annotations[0].description if response.text_annotations else ""
        
        # Filtriamo i codici comuni (S + 10 cifre o lunghe stringhe alfanumeriche)
        match = re.search(r'\b(S\d{9,12}|[A-Z0-9]{15,35})\b', testo)
        return match.group(1) if match else None
    except:
        return None

def estrai_dati_chirurgica(testo_intero):
    testo_intero = testo_intero.upper().replace('\n', ' ')
    dati = {
        "Codice a barre": "", "Produttore/Fornitore": "Sconosciuto",
        "Spessore dichiarato": 0.0, "Arrivo": datetime.now().strftime("%Y-%m-%d"),
        "Descrizione": "", "Codice Colore": "", "Peso": 0, "Linea": "1"
    }

    # Fornitori
    forn_map = {"LAMPRE": "Lampre", "MARCEGAGLIA": "marcegaglia", "VARCOLOR": "varcolor", 
                "ARCELOR": "arcelormittal", "FIBROSAN": "Fibrosan", "VETRORESINA": "Vetroresina Spa"}
    for k, v in forn_map.items():
        if k in testo_intero: dati["Produttore/Fornitore"] = v

    # Peso (Fix errore)
    match_peso = re.search(r'(\d{3,5})\s*(?:KG|NET|NETTO)', testo_intero)
    if match_peso:
        try: dati["Peso"] = int(re.sub(r'[.,]', '', match_peso.group(1)))
        except: pass

    # Spessore
    match_sp = re.search(r'\b([0-1][.,]\d{2})\b', testo_intero)
    if match_sp: 
        try: dati["Spessore dichiarato"] = float(match_sp.group(1).replace(',', '.'))
        except: pass

    return dati

# --- 3. INTERFACCIA ---

st.markdown('<h1 class="main-title">SB <span class="orange-text">ARRIVI</span> PRO</h1>', unsafe_allow_html=True)
st.markdown('<p style="color: #64748b; font-weight: 600;">LOGISTICA E CARICO MATERIALI</p>', unsafe_allow_html=True)

if 'session_data' not in st.session_state:
    st.session_state.session_data = []

tab1, tab2 = st.tabs(["📸 SCANSIONE", "📊 ARCHIVIO SESSIONE"])

with tab1:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        img_file = st.file_uploader("Carica Foto Etichetta", type=['jpg','png','jpeg'])
        camera_file = st.camera_input("Usa Fotocamera")
        st.markdown('</div>', unsafe_allow_html=True)

    input_file = camera_file if camera_file else img_file

    if input_file:
        raw_text = analizza_con_google(input_file.getvalue())
        info = estrai_dati_chirurgica(raw_text)
        
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("Dati Rilevati")
        
        with st.form("entry_form"):
            # RIGA 1: Codice con tasto SCAN
            col_b1, col_b2 = st.columns([3, 1])
            f_barcode = col_b1.text_input("📦 CODICE A BARRE", info["Codice a barre"])
            if col_b2.form_submit_button("🔍 SCAN QR"):
                # Forza ricarica cercando solo il codice
                barcode_found = estrai_barcode_dedicato(input_file.getvalue())
                if barcode_found: 
                    f_barcode = barcode_found
                    st.success(f"Codice trovato: {barcode_found}")

            # RIGA 2
            r2c1, r2c2, r2c3 = st.columns(3)
            f_forn = r2c1.text_input("🏭 FORNITORE", info["Produttore/Fornitore"])
            f_spess = r2c2.number_input("📏 SPESSORE", value=info["Spessore dichiarato"])
            f_peso = r2c3.number_input("⚖️ PESO (KG)", value=info["Peso"])
            
            # RIGA 3
            r3c1, r3c2, r3c3 = st.columns(3)
            f_color = r3c1.text_input("🎨 COLORE", info["Codice Colore"])
            f_linea = r3c2.selectbox("🏗️ LINEA", ["1", "2"], index=1 if "VETRORESINA" in f_forn.upper() or "FIBROSAN" in f_forn.upper() else 0)
            f_data = r3c3.text_input("📅 DATA", info["Arrivo"])

            if st.form_submit_button("💾 SALVA NEL CARICO"):
                st.session_state.session_data.append({
                    "Codice a barre": f_barcode, "Produttore/Fornitore": f_forn,
                    "Spessore dichiarato": f_spess, "Arrivo": f_data,
                    "Peso": f_peso, "Linea": f_linea, "Codice Colore": f_color
                })
                st.balloons()
        st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    if st.session_state.session_data:
        df = pd.DataFrame(st.session_state.session_data)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True)
        
        # Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "Carico_Merci.xlsx", "application/vnd.ms-excel")
        if st.button("🗑️ SVUOTA"):
            st.session_state.session_data = []
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
