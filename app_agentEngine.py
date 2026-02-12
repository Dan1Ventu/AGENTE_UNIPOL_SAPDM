
import streamlit as st
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Vertex AI + auth
import vertexai
from google.oauth2 import service_account
from vertexai import agent_engines

# Carica variabili da .env (opzionale)
load_dotenv()

# >>>>>> CONFIG DEL TUO PROGETTO <<<<<<
PROJECT_ID = os.getenv("PROJECT_ID", "data-platform-framework")
LOCATION = os.getenv("LOCATION", "europe-west4")
RESOURCE_ID = os.getenv(
    "RESOURCE_ID",
    "projects/1014880272171/locations/europe-west4/reasoningEngines/4411574902172155904"
)


def initialize_vertex_ai() -> bool:
    """Inizializza Vertex AI usando credenziali da st.secrets (se presenti) oppure ADC."""
    try:
        credentials = None
        # Se hai inserito la chiave del service account in .streamlit/secrets.toml
        if "gcp_service_account" in st.secrets:
            credentials = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )

        if credentials:
            vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=credentials)
        else:
            # Fallback a ADC (GOOGLE_APPLICATION_CREDENTIALS o gcloud auth application-default login)
            vertexai.init(project=PROJECT_ID, location=LOCATION)

        return True
    except Exception as e:
        st.error(f"Errore nell'inizializzazione di Vertex AI: {e}")
        return False


# ---------- Utility ----------
def _format_timestamp(ts: Any) -> str:
    """Gestione robusta di epoch sec/ms o stringhe ISO8601."""
    try:
        if isinstance(ts, (int, float)):
            # euristica: se è in millisecondi
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts).strftime('%d/%m %H:%M')
        elif isinstance(ts, str):
            s = ts.replace("Z", "+00:00")
            # datetime.fromisoformat supporta il formato con offset
            dt = datetime.fromisoformat(s)
            return dt.strftime('%d/%m %H:%M')
    except Exception:
        pass
    return "Sconosciuto"


# ---------- Operazioni Agent Engine ----------
def create_new_session(resource_id: str, user_id: str) -> Optional[str]:
    """Crea una nuova sessione e ritorna l'ID della sessione."""
    try:
        remote_app = agent_engines.get(resource_id)
        remote_session = remote_app.create_session(user_id=user_id)
        if isinstance(remote_session, str):
            return remote_session
        elif isinstance(remote_session, dict):
            return remote_session.get('id')
        else:
            return None
    except Exception as e:
        st.error(f"Errore nella creazione della sessione: {e}")
        return None


def get_sessions_list(resource_id: str, user_id: str) -> List[Dict[str, Any]]:
    """Lista le sessioni dell'utente."""
    try:
        remote_app = agent_engines.get(resource_id)
        sessions = remote_app.list_sessions(user_id=user_id)
        if isinstance(sessions, dict) and 'sessions' in sessions:
            return sessions['sessions']
        elif isinstance(sessions, list):
            return sessions
        else:
            return []
    except Exception as e:
        st.error(f"Errore nel recupero delle sessioni: {e}")
        return []


def get_session_details(resource_id: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Dettagli della sessione inclusa la history conversazionale."""
    try:
        remote_app = agent_engines.get(resource_id)
        session = remote_app.get_session(user_id=user_id, session_id=session_id)
        if isinstance(session, dict):
            return session
        else:
            return None
    except Exception as e:
        st.error(f"Errore nel recupero dei dettagli della sessione: {e}")
        return None


def delete_session_by_id(resource_id: str, user_id: str, session_id: str) -> bool:
    """Elimina una sessione per ID."""
    try:
        remote_app = agent_engines.get(resource_id)
        remote_app.delete_session(user_id=user_id, session_id=session_id)
        return True
    except Exception as e:
        st.error(f"Errore nell'eliminazione della sessione: {e}")
        return False


def send_message_to_agent(resource_id: str, user_id: str, session_id: str, message: str) -> List[str]:
    """Invia un messaggio all'agente e restituisce le risposte (streaming)."""
    try:
        remote_app = agent_engines.get(resource_id)
        responses: List[str] = []

        for event in remote_app.stream_query(
            user_id=user_id,
            session_id=session_id,
            message=message,
        ):
            # Estrai testo dall'evento
            if isinstance(event, dict):
                content = event.get('content', {})
                if isinstance(content, dict):
                    parts = content.get('parts', [])
                    for part in parts:
                        if isinstance(part, dict) and 'text' in part:
                            text = part['text']
                            if text and str(text).strip():
                                responses.append(str(text))
        return responses
    except Exception as e:
        st.error(f"Errore durante l'invio del messaggio: {e}")
        return []


def display_conversation_history(session_details: Dict[str, Any]):
    """Mostra la history della conversazione dagli eventi di sessione."""
    events = session_details.get('events', [])
    if not events:
        st.info("Nessuna conversazione al momento. Invia un messaggio per iniziare!")
        return

    for event in events:
        if isinstance(event, dict):
            content = event.get('content', {})
            author = event.get('author', 'unknown')
            if isinstance(content, dict):
                parts = content.get('parts', [])
                role = content.get('role', author)

                text_content = ""
                for part in parts:
                    if isinstance(part, dict) and 'text' in part and part['text'] is not None:
                        text_content += str(part['text'])

                if text_content.strip():
                    if role == 'user' or author == 'user':
                        with st.chat_message("user"):
                            st.write(text_content)
                    else:
                        with st.chat_message("assistant"):
                            st.write(text_content)


def main():
    st.set_page_config(
        page_title="Chat Agente Vertex AI",
        page_icon="🤖",
        layout="wide"
    )
    st.title("🤖 Chat Agente Vertex AI (Agent Engine)")
    st.markdown("Interagisci con il tuo agente Vertex AI già deployato.")

    # Inizializzazione Vertex AI con il tuo progetto/region
    if not initialize_vertex_ai():
        st.stop()

    # Stato della sessione
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "sessions" not in st.session_state:
        st.session_state.sessions = []
    if "refresh_sessions" not in st.session_state:
        st.session_state.refresh_sessions = True
    if "user_name" not in st.session_state:
        st.session_state.user_name = "test_user"

    # Sidebar: gestione sessioni
    with st.sidebar:
        user_id = st.text_input("Utente", value=st.session_state.user_name)
        st.session_state.user_name = user_id
        st.header("Gestione sessioni")

        if st.button("🔄 Aggiorna sessioni"):
            st.session_state.refresh_sessions = True

        if st.session_state.refresh_sessions:
            st.session_state.sessions = get_sessions_list(RESOURCE_ID, user_id)
            st.session_state.refresh_sessions = False

        if st.button("➕ Crea nuova sessione"):
            new_session_id = create_new_session(RESOURCE_ID, user_id)
            if new_session_id:
                st.success(f"Nuova sessione creata: {new_session_id}")
                st.session_state.session_id = new_session_id
                st.session_state.refresh_sessions = True
                st.rerun()

        if st.session_state.sessions:
            st.subheader("Sessioni disponibili")
            for i, session in enumerate(st.session_state.sessions):
                session_id = session.get('id', f'session_{i}')
                last_update = session.get('lastUpdateTime', 0)
                last_update_str = _format_timestamp(last_update)

                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button(f"📝 {session_id[:8]}... ({last_update_str})",
                                 key=f"select_{session_id}"):
                        st.session_state.session_id = session_id
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"delete_{session_id}", help="Elimina sessione"):
                        if delete_session_by_id(RESOURCE_ID, user_id, session_id):
                            st.success("Sessione eliminata!")
                            if st.session_state.session_id == session_id:
                                st.session_state.session_id = None
                            st.session_state.refresh_sessions = True
                            st.rerun()
        else:
            st.info("Nessuna sessione trovata. Crea una nuova sessione per iniziare!")

    # Area chat principale
    if st.session_state.session_id:
        st.subheader(f"Sessione: {st.session_state.session_id}")

        session_details = get_session_details(RESOURCE_ID, user_id, st.session_state.session_id)
        if session_details:
            display_conversation_history(session_details)

            st.markdown("---")
            user_message = st.chat_input("Scrivi qui il tuo messaggio...")
            if user_message:
                # Mostra subito il messaggio utente
                with st.chat_message("user"):
                    st.write(user_message)

                # Risposta agente (streaming aggregato)
                with st.chat_message("assistant"):
                    with st.spinner("Sto pensando..."):
                        responses = send_message_to_agent(
                            RESOURCE_ID, user_id, st.session_state.session_id, user_message
                        )
                        if responses:
                            for response in responses:
                                st.write(response)
                        else:
                            st.error("Nessuna risposta ricevuta dall'agente.")
                # Aggiorna la history
                st.rerun()
        else:
            st.error("Impossibile caricare i dettagli della sessione. Riprova ad aggiornare o crea una nuova sessione.")
    else:
        st.info("👈 Seleziona o crea una sessione dalla sidebar per iniziare a chattare.")

    # Info utili
    st.markdown(
        f"""
        ---
        ### Configurazione
        - **User ID**: `{user_id}`
        - **Project ID**: `{PROJECT_ID}`
        - **Location**: `{LOCATION}`
        - **Resource ID**: `{RESOURCE_ID}`

        Assicurati che l'Agent Engine sia deployato e che il Resource ID sia corretto.
        """
    )


if __name__ == "__main__":
    main()
