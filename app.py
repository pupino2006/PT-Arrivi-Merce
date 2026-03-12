import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="PT Carico", layout="centered")

# --- CSS CUSTOM: GIOVANE, SMARTPHONE, TESTO NERO ---
st.markdown("""
    <style>
    /* Sfondo e Font */
    .stApp { background-color: #f4f7f9; font-family: -apple-system, sans-serif; }
    
    /* Header con Logo */
    .header-container {
        background: white;
        padding: 15px;
        text-align: center;
        border-bottom: 2px solid #1a73e8;
        margin-bottom: 15px;
        border-radius: 0 0 20px 20px;
    }
    
    /* Testo Nero e Labels */
    h1, h2, h3, p, label, .stMarkdown { color: #000000 !important; font-weight: 600 !important; }
    
    /* Card Inserimento */
    .stForm {
        background: white !important;
        border: none !important;
        border-radius: 20px !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.08) !important;
        padding: 20px !important;
    }

    /* Input Fields */
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        color: #000000 !important;
        border: 1.5px solid #dfe1e5 !important;
        border-radius: 12px !important;
        background: #ffffff !important;
        height: 45px !important;
    }

    /* Bottoni */
    .stButton>button {
        width: 100%;
        border-radius: 12px !important;
        background-color: #1a73e8 !important;
        color: white !important;
        font-weight: 700 !important;
        padding: 12px !important;
        border: none !important;
        text-transform: uppercase;
    }
    
    /* Scanner Expander */
    .stExpander { border: none !important; background: #e8f0fe !important; border-radius: 15px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGO ---
col_l, col_r = st.columns([1, 1])
try:
    logo = Image.open("ptsimbolo.png")
    st.image(logo, width=80)
except:
    st.markdown("### PT CARICO")

# --- LOGICA OCR ---
def analizza_foto(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        return response.text_annotations[0].description if response.text_annotations else ""
    except: return ""

def estrai_codice(testo):
    match = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo)
    return match.group(1) if match else ""

# --- UI APP ---
if 'dati_sessione' not in st.session_state:
    st.session_state.dati_sessione = []

tab_new, tab_list = st.tabs(["🆕 NUOVO", "📂 STORICO"])

with tab_new:
    # Selezione Metodo di Input
    with st.expander("📷 APRI FOTOCAMERA PER SCANNER"):
        foto = st.camera_input("Inquadra l'etichetta")
    
    carica_file = st.file_uploader("🖼️ CARICA DA GALLERIA", type=['jpg','png','jpeg'])

    testo_rilevato = ""
    file_input = foto if foto else carica_file
    
    if file_input:
        testo_rilevato = analizza_foto(file_input.getvalue())
        st.toast("Etichetta letta!", icon="🔎")

    # --- FORM ---
    with st.form("carico_form", clear_on_submit=True):
        st.markdown("### 📝 Dati Materiale")
        
        # 1. Codice a barre
        f_barcode = st.text_input("📦 CODICE A BARRE", value=estrai_codice(testo_rilevato))
        
        # 2. Fornitore e 3. Spessore
        c1, c2 = st.columns(2)
        f_fornitore = c1.text_input("🏭 FORNITORE", value="Lampre" if "LAMPRE" in testo_rilevato.upper() else "")
        f_spessore = c2.number_input("📏 SPESSORE", format="%.2f", step=0.01)
        
        # 4. Arrivo e 5. Descrizione
        f_arrivo = st.date_input("📅 DATA ARRIVO", datetime.now())
        f_descrizione = st.text_input("📄 DESCRIZIONE")
        
        # 6. Colore e 7. Peso
        c3, c4 = st.columns(2)
        f_colore = c3.text_input("🎨 CODICE COLORE")
        f_peso = c4.number_input("⚖️ PESO (KG)", step=1)
        
        # 8. Mq e 9. Linea
        c5, c6 = st.columns(2)
        f_mq = c5.number_input("📐 METRI QUADRI", step=0.01)
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"])
        
        # 10. Terminato (Stato lasciato vuoto di default)
        f_terminato = st.selectbox("🏁 STATO (TERMINATO)", ["", "SI", "NO"], index=0)

        if st.form_submit_button("REGISTRA NEL SISTEMA"):
            st.session_state.dati_sessione.append({
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
            st.success("Carico registrato!")

with tab_list:
    if st.session_state.dati_sessione:
        df = pd.DataFrame(st.session_state.dati_sessione)
        st.write("### Riepilogo")
        st.dataframe(df)
        
        # Download Excel
        buf = BytesIO()
        df.to_excel(buf, index=False)
        st.download_button("📥 SCARICA EXCEL", buf.getvalue(), "carico_pt.xlsx")
        
        if st.button("🗑️ CANCELLA TUTTO"):
            st.session_state.dati_sessione = []
            st.rerun()
    else:
        st.info("Nessun dato presente.")
