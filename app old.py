import streamlit as st
import vertexai
from vertexai.preview import reasoning_engines

# CONFIGURAZIONE 
PROJECT_ID = "data-platform-framework"
LOCATION = "europe-west4" # o la tua region
AGENT_ID = "projects/1014880272171/locations/europe-west4/reasoningEngines/4411574902172155904"

# Inizializzazione Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

st.set_page_config(page_title="Agente AI per SAP DM", page_icon="🤖")
st.title("Sapassistant")

# Inizializzazione dell'agente (caricato una sola volta)
@st.cache_resource
def get_agent():
    return reasoning_engines.ReasoningEngine(AGENT_ID)

agent = get_agent()

# Gestione della cronologia chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Visualizzazione dei messaggi precedenti
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input dell'utente
if prompt := st.chat_input("Ciao, benvenuto, come posso esserti utile?"):
    # Aggiungi messaggio utente alla UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generazione risposta dall'Agente
    with st.chat_message("assistant"):
        with st.spinner("L'agente sta pensando..."):
            try:
                # Chiamata all'Agente su Agent Engine
                response = agent.query(input=prompt)
                
                # Nota: ADK restituisce solitamente un dizionario o una stringa
                # Adattiamo l'estrazione in base al tuo output specifico
                answer = response.get("output") if isinstance(response, dict) else response
                
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"Errore: {str(e)}")