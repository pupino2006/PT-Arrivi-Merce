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
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="🏗️")

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
    testo_intero = testo_intero.upper().replace('§', 'S').replace('|', 'I')
    
    # Inizializzazione con i nomi colonne esatti del tuo Excel
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

    # Identificazione Fornitore (basata sui tuoi esempi)
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

    # Estrazione Codice a Barre (gestisce Lampre 'S' e codici lunghi Fibrosan)
    if "LAMPRE" in testo_intero:
        match = re.search(r'S\s*(\d{9,10})', testo_intero)
        if match: dati["Codice a barre"] = "S" + match.group(1)
    else:
        # Cerca sequenze alfanumeriche lunghe (fino a 32 per Fibrosan)
        match = re.search(r'\b([A-Z0-9/-]{8,32})\b', testo_intero)
        if match: dati["Codice a barre"] = match.group(1)

    # Spessore (Gestisce 0.45 dei metalli e 1.8 della VTR)
    match_sp = re.search(r'([0-2][.,]\d{1,2})', testo_intero)
    if match_sp: dati["Spessore dichiarato"] = float(match_sp.group(1).replace(',', '.'))

    # Peso
    match_peso = re.search(r'(\d{3,5})\s*(?:KG|NET|NETTO)', testo_intero)
    if match_peso: dati["Peso"] = int(match_peso.group(1))

    # Colore (Cerca RAL)
    match_ral = re.search(r'(RAL\s*\d{4})', testo_intero)
    if match_ral: dati["Codice Colore"] = match_ral.group(1)

    return dati

# --- 4. AVVIO APPLICAZIONE ---
if check_password():
    
    if "google_credentials" in st.secrets:
        creds = dict(st.secrets["google_credentials"])
        if not os.path.exists("temp_key.json"):
            with open("temp_key.json", "w") as f: json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    st.title("🏗️ SB Supporti - Arrivi")

    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

    input_mode = st.radio("Sorgente immagine:", ["📷 Scatta Foto", "📁 Galleria"], horizontal=True)
    foto_bytes = None

    if input_mode == "📷 Scatta Foto":
        camera_img = st.camera_input("Inquadra l'etichetta")
        if camera_img: foto_bytes = camera_img.getvalue()
    else:
        uploaded_file = st.file_uploader("Carica immagine", type=['jpg', 'jpeg', 'png'])
        if uploaded_file: foto_bytes = uploaded_file.getvalue()

    if foto_bytes:
        with st.spinner('Analisi AI in corso...'):
            testo_raw = analizza_con_google(foto_bytes)
            if testo_raw:
                info = estrai_dati_chirurgica(testo_raw)
                
                with st.form("validazione"):
                    st.subheader("📝 Verifica Dati")
                    col1, col2 = st.columns(2)
                    f_bar = col1.text_input("Codice a barre", info["Codice a barre"])
                    f_forn = col2.text_input("Produttore/Fornitore", info["Produttore/Fornitore"])
                    
                    c1, c2, c3 = st.columns(3)
                    f_spess = c1.number_input("Spessore dichiarato", value=info["Spessore dichiarato"], format="%.2f")
                    f_peso = c2.number_input("Peso", value=info["Peso"])
                    f_mq = c3.number_input("Metri Quadri", value=0.0, format="%.2f")
                    
                    f_data = st.text_input("Arrivo (Data)", info["Arrivo"])
                    f_desc = st.text_input("Descrizione", info["Descrizione"])
                    f_color = st.text_input("Codice Colore", info["Codice Colore"])
                    f_linea = st.selectbox("Linea", ["1", "2"], index=0 if "VETRORESINA" not in info["Produttore/Fornitore"].upper() else 1)

                    if st.form_submit_button("✅ AGGIUNGI RIGA AL CARICO"):
                        st.session_state.session_data.append({
                            "Codice a barre": f_bar,
                            "Produttore/Fornitore": f_forn,
                            "Spessore dichiarato": f_spess,
                            "Arrivo": f_data,
                            "Descrizione": f_desc,
                            "Codice Colore": f_color,
                            "Peso": f_peso,
                            "Metri Quadri": f_mq,
                            "Terminato": "", # Sempre vuoto come richiesto
                            "Linea": f_linea
                        })
                        st.success("Riga aggiunta!")
                        st.balloons()

    if st.session_state.session_data:
        st.divider()
        df = pd.DataFrame(st.session_state.session_data)
        
        # Ordiniamo le colonne esattamente come il tuo Excel
        ordine_colonne = [
            "Codice a barre", "Produttore/Fornitore", "Spessore dichiarato", 
            "Arrivo", "Descrizione", "Codice Colore", "Peso", 
            "Metri Quadri", "Terminato", "Linea"
        ]
        df = df[ordine_colonne]
        
        st.subheader("📋 Riepilogo Carico")
        st.dataframe(df, use_container_width=True)

        # Export Excel
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

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()
