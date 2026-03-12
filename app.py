import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="SB Arrivi Intelligenti",
    layout="wide", # Layout largo per gestire meglio le colonne
    page_icon="🏗️"
)

# CSS Personalizzato per Grafica User-Friendly
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; border: none; }
    .stDownloadButton>button { background-color: #28a745 !important; color: white !important; }
    .data-card { background-color: white; padding: 20px; border-radius: 15px; border: 1px solid #e0e0e0; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }
    .stTextInput>div>div>input { border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

PASSWORD_FILE = ".password_hash"

# --- 2. LOGICA DI SICUREZZA ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Configurazione Iniziale")
        new_pass = st.text_input("Crea Password Master", type="password")
        conf_pass = st.text_input("Conferma Password", type="password")
        if st.button("Salva e Configura"):
            if new_pass == conf_pass and len(new_pass) > 3:
                with open(PASSWORD_FILE, "w") as f: f.write(new_pass)
                st.success("Password impostata!")
                st.rerun()
        return False

    st.title("🔒 Accesso Riservato")
    input_pass = st.text_input("Inserisci Password:", type="password")
    if st.button("Sblocca Sistema"):
        with open(PASSWORD_FILE, "r") as f: saved_pass = f.read().strip()
        if input_pass == saved_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False

# --- 3. FUNZIONI CORE ---
def analizza_con_google(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        if response.text_annotations:
            return response.text_annotations[0].description
        return ""
    except Exception as e:
        st.error(f"Errore Google Vision: {e}")
        return ""

def estrai_dati_chirurgica(testo_intero):
    # Unifichiamo il testo per evitare problemi di riga
    testo_intero = testo_intero.upper().replace('§', 'S').replace('|', 'I').replace('\n', ' ')
    
    dati = {
        "Codice a barre": "Non trovato",
        "Produttore/Fornitore": "Sconosciuto",
        "Spessore dichiarato": 0.0,
        "Arrivo": datetime.now().strftime("%Y-%m-%d"),
        "Descrizione": "",
        "Codice Colore": "",
        "Peso": 0,
        "Metri Quadri": 0.0,
        "Terminato": "",
        "Linea": "1"
    }

    # 1. FORNITORE
    fornitori_map = {
        "LAMPRE": "Lampre", "MARCEGAGLIA": "marcegaglia", "VARCOLOR": "varcolor",
        "ARCELOR": "arcelormittal", "SANDRINI": "Sandrini Metalli", 
        "NOVELIS": "Novelis Ita", "METALCOAT": "metalcoat", 
        "VETRORESINA": "Vetroresina Spa", "FIBROSAN": "Fibrosan", "RIVIERASCA": "Rivierasca"
    }
    for chiave, nome in fornitori_map.items():
        if chiave in testo_intero:
            dati["Produttore/Fornitore"] = nome
            break

    # 2. CODICE A BARRE (Specifico Lampre e Fibrosan)
    if "LAMPRE" in testo_intero:
        match = re.search(r'S\s*(\d{9,11})', testo_intero)
        if match: dati["Codice a barre"] = "S" + match.group(1)
    else:
        match = re.search(r'\b([A-Z0-9/-]{8,32})\b', testo_intero)
        if match: dati["Codice a barre"] = match.group(1)

    # 3. SPESSORE (FIX ERRORE TIPO)
    match_sp = re.search(r'\b([0-1][.,]\d{2,3})\b|\b(1[.,]\d)\b', testo_intero)
    if match_sp:
        try:
            val = match_sp.group(0).replace(',', '.')
            dati["Spessore dichiarato"] = float(val)
        except: pass

    # 4. PESO (FIX TYPEERROR)
    match_peso = re.search(r'(\d{3,5})\s*(?:KG|NET|NETTO)', testo_intero)
    if match_peso:
        try:
            # Rimuove eventuali punti/virgole se l'OCR ha letto "2.225" invece di "2225"
            peso_clean = re.sub(r'[.,]', '', match_peso.group(1))
            dati["Peso"] = int(peso_clean)
        except: pass
    
    # 5. CODICE COLORE
    if "9010" in testo_intero: dati["Codice Colore"] = "RAL 9010"
    elif "9002" in testo_intero: dati["Codice Colore"] = "RAL 9002"
    match_ral = re.search(r'RAL\s*(\d{4})', testo_intero)
    if match_ral: dati["Codice Colore"] = "RAL " + match_ral.group(1)

    return dati

# --- 4. AVVIO APPLICAZIONE ---
if check_password():
    
    if "google_credentials" in st.secrets:
        creds = dict(st.secrets["google_credentials"])
        if not os.path.exists("temp_key.json"):
            with open("temp_key.json", "w") as f: json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    # Header Grafico
    col_l, col_r = st.columns([1, 4])
    with col_l:
        st.title("🏗️")
    with col_r:
        st.title("SB Arrivi - Gestione Carico")
        st.caption(f"Sessione attiva: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

    # Area di Input con Tab
    tab_foto, tab_archivio = st.tabs(["📸 Nuova Scansione", "📊 Archivio Sessione"])

    with tab_foto:
        c1, c2 = st.columns([1, 1])
        with c1:
            input_mode = st.radio("Metodo:", ["📷 Scatta", "📁 Galleria"], horizontal=True)
            if input_mode == "📷 Scatta":
                img = st.camera_input("Inquadra etichetta")
            else:
                img = st.file_uploader("Carica immagine", type=['jpg','png','jpeg'])
        
        if img:
            with st.spinner('✨ L\'intelligenza artificiale sta leggendo...'):
                raw_text = analizza_con_google(img.getvalue())
                info = estrai_dati_chirurgica(raw_text)
            
            with st.container():
                st.markdown('<div class="data-card">', unsafe_allow_html=True)
                st.subheader("📝 Verifica e Conferma Dati")
                
                with st.form("form_dati"):
                    r1_c1, r1_c2, r1_c3 = st.columns(3)
                    f_bar = r1_c1.text_input("📦 Codice a barre", info["Codice a barre"])
                    f_forn = r1_c2.text_input("🏭 Fornitore", info["Produttore/Fornitore"])
                    f_data = r1_c3.text_input("📅 Data Arrivo", info["Arrivo"])

                    r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
                    f_spess = r2_c1.number_input("📏 Spessore", value=info["Spessore dichiarato"], format="%.2f")
                    f_peso = r2_c2.number_input("⚖️ Peso (Kg)", value=int(info["Peso"]))
                    f_mq = r2_c3.number_input("📐 Metri Quadri", value=0.0)
                    f_linea = r2_c4.selectbox("🏗️ Linea", ["1", "2"], index=0 if "VETRORESINA" not in f_forn.upper() else 1)

                    r3_c1, r3_c2 = st.columns(2)
                    f_color = r3_c1.text_input("🎨 Colore / RAL", info["Codice Colore"])
                    f_desc = r3_c2.text_input("📄 Descrizione Breve", info["Descrizione"])

                    submit = st.form_submit_button("✅ AGGIUNGI AL CARICO EXCEL")
                    
                    if submit:
                        st.session_state.session_data.append({
                            "Codice a barre": f_bar,
                            "Produttore/Fornitore": f_forn,
                            "Spessore dichiarato": f_spess,
                            "Arrivo": f_data,
                            "Descrizione": f_desc,
                            "Codice Colore": f_color,
                            "Peso": f_peso,
                            "Metri Quadri": f_mq,
                            "Terminato": "",
                            "Linea": f_linea
                        })
                        st.toast("Riga aggiunta!", icon="✅")
                st.markdown('</div>', unsafe_allow_html=True)

    with tab_archivio:
        if st.session_state.session_data:
            df = pd.DataFrame(st.session_state.session_data)
            # Reorder
            cols = ["Codice a barre", "Produttore/Fornitore", "Spessore dichiarato", "Arrivo", "Descrizione", "Codice Colore", "Peso", "Metri Quadri", "Terminato", "Linea"]
            st.dataframe(df[cols], use_container_width=True)
            
            c_down, c_empty, c_del = st.columns([2, 2, 1])
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df[cols].to_excel(writer, index=False, sheet_name='Arrivi')
            
            c_down.download_button(
                "📥 SCARICA FILE EXCEL FINALE",
                data=output.getvalue(),
                file_name=f"Carico_SB_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            if c_del.button("🗑️ Svuota Tutto"):
                st.session_state.session_data = []
                st.rerun()
        else:
            st.info("Nessun dato scansionato in questa sessione.")

    # Sidebar
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/4090/4090458.png", width=100)
        st.title("SB Supporti")
        st.markdown("---")
        if st.button("Logout 🔒"):
            st.session_state["password_correct"] = False
            st.rerun()
