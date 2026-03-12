import streamlit as st
import pandas as pd
import re
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="PT Carico Merci", layout="centered")

# --- CSS ORIGINALE (LOOK PULITO, TESTO NERO, TASTI BIANCHI) ---
st.markdown("""
    <style>
    /* Reset e Base */
    .stApp { background: white; font-family: -apple-system, sans-serif; }
    
    /* Header */
    .header-pt {
        padding: 20px;
        text-align: center;
        border-bottom: 3px solid #004a99;
    }

    /* Testi Neri */
    label, p, h3, .stMarkdown { color: #000000 !important; font-weight: bold !important; }
    
    /* Input */
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        border: 1px solid #004a99 !important;
        color: #000000 !important;
    }

    /* BOTTONI: SFONDO BLU, TESTO BIANCO */
    .stButton>button {
        width: 100%;
        background-color: #004a99 !important;
        color: #FFFFFF !important; /* Testo Bianco per contrasto */
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        height: 50px;
    }
    
    /* Tasto Scan Piccolo */
    div[data-testid="column"] .stButton>button {
        height: 45px !important;
        background-color: #1a73e8 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNZIONI LOGICHE ---
def analizza_etichetta(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        testo = response.text_annotations[0].description if response.text_annotations else ""
        
        # Estrazione automatica
        dati = {"barcode": "", "fornitore": ""}
        barcode_match = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo)
        if barcode_match: dati["barcode"] = barcode_match.group(1)
        
        testo_up = testo.upper()
        if "LAMPRE" in testo_up: dati["fornitore"] = "Lampre"
        elif "MARCEGAGLIA" in testo_up: dati["fornitore"] = "Marcegaglia"
        elif "VARCOLOR" in testo_up: dati["fornitore"] = "Varcolor"
        
        return dati
    except: return {"barcode": "", "fornitore": ""}

# --- GESTIONE STATO ---
if 'temp_data' not in st.session_state:
    st.session_state.temp_data = {"barcode": "", "fornitore": ""}
if 'archivio' not in st.session_state:
    st.session_state.archivio = []

# --- INTERFACCIA ---
st.markdown('<div class="header-pt">', unsafe_allow_html=True)
try:
    st.image("ptsimbolo.png", width=80)
except:
    st.title("PT CARICO MERCI")
st.markdown('</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 ARCHIVIO"])

with tab1:
    # 1. SCANNER (Ora integrato per funzionare subito)
    st.markdown("### 📷 SCANSIONA")
    foto = st.camera_input("Inquadra il QR o Barcode dell'etichetta")
    
    if foto:
        risultati = analizza_etichetta(foto.getvalue())
        st.session_state.temp_data = risultati
        st.success(f"Dati rilevati: {risultati['barcode']}")

    # 2. FORM DI INSERIMENTO
    with st.form("main_form", clear_on_submit=True):
        st.markdown("---")
        
        # Codice a barre con pulsante "trigger"
        col_a, col_b = st.columns([3, 1])
        f_barcode = col_a.text_input("📦 CODICE A BARRE", value=st.session_state.temp_data["barcode"])
        with col_b:
            st.write("##")
            st.form_submit_button("📷 SCAN")

        f_fornitore = st.text_input("🏭 PRODUTTORE/FORNITORE", value=st.session_state.temp_data["fornitore"])
        
        c1, c2 = st.columns(2)
        f_spessore = c1.number_input("📏 SPESSORE DICHIARATO", format="%.2f", step=0.01)
        f_arrivo = c2.date_input("📅 DATA ARRIVO", datetime.now())
        
        f_descrizione = st.text_input("📝 DESCRIZIONE")
        f_colore = st.text_input("🎨 CODICE COLORE")
        
        c3, c4 = st.columns(2)
        f_peso = c3.number_input("⚖️ PESO (KG)", step=1)
        f_mq = c4.number_input("📐 METRI QUADRI", step=0.01)
        
        c5, c6 = st.columns(2)
        f_linea = c5.selectbox("🏗️ LINEA", ["1", "2"])
        f_terminato = c6.selectbox("🏁 TERMINATO", ["", "SI", "NO"], index=0)

        # Bottone Salva
        salva = st.form_submit_button("🚀 REGISTRA CARICO")
        
        if salva:
            nuovo_record = {
                "Codice a barre": f_barcode,
                "Produttore/Fornitore": f_fornitore,
                "Spessore dichiarato": f_spessore,
                "Arrivo": f_arrivo.strftime("%Y-%m-%d"),
                "Descrizione": f_descrizione,
                "Codice Colore": f_colore,
                "Peso": f_peso,
                "Metri Quadri": f_mq,
                "Terminato": f_terminato,
                "Linea": f_linea
            }
            st.session_state.archivio.append(nuovo_record)
            st.session_state.temp_data = {"barcode": "", "fornitore": ""} # Pulisce per il prossimo
            st.success("Carico salvato con successo!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df, use_container_width=True)
        
        # Export Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico_merci.xlsx")
    else:
        st.info("Nessun dato registrato.")
