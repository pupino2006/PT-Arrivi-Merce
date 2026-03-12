import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- FILE PER LA PERSISTENZA PASSWORD ---
PASSWORD_FILE = ".password_hash"

# --- 1. CONFIGURAZIONE PAGINA E PWA ---
st.set_page_config(
    page_title="SB App Arrivi", 
    layout="centered", 
    page_icon="ptsimbolo.png"
)

def add_pwa_headers():
    pwa_html = """
        <link rel="manifest" href="manifest.json">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    """
    st.markdown(pwa_html, unsafe_allow_html=True)

add_pwa_headers()

# --- 2. LOGICA DI SICUREZZA ---
def check_password():
    """Gestisce la creazione e la verifica della password."""
    if st.session_state.get("password_correct", False):
        return True

    # Se la password non è mai stata configurata (prima volta assoluta)
    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Configurazione Iniziale")
        st.info("Benvenuto! Crea una password master per proteggere l'accesso all'app.")
        new_pass = st.text_input("Crea Password Master", type="password")
        conf_pass = st.text_input("Conferma Password Master", type="password")
        
        if st.button("Salva e Configura"):
            if new_pass == conf_pass and len(new_pass) > 3:
                with open(PASSWORD_FILE, "w") as f:
                    f.write(new_pass)
                st.success("Password impostata! Ora effettua l'accesso.")
                st.rerun()
            else:
                st.error("Le password non coincidono o sono troppo brevi (min 4 caratteri).")
        return False

    # Login standard
    st.title("🔒 Accesso Riservato")
    st.caption("Contenuto protetto. Inserisci la password per sbloccare le funzioni.")
    
    # Anteprima oscurata
    dummy_df = pd.DataFrame({"ID Collo": ["****", "****"], "Stato": ["PROTETTO", "PROTETTO"]})
    st.table(dummy_df)
    
    input_pass = st.text_input("Password:", type="password")
    if st.button("Sblocca Sistema"):
        with open(PASSWORD_FILE, "r") as f:
            saved_pass = f.read().strip()
        
        if input_pass == saved_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False

# --- 3. LOGICA APPLICATIVA (Solo se autenticati) ---
if check_password():
    
    # --- CONFIGURAZIONE GOOGLE VISION (Locale o Cloud) ---
    if os.path.exists("chiave_google.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "chiave_google.json"
    elif "google_credentials" in st.secrets:
        # Gestione segreti per il deploy su Streamlit Cloud
        creds_dict = dict(st.secrets["google_credentials"])
        with open("temp_key.json", "w") as f:
            json.dump(creds_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    def analizza_con_google(image_bytes):
        try:
            client = vision.ImageAnnotatorClient()
            image = vision.Image(content=image_bytes)
            response = client.text_detection(image=image)
            return response.text_annotations[0].description if response.text_annotations else ""
        except Exception as e:
            st.error(f"Errore Google Vision: {e}")
            return ""

def estrai_dati_chirurgica(annotation):
    testo_intero = annotation.text.upper()
    # Pulizia caratteri comuni errati dall'OCR
    testo_intero = testo_intero.replace('§', 'S').replace('|', 'I')
    
    dati = {
        "barcode": "Non trovato", "fornitore": "Sconosciuto", 
        "spessore": 0.0, "peso": 0, "larghezza": 0, "lunghezza": 0.0,
        "data_etichetta": datetime.now().strftime("%d/%m/%Y"),
        "codice_colore": "", "descrizione": ""
    }

    # 1. IDENTIFICAZIONE FORNITORE (LOGICA ESTESA)
    fornitori_map = {
        "MARCEGAGLIA": "MARCEGAGLIA",
        "LAMPRE": "LAMPRE",
        "ARCELOR": "ARCELORMITTAL",
        "NOVELIS": "NOVELIS",
        "VARCOLOR": "VARCOLOR",
        "METALCOAT": "METALCOAT",
        "SANDRINI": "SANDRINI METALLI",
        "VETRORESINA": "VETRORESINA SPA",
        "FIBROSAN": "FIBROSAN",
        "RIVIERASCA": "RIVIERASCA"
    }
    
    for chiave, nome in fornitori_map.items():
        if chiave in testo_intero:
            dati["fornitore"] = nome
            break

    # 2. ESTRAZIONE CODICE / BARCODE (CHIRURGICA PER TIPO)
    if dati["fornitore"] == "LAMPRE":
        match = re.search(r'S\s*(\d{9,10})', testo_intero)
        if match: dati["barcode"] = "S" + match.group(1)
    elif dati["fornitore"] == "SANDRINI METALLI":
        match = re.search(r'(T\d{5}[-\w]+)', testo_intero)
        if match: dati["barcode"] = match.group(1)
    elif dati["fornitore"] == "FIBROSAN":
        match = re.search(r'(\d{15,})', testo_intero) # Codici lunghi Fibrosan
        if match: dati["barcode"] = match.group(1)
    else:
        # Generico per Varcolor/Novelis/Metalcoat (cerca sequenze numeriche 9-12 cifre)
        match = re.search(r'\b(\d{9,12})\b', testo_intero)
        if match: dati["barcode"] = match.group(1)

    # 3. SPESSORE (VTR vs METALLO)
    # Se VTR o Fibrosan, lo spessore è alto (1.2 - 1.8)
    if any(x in dati["fornitore"] for x in ["VETRORESINA", "FIBROSAN", "RIVIERASCA"]):
        match_sp = re.search(r'(\d[.,]\d)', testo_intero)
        if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))
    else:
        # Per metalli (0.40 - 0.80)
        match_sp = re.search(r'(0[.,]\d{2,3})', testo_intero)
        if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))

    # 4. PESO E DIMENSIONI
    # Peso Netto (Cerca numeri 3-5 cifre vicino a KG o NET)
    match_peso = re.search(r'(\d{3,5})\s*(?:KG|NET|NETTO)', testo_intero)
    if match_peso: dati["peso"] = int(match_peso.group(1))
    
    # Larghezza (Standard 1000, 1200, 1250, 1500 o simili)
    match_largh = re.search(r'\b(1000|1200|1219|1225|1250|1500|600|360)\b', testo_intero)
    if match_largh: dati["larghezza"] = int(match_largh.group(1))

    # 5. COLORE (RAL O CODICI SPECIALI)
    match_ral = re.search(r'(RAL\s*\d{4})', testo_intero)
    if match_ral: dati["codice_colore"] = match_ral.group(1)
    elif "9010" in testo_intero: dati["codice_colore"] = "RAL 9010" # Molto comune nei tuoi dati

    return dati

    # --- UI ESTETICA ---
    st.markdown("""
        <style>
        .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #004a99; color: white; font-weight: bold; }
        .stDownloadButton>button { background-color: #28a745 !important; border-radius: 12px; }
        .stCameraInput>div>button { background-color: #004a99 !important; color: white !important; }
        </style>
        """, unsafe_allow_html=True)

    try:
        logo = Image.open("ptsimbolo.png")
        st.image(logo, width=100)
    except:
        st.title("🏗️ SB Supporti")
    
    st.subheader("Carico Arrivi Intelligente")

    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

  # Sezione Input
    st.divider()
    input_mode = st.radio("Metodo inserimento:", ["Scatta Foto", "Scegli dalla Galleria"], horizontal=True)

    foto_bytes = None
    if input_mode == "Scatta Foto":
        camera_img = st.camera_input("Inquadra l'etichetta")
        if camera_img: 
            foto_bytes = camera_img.getvalue()
    else:
        uploaded_file = st.file_uploader("Carica immagine", type=['jpg', 'jpeg', 'png'])
        if uploaded_file: 
            foto_bytes = uploaded_file.getvalue()

    # Processamento AI
    if foto_bytes:
        with st.spinner('L\'AI sta leggendo l\'etichetta...'):
            testo_ocr = analizza_con_google(foto_bytes)
            if testo_ocr:
                info = estrai_dati_chirurgica(testo_ocr)
                linea_calc = "1" if info["larghezza"] in [1200, 1225, 1250] else "2"
                
                with st.form("conferma_dati"):
                    st.subheader("📝 Verifica Dati")
                    f_bar = st.text_input("📦 Codice a barre / ID Collo", info["barcode"])
                    f_forn = st.text_input("🏭 Produttore/Fornitore", info["fornitore"])
                    f_data = st.text_input("📅 Data Arrivo", info["data_etichetta"])
                    f_color = st.text_input("🎨 Codice Colore", info["codice_colore"])

                    c1, c2, c3 = st.columns(3)
                    f_spess = c1.number_input("📏 Spessore", value=info["spessore"], format="%.2f")
                    f_peso = c2.number_input("⚖️ Peso (kg)", value=info["peso"])
                    f_lin = c3.number_input("↔️ M. Lineari", value=info["lunghezza"], format="%.1f")
                    
                    f_desc = st.text_input("📄 Descrizione", info["descrizione"])
                    f_linea = st.selectbox("🏗️ Linea", ["1", "2"], index=0 if linea_calc=="1" else 1)
                    
                    if st.form_submit_button("AGGIUNGI RIGA AL CARICO"):
                        m_quadri = f_lin * (float(info["larghezza"])/1000) if info["larghezza"] > 0 else 0.0
                        st.session_state.session_data.append({
                            "Codice a barre": f_bar, "Produttore/Fornitore": f_forn, "Spessore dichiarato": f_spess,
                            "Arrivo": f_data, "Descrizione": f_desc, "Codice Colore": f_color, "Peso": f_peso,
                            "Metri Quadri": round(m_quadri, 1), "Terminato": "", "Linea": f_linea, "Metri Lineari": f_lin
                        })
                        st.balloons()
                        st.success("Riga aggiunta!")

    # Tabella Riassuntiva
    if st.session_state.session_data:
        st.divider()
        df = pd.DataFrame(st.session_state.session_data)
        st.markdown("### 📋 Riepilogo Carico")
        st.dataframe(df, use_container_width=True)

        # Esportazione Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Carico SB')
        
        st.download_button(
            label="📥 SCARICA EXCEL FINALE",
            data=output.getvalue(),
            file_name=f"Carico_SB_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if st.button("🗑️ Svuota sessione"):
            st.session_state.session_data = []
            st.rerun()

    # Sidebar Logout
    if st.sidebar.button("Esci (Logout)"):
        st.session_state["password_correct"] = False
        st.rerun()

