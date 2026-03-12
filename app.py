import streamlit as st
import pandas as pd
import numpy as np
import re
import os
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image
from streamlit_qrcode_scanner import qrcode_scanner

# 1. Configurazione della pagina
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="ptsimbolo.png")

# 2. CSS AVANZATO (Stile professionale e tasti blu)
st.markdown("""
    <style>
    /* Sfondo e font generale */
    .stApp { background-color: #f8f9fa; }
    
    /* Titoli e Label in grassetto nero */
    label, p, h3, .stMarkdown { 
        color: #1a1a1a !important; 
        font-weight: bold !important; 
    }
    
    /* Stile personalizzato per i pulsanti */
    div.stButton > button, div.stFormSubmitButton > button {
        background-color: #004a99 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 10px !important;
        border: none !important;
        height: 3em !important;
        width: 100% !important;
        transition: all 0.3s ease;
    }
    
    div.stButton > button:hover {
        background-color: #003366 !important;
        transform: scale(1.02);
    }

    /* Stile per i campi di input */
    .stTextInput > div > div > input, .stNumberInput > div > div > input {
        border-radius: 8px !important;
        border: 1px solid #004a99 !important;
    }

    /* Tab header */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 10px 10px 0px 0px;
        gap: 1px;
        padding-top: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #004a99 !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNZIONI DI SUPPORTO ---
def analizza_con_google(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        return response.text_annotations[0].description if response.text_annotations else ""
    except:
        return ""

def estrai_dati_completi(testo):
    testo_u = testo.upper()
    dati = {"barcode": "", "fornitore": "", "spessore": 0.0, "peso": 0, "mq": 0.0, "colore": "", "descrizione": "", "linea": "1"}
    
    # Regex per Barcode (formato S+numeri o lunghe stringhe numeriche)
    match_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo_u)
    if match_bar: dati["barcode"] = match_bar.group(1)
    
    # Mappatura fornitori
    mappa = {"LAMPRE": "Lampre", "MARCEGAGLIA": "Marcegaglia", "VARCOLOR": "Varcolor", "METALCOAT": "Metalcoat"}
    for k, v in mappa.items():
        if k in testo_u: dati["fornitore"] = v
        
    # Estrazione spessore (es: 0.50 o 0,60)
    match_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))
    
    return dati

# --- INIZIALIZZAZIONE STATI ---
if 'archivio' not in st.session_state: st.session_state.archivio = []
if 'temp_scan' not in st.session_state: st.session_state.temp_scan = {}
if 'show_quick_scan' not in st.session_state: st.session_state.show_quick_scan = False

# --- UI PRINCIPALE ---
col_logo, col_title = st.columns([1, 4])
with col_logo:
    try: st.image("ptsimbolo.png", width=80)
    except: pass
with col_title:
    st.title("Pietro Roseto - Arrivi Merce")

tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 STORICO CARICHI"])

with tab1:
    # 1. SCANNER GOOGLE VISION (Per compilazione automatica totale)
    with st.expander("📷 ANALISI ETICHETTA COMPLETA (FOTO)"):
        foto = st.camera_input("Scatta foto per estrarre tutti i dati")
        if foto:
            with st.spinner("Analisi in corso con Google Vision..."):
                testo = analizza_con_google(foto.getvalue())
                st.session_state.temp_scan = estrai_dati_completi(testo)
                st.success("Dati estratti con successo!")

    # 2. SCANNER RAPIDO (Solo per il Barcode)
    if st.session_state.show_quick_scan:
        st.info("Inquadra il QR Code o il Barcode con la fotocamera")
        barcode_letto = qrcode_scanner(key='scanner_veloce')
        
        if barcode_letto:
            st.session_state.temp_scan["barcode"] = barcode_letto
            st.session_state.show_quick_scan = False
            st.rerun()
            
        if st.button("❌ ANNULLA SCAN"):
            st.session_state.show_quick_scan = False
            st.rerun()

    # 3. FORM DI CARICO
    with st.form("form_carico_unico", clear_on_submit=True):
        st.markdown("### 📋 Inserimento Dati")
        
        # Campo Barcode con pulsante Scan a fianco
        col_bar_1, col_bar_2 = st.columns([3, 1])
        f_barcode = col_bar_1.text_input("📦 CODICE A BARRE", value=st.session_state.temp_scan.get("barcode", ""))
        with col_bar_2:
            st.write("##") # Spazio per allineare al campo
            if st.form_submit_button("📷 SCAN"):
                st.session_state.show_quick_scan = True
                st.rerun()

        # Altri Campi
        c1, c2 = st.columns(2)
        f_fornitore = c1.text_input("🏭 FORNITORE", value=st.session_state.temp_scan.get("fornitore", ""))
        f_spessore = c2.number_input("📏 SPESSORE", value=float(st.session_state.temp_scan.get("spessore", 0.0)), format="%.2f", step=0.01)

        f_descrizione = st.text_input("📝 DESCRIZIONE", value=st.session_state.temp_scan.get("descrizione", ""))
        f_arrivo = st.date_input("📅 DATA ARRIVO", datetime.now())

        c3, c4 = st.columns(2)
        f_colore = c3.text_input("🎨 CODICE COLORE", value=st.session_state.temp_scan.get("colore", ""))
        f_peso = c4.number_input("⚖️ PESO (KG)", value=int(st.session_state.temp_scan.get("peso", 0)), step=1)

        c5, c6 = st.columns(2)
        f_mq = c5.number_input("📐 METRI QUADRI", value=float(st.session_state.temp_scan.get("mq", 0.0)), step=0.01)
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"], index=0 if st.session_state.temp_scan.get("linea")=="1" else 1)

        f_terminato = st.selectbox("🏁 TERMINATO", ["", "SI", "NO"], index=0)

        # Pulsante Registrazione
        if st.form_submit_button("🚀 REGISTRA CARICO IN ARCHIVIO"):
            if not f_barcode:
                st.error("Il codice a barre è obbligatorio!")
            else:
                st.session_state.archivio.append({
                    "Codice a barre": f_barcode, "Produttore/Fornitore": f_fornitore,
                    "Spessore dichiarato": f_spessore, "Arrivo": f_arrivo.strftime("%d/%m/%Y"),
                    "Descrizione": f_descrizione, "Codice Colore": f_colore,
                    "Peso": f_peso, "Metri Quadri": f_mq, "Terminato": f_terminato, "Linea": f_linea
                })
                st.session_state.temp_scan = {} # Reset
                st.success("✅ Carico registrato correttamente!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.markdown("### 📋 Lista Carichi Registrati")
        st.dataframe(df, use_container_width=True)
        
        # Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        col_down_1, col_down_2 = st.columns(2)
        col_down_1.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico_merci.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        if col_down_2.button("🗑️ CANCELLA TUTTO"):
            st.session_state.archivio = []
            st.rerun()
    else:
        st.info("📦 L'archivio è vuoto. Inserisci il primo carico nel Tab 1.")
