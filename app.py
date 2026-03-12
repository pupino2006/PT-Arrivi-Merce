import streamlit as st
import pandas as pd
import re
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="PT Carico", layout="centered")

# --- CSS CUSTOM: LOOK SMARTPHONE, TESTO NERO, TASTI TESTO BIANCO ---
st.markdown("""
    <style>
    /* Sfondo e Font */
    .stApp { background-color: #f4f7f9; font-family: -apple-system, sans-serif; }
    
    /* Header */
    .header-container { text-align: center; padding: 10px; }
    
    /* Testo Nero per Label e Markdown */
    label, .stMarkdown p, h1, h2, h3 { color: #000000 !important; font-weight: 700 !important; }
    
    /* Input Fields Neri */
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        color: #000000 !important;
        border: 1.5px solid #1a73e8 !important;
        border-radius: 12px !important;
    }

    /* BOTTONI: SFONDO BLU, TESTO BIANCO CORRETTO */
    .stButton>button {
        width: 100%;
        border-radius: 12px !important;
        background-color: #1a73e8 !important;
        color: #FFFFFF !important; /* Testo Bianco */
        font-weight: 700 !important;
        padding: 12px !important;
        border: none !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Hover bottoni */
    .stButton>button:hover { color: #FFFFFF !important; background-color: #1557b0 !important; }

    /* Fix per tasti piccoli affiancati */
    div[data-testid="column"] .stButton>button {
        padding: 8px !important;
        font-size: 14px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- LOGO ---
try:
    st.image("ptsimbolo.png", width=70)
except:
    st.markdown("### PT CARICO")

# --- FUNZIONI DI ANALISI ---
def analizza_foto(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        testo = response.text_annotations[0].description if response.text_annotations else ""
        return testo
    except: return ""

def estrai_dati(testo):
    """Estrae i dati dal testo OCR per popolare il form"""
    dati = {
        "barcode": "",
        "fornitore": ""
    }
    if testo:
        # Cerca barcode (S seguito da numeri o stringhe lunghe)
        match = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo)
        if match: dati["barcode"] = match.group(1)
        
        # Cerca fornitore
        testo_up = testo.upper()
        if "LAMPRE" in testo_up: dati["fornitore"] = "Lampre"
        elif "MARCEGAGLIA" in testo_up: dati["fornitore"] = "Marcegaglia"
        elif "VARCOLOR" in testo_up: dati["fornitore"] = "Varcolor"
    return dati

# --- LOGICA SESSIONE ---
if 'dati_caricati' not in st.session_state:
    st.session_state.dati_caricati = {"barcode": "", "fornitore": ""}
if 'archivio' not in st.session_state:
    st.session_state.archivio = []

# --- UI ---
tab_new, tab_list = st.tabs(["➕ NUOVO", "📂 STORICO"])

with tab_new:
    # 1. Caricamento/Scanner
    with st.expander("📷 SCANSIONA ETICHETTA INTERA"):
        foto_full = st.camera_input("Inquadra per auto-compilare i campi")
        if foto_full:
            testo = analizza_foto(foto_full.getvalue())
            st.session_state.dati_caricati = estrai_dati(testo)
            st.success("Dati estratti con successo!")

    # --- FORM ---
    with st.form("carico_form", clear_on_submit=True):
        st.markdown("### 📝 Scheda Tecnica")
        
        # Codice a barre con pulsante scanner affiancato
        col_bar, col_btn = st.columns([3, 1])
        f_barcode = col_bar.text_input("📦 CODICE A BARRE", value=st.session_state.dati_caricati["barcode"])
        with col_btn:
            st.write("##") # Allineamento
            scansiona_singolo = st.form_submit_button("📷 SCAN")
            # In Streamlit lo scanner singolo dentro il form funge da trigger per il refresh o l'uso della camera sopra

        c1, c2 = st.columns(2)
        f_fornitore = c1.text_input("🏭 FORNITORE", value=st.session_state.dati_caricati["fornitore"])
        f_spessore = c2.number_input("📏 SPESSORE", format="%.2f", step=0.01)
        
        f_descrizione = st.text_input("📄 DESCRIZIONE")
        f_arrivo = st.date_input("📅 DATA ARRIVO", datetime.now())
        
        c3, c4 = st.columns(2)
        f_colore = c3.text_input("🎨 CODICE COLORE")
        f_peso = c4.number_input("⚖️ PESO (KG)", step=1)
        
        c5, c6 = st.columns(2)
        f_mq = c5.number_input("📐 METRI QUADRI", step=0.01)
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"])
        
        # Stato sempre vuoto all'inizio
        f_terminato = st.selectbox("🏁 STATO (TERMINATO)", ["", "SI", "NO"], index=0)

        submit = st.form_submit_button("REGISTRA CARICO")
        
        if submit:
            st.session_state.archivio.append({
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
            })
            # Reset dei dati caricati dopo il salvataggio
            st.session_state.dati_caricati = {"barcode": "", "fornitore": ""}
            st.success("Dato salvato!")

with tab_list:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df)
        
        buf = BytesIO()
        df.to_excel(buf, index=False)
        st.download_button("📥 SCARICA EXCEL (TESTO BIANCO)", buf.getvalue(), "carico.xlsx")
    else:
        st.info("Nessun dato in memoria.")
