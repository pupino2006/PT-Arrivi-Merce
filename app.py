import streamlit as st
import pandas as pd
import re
from datetime import datetime
from io import BytesIO
from google.cloud import vision

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="PT - Carico Merci", layout="centered")

# --- CSS PERSONALIZZATO (STYLE PT) ---
st.markdown("""
    <style>
    /* Reset e Base */
    .stApp { background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    
    /* Container Bianco Centrale */
    [data-testid="stVerticalBlock"] > div:has(.main-card) {
        background: white;
        padding: 0;
        border-radius: 0;
        box-shadow: 0 0 20px rgba(0,0,0,0.1);
    }

    /* Header e Logo */
    .header-pt {
        background: white;
        padding: 20px;
        text-align: center;
        border-bottom: 3px solid #004a99;
        margin-bottom: 0px;
    }
    .header-pt h1 { color: #004a99; font-weight: 800; margin: 0; font-size: 24px; text-transform: uppercase; }

    /* Tabs Stile PT */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #004a99;
        padding: 5px 10px;
    }
    .stTabs [data-baseweb="tab"] {
        color: white !important;
        opacity: 0.7;
        font-weight: bold;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        opacity: 1 !important;
        border-bottom: 4px solid white !important;
    }

    /* Form e Input */
    label { color: #004a99 !important; font-weight: bold !important; text-transform: uppercase; font-size: 13px !self; }
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        border-radius: 8px !important;
        border: 1px solid #ccc !important;
    }

    /* Bottoni */
    .stButton>button {
        width: 100%;
        border-radius: 8px !important;
        background-color: #004a99 !important;
        color: white !important;
        font-weight: bold !important;
        padding: 15px !important;
        transition: 0.3s;
    }
    .stButton>button:hover { background-color: #003366 !important; }
    
    /* Bottone Invia (Verde) */
    div.stButton > button:first-child:contains("SALVA") {
        background-color: #28a745 !important;
        border: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA ESTRAZIONE (GOOGLE VISION) ---
def analizza_etichetta(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        texts = response.text_annotations
        return texts[0].description if texts else ""
    except: return ""

def cerca_barcode(testo):
    # Regex per vari formati di barcode (es: S + cifre, o stringhe alfanumeriche lunghe)
    match = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo)
    return match.group(1) if match else ""

# --- INTERFACCIA ---

st.markdown('<div class="header-pt"><h1>PT - CARICO MERCI</h1></div>', unsafe_allow_html=True)

if 'archivio' not in st.session_state:
    st.session_state.archivio = []

tab1, tab2 = st.tabs(["📋 INSERIMENTO", "📦 ARCHIVIO"])

with tab1:
    with st.container():
        st.markdown('<div style="padding: 20px;">', unsafe_allow_html=True)
        
        # Caricamento
        foto = st.camera_input("📷 SCANSIONA ETICHETTA")
        
        testo_ocr = ""
        if foto:
            testo_ocr = analizza_etichetta(foto.getvalue())
            st.success("Etichetta letta correttamente!")

        # --- FORM DATI ---
        with st.form("form_carico"):
            st.markdown("### DATI MATERIALE")
            
            # Codice a barre con tasto dedicato
            col_code, col_btn = st.columns([3,1])
            barcode_rilevato = cerca_barcode(testo_ocr)
            f_barcode = col_code.text_input("CODICE A BARRE", value=barcode_rilevato)
            if col_btn.form_submit_button("🔍 SCAN"):
                # In Streamlit il pulsante all'interno del form resetta, 
                # ma qui lo usiamo come indicatore visivo o trigger logico
                pass

            col1, col2 = st.columns(2)
            f_fornitore = col1.text_input("PRODUTTORE / FORNITORE", value="Lampre" if "LAMPRE" in testo_ocr.upper() else "")
            f_spessore = col2.number_input("SPESSORE DICHIARATO", format="%.2f", step=0.01)
            
            col3, col4 = st.columns(2)
            f_arrivo = col3.date_input("DATA ARRIVO", datetime.now())
            f_colore = col4.text_input("CODICE COLORE")
            
            f_descrizione = st.text_area("DESCRIZIONE", placeholder="Es: Fe Plast 9010...")
            
            col5, col6, col7 = st.columns(3)
            f_peso = col5.number_input("PESO (KG)", step=1)
            f_mq = col6.number_input("METRI QUADRI", step=0.01)
            f_linea = col7.selectbox("LINEA", ["1", "2"])
            
            f_terminato = st.checkbox("TERMINATO", value=False)

            submit = st.form_submit_button("🚀 SALVA NELL'ELENCO")
            
            if submit:
                nuovo_dato = {
                    "Codice a barre": f_barcode,
                    "Produttore/Fornitore": f_fornitore,
                    "Spessore dichiarato": f_spessore,
                    "Arrivo": f_arrivo.strftime("%Y-%m-%d"),
                    "Descrizione": f_descrizione,
                    "Codice Colore": f_colore,
                    "Peso": f_peso,
                    "Metri Quadri": f_mq,
                    "Terminato": "SI" if f_terminato else "NO",
                    "Linea": f_linea
                }
                st.session_state.archivio.append(nuovo_dato)
                st.toast("Dato salvato con successo!")

        st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div style="padding: 20px;">', unsafe_allow_html=True)
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df, use_container_width=True)
        
        # Esporta in Excel
        towrite = BytesIO()
        df.to_excel(towrite, index=False, engine='xlsxwriter')
        st.download_button(
            label="📥 SCARICA EXCEL COMPLETO",
            data=towrite.getvalue(),
            file_name=f"carico_merci_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.ms-excel"
        )
        
        if st.button("🗑️ CANCELLA TUTTA LA SESSIONE"):
            st.session_state.archivio = []
            st.rerun()
    else:
        st.info("Nessun dato caricato in questa sessione.")
    st.markdown('</div>', unsafe_allow_html=True)
