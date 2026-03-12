import streamlit as st
import pandas as pd
import re
from datetime import datetime
from io import BytesIO
from google.cloud import vision

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="PT Carico Merci", layout="centered")

# --- CSS STILE APP MODERNA (GIOVANE E PULITO) ---
st.markdown("""
    <style>
    /* Reset generale */
    .stApp { background-color: #f8f9fa; font-family: 'Inter', -apple-system, sans-serif; }
    
    /* Header stile App */
    .app-header {
        background: white;
        padding: 1.5rem;
        text-align: center;
        border-bottom: 1px solid #eee;
        margin-bottom: 2rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .app-header h1 { color: #1a73e8; font-weight: 800; font-size: 22px; margin: 0; }

    /* Card per i form */
    .stForm {
        background: white !important;
        border: none !important;
        padding: 20px !important;
        border-radius: 16px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05) !important;
    }

    /* Input personalizzati */
    label { font-size: 12px !important; color: #5f6368 !important; text-transform: uppercase; letter-spacing: 0.5px; }
    .stTextInput input, .stNumberInput input {
        border-radius: 10px !important;
        border: 1px solid #dadce0 !important;
        padding: 12px !important;
        background: #fdfdfd !important;
    }

    /* Bottoni stile App */
    .stButton>button {
        width: 100%;
        border-radius: 12px !important;
        background-color: #1a73e8 !important;
        color: white !important;
        font-weight: 700 !important;
        padding: 0.8rem !important;
        border: none !important;
        transition: all 0.2s;
    }
    .stButton>button:hover { transform: translateY(-1px); box-shadow: 0 4px 8px rgba(26,115,232,0.3); }
    
    /* Bottone Scanner (Giallo/Arancio) */
    div[data-testid="stExpander"] { border: none !important; background: transparent !important; }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: white;
        border-radius: 10px 10px 0 0;
        padding: 10px 20px;
        color: #5f6368;
    }
    .stTabs [aria-selected="true"] { color: #1a73e8 !important; border-bottom: 3px solid #1a73e8 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA ESTRAZIONE ---
def analizza_etichetta(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        return response.text_annotations[0].description if response.text_annotations else ""
    except: return ""

def cerca_barcode(testo):
    match = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo)
    return match.group(1) if match else ""

# --- UI APP ---
st.markdown('<div class="app-header"><h1>🚀 PT CARICO MERCI</h1></div>', unsafe_allow_html=True)

if 'archivio' not in st.session_state:
    st.session_state.archivio = []

tab1, tab2 = st.tabs(["➕ NUOVO CARICO", "📂 STORICO SESSIONE"])

with tab1:
    # --- SEZIONE ACQUISIZIONE ---
    col_cam, col_file = st.columns(2)
    
    with col_cam:
        with st.expander("📷 SCATTA FOTO"):
            foto = st.camera_input("Inquadra l'etichetta")
    
    with col_file:
        file_caricato = st.file_uploader("📁 CARICA FOTO/PDF", type=['jpg','png','jpeg','pdf'])

    testo_ocr = ""
    input_effettivo = foto if foto else file_caricato
    
    if input_effettivo:
        testo_ocr = analizza_etichetta(input_effettivo.getvalue())
        st.toast("Dati estratti!", icon="✅")

    # --- FORM DI INSERIMENTO ---
    with st.form("form_carico", clear_on_submit=True):
        st.markdown("### 📝 Scheda Tecnica")
        
        # Codice e Fornitore
        col1, col2 = st.columns([3, 2])
        f_barcode = col1.text_input("📦 CODICE A BARRE", value=cerca_barcode(testo_ocr))
        f_fornitore = col2.text_input("🏭 FORNITORE", value="Lampre" if "LAMPRE" in testo_ocr.upper() else "")

        # Descrizione e Colore
        f_descrizione = st.text_input("📄 DESCRIZIONE", placeholder="Es. Fe Plast 9010...")
        f_colore = st.text_input("🎨 CODICE COLORE")

        # Dati Tecnici
        c3, c4, c5 = st.columns(3)
        f_spessore = c3.number_input("📏 SPESSORE", format="%.2f", step=0.01)
        f_peso = c4.number_input("⚖️ PESO (KG)", step=1)
        f_mq = c5.number_input("📐 MQ", step=0.01)

        # Logistica
        c6, c7, c8 = st.columns(3)
        f_arrivo = c6.date_input("📅 DATA ARRIVO", datetime.now())
        f_linea = c7.selectbox("🏗️ LINEA", ["1", "2"])
        f_terminato = c8.selectbox("🏁 STATO", ["IN CORSO", "TERMINATO"])

        submit = st.form_submit_button("REGISTRA CARICO")
        
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
                "Terminato": f_terminato,
                "Linea": f_linea
            }
            st.session_state.archivio.append(nuovo_dato)
            st.success("Dato aggiunto alla sessione!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.markdown("### Materiale in questa sessione")
        st.dataframe(df, use_container_width=True)
        
        # Download
        towrite = BytesIO()
        df.to_excel(towrite, index=False, engine='xlsxwriter')
        st.download_button(
            label="📥 ESPORTA EXCEL",
            data=towrite.getvalue(),
            file_name=f"carico_{datetime.now().strftime('%d%m_%H%M')}.xlsx",
            mime="application/vnd.ms-excel"
        )
        
        if st.button("🗑️ RESET"):
            st.session_state.archivio = []
            st.rerun()
    else:
        st.info("Inizia a scansionare per vedere i dati qui.")
