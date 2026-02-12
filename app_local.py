
import streamlit as st
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import requests
import json

# Carica variabili da .env
load_dotenv()

# Config da env o st.secrets
def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        return st.secrets.get(key, default)  # type: ignore[attr-defined]
    except Exception:
        return default

BASE_URL = os.getenv("LOCAL_AGENT_URL", _get_secret("LOCAL_AGENT_URL", "http://127.0.0.1:8000"))
APP_NAME = os.getenv("LOCAL_APP_NAME", _get_secret("LOCAL_APP_NAME", "greeting_agent"))

HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json"
}

# ---------- Utility ----------
def _format_timestamp(ts: Any) -> str:
    try:
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts).strftime('%d/%m %H:%M')
        elif isinstance(ts, str):
            s = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.strftime('%d/%m %H:%M')
    except Exception:
        pass
    return "Unknown"

def _parse_json_or_empty(response: requests.Response, on_empty=None):
    """
    Ritorna JSON se possibile.
    - Se 204/empty body -> on_empty (default: []), senza errori.
    - Se non è JSON -> mostra diagnostica e ritorna on_empty.
    """
    if on_empty is None:
        on_empty = []
    try:
        # 204 No Content o corpo vuoto
        if response.status_code == 204 or not response.content or response.text.strip() == "":
            return on_empty
        # Prova JSON
        return response.json()
    except ValueError:
        # Non-JSON: mostra diagnostica utile
        ct = response.headers.get("content-type", "unknown")
        body_snippet = response.text[:500] if response.text else "<no body>"
        st.error(
            f"⚠️ Risposta non-JSON dall'API.\n\n"
            f"- Status: {response.status_code}\n"
            f"- Content-Type: {ct}\n"
            f"- Body (snippet):\n```\n{body_snippet}\n```"
        )
        return on_empty

# ****************************************
# Application Operations
# ****************************************
def list_apps():
    """GET /list-apps"""
    endpoint = f"{BASE_URL}/list-apps"
    try:
        resp = requests.get(endpoint, headers=HEADERS)
        resp.raise_for_status()
        return _parse_json_or_empty(resp, on_empty=[])
    except requests.exceptions.RequestException as e:
        st.error(f"Error listing apps: {e}")
        return None

# ****************************************
# Session Operations
# ****************************************
def list_sessions(app_name: str, user_id: str) -> List[Dict[str, Any]]:
    """GET /apps/{app_name}/users/{user_id}/sessions"""
    endpoint = f"{BASE_URL}/apps/{app_name}/users/{user_id}/sessions"
    try:
        resp = requests.get(endpoint, headers=HEADERS)
        resp.raise_for_status()
        data = _parse_json_or_empty(resp, on_empty=[])
        # Alcune API restituiscono {"sessions": [...]}
        if isinstance(data, dict) and "sessions" in data:
            return data["sessions"] or []
        return data if isinstance(data, list) else []
    except requests.exceptions.RequestException as e:
        st.error(f"Error listing sessions for user {user_id} in app {app_name}: {e}")
        return []

def get_session(app_name: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """GET /apps/{app_name}/users/{user_id}/sessions/{session_id}"""
    endpoint = f"{BASE_URL}/apps/{app_name}/users/{user_id}/sessions/{session_id}"
    try:
        resp = requests.get(endpoint, headers=HEADERS)
        resp.raise_for_status()
        data = _parse_json_or_empty(resp, on_empty=None)
        return data if isinstance(data, dict) else None
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting session {session_id}: {e}")
        return None

def delete_session(app_name: str, user_id: str, session_id: str) -> bool:
    """DELETE /apps/{app_name}/users/{user_id}/sessions/{session_id}"""
    endpoint = f"{BASE_URL}/apps/{app_name}/users/{user_id}/sessions/{session_id}"
    try:
        resp = requests.delete(endpoint, headers=HEADERS)
        # Alcune API rispondono 204 (No Content)
        if resp.status_code in [200, 202, 204]:
            return True
        # Prova a leggere eventuale JSON di errore per diagnosi
        _ = _parse_json_or_empty(resp, on_empty=None)
        return resp.ok
    except requests.exceptions.RequestException as e:
        st.error(f"Error deleting session {session_id}: {e}")
        return False

def create_session(app_name: str, user_id: str, session_data: Optional[dict] = None) -> Optional[str]:
    """POST /apps/{app_name}/users/{user_id}/sessions"""
    endpoint = f"{BASE_URL}/apps/{app_name}/users/{user_id}/sessions"
    try:
        payload = session_data if session_data is not None else {}
        resp = requests.post(endpoint, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = _parse_json_or_empty(resp, on_empty=None)
        if isinstance(data, dict):
            return data.get("id")
        # Alcune API tornano {"session": {"id": "..."}} o una lista
        if isinstance(data, dict) and "session" in data and isinstance(data["session"], dict):
            return data["session"].get("id")
        if isinstance(data, list) and data:
            maybe = data[0]
            if isinstance(maybe, dict) and "id" in maybe:
                return maybe["id"]
        st.warning("La risposta alla creazione sessione non contiene un campo 'id'.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error creating session for user {user_id} in app {app_name}: {e}")
        return None

# ****************************************
# Agent Operations
# ****************************************
def agent_run_sse(app_name: str, user_id: str, session_id: str, query: str):
    """POST /run_sse (Server-Sent Events)"""
    endpoint = f"{BASE_URL}/run_sse"
    request_data = {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [{"text": query}]
        },
        "stream": True
    }
    try:
        with requests.post(endpoint, headers=HEADERS, json=request_data, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        try:
                            yield json.loads(decoded_line[len("data: "):])
                        except json.JSONDecodeError:
                            st.warning(f"Could not decode JSON from stream: {decoded_line}")
                    # Altri tipi di righe (commenti/keepalive) sono ignorati
    except requests.exceptions.RequestException as e:
        st.error(f"Error during agent run SSE: {e}")
        return

def display_conversation_history(session_details: Dict[str, Any]):
    events = session_details.get('events', [])
    if not events:
        st.info("No conversation history yet. Start by sending a message!")
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
                        text_content += part['text']
                if text_content.strip():
                    if role == 'user' or author == 'user':
                        with st.chat_message("user"):
                            st.write(text_content)
                    else:
                        with st.chat_message("assistant"):
                            st.write(text_content)

def main():
    st.set_page_config(
        page_title="Local Agent Chat",
        page_icon="🤖",
        layout="wide"
    )
    st.title("🤖 Assistente SAP DM")
    st.markdown("Chat with your local agent running at `{}`".format(BASE_URL))

    # Stato sessione
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "sessions" not in st.session_state:
        st.session_state.sessions = []
    if "refresh_sessions" not in st.session_state:
        st.session_state.refresh_sessions = True
    if "user_name" not in st.session_state:
        st.session_state.user_name = "test_user"

    # Sidebar
    with st.sidebar:
        user_id = st.text_input("User Name", value=st.session_state.user_name)
        st.session_state.user_name = user_id
        st.header("Session Management")

        # Diagnostica rapida API
        with st.expander("🔎 Diagnostica API"):
            st.caption("Esegui un test veloce sull'endpoint /list-apps per vedere risposta raw.")
            if st.button("Test /list-apps"):
                try:
                    ep = f"{BASE_URL}/list-apps"
                    r = requests.get(ep, headers=HEADERS)
                    st.write("Status:", r.status_code)
                    st.write("Content-Type:", r.headers.get("content-type"))
                    st.code(r.text[:1000] if r.text else "<no body>", language="text")
                except Exception as e:
                    st.error(f"Errore test /list-apps: {e}")

        if st.button("🔄 Refresh Sessions"):
            st.session_state.refresh_sessions = True

        if st.session_state.refresh_sessions:
            st.session_state.sessions = list_sessions(APP_NAME, user_id)
            st.session_state.refresh_sessions = False

        if st.button("➕ Create New Session"):
            new_session_id = create_session(APP_NAME, user_id)
            if new_session_id:
                st.success(f"Created new session: {new_session_id}")
                st.session_state.session_id = new_session_id
                st.session_state.refresh_sessions = True
                st.rerun()

        if st.session_state.sessions:
            st.subheader("Available Sessions")
            for i, session in enumerate(st.session_state.sessions):
                session_id = session.get('id', f'session_{i}')
                last_update = session.get('lastUpdateTime', 0)
                last_update_str = _format_timestamp(last_update)

                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button(f"📝 {session_id[:8]}... ({last_update_str})", key=f"select_{session_id}"):
                        st.session_state.session_id = session_id
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"delete_{session_id}", help="Delete session"):
                        if delete_session(APP_NAME, user_id, session_id):
                            st.success("Session deleted!")
                            if st.session_state.session_id == session_id:
                                st.session_state.session_id = None
                            st.session_state.refresh_sessions = True
                            st.rerun()
        else:
            st.info("No sessions found. Create a new session to start chatting!")

    # Main chat
    if st.session_state.session_id:
        st.subheader(f"Chat Session: {st.session_state.session_id}")
        session_details = get_session(APP_NAME, user_id, st.session_state.session_id)
        if session_details:
            display_conversation_history(session_details)

            st.markdown("---")
            user_message = st.chat_input("Type your message here...")
            if user_message:
                with st.chat_message("user"):
                    st.write(user_message)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        responses = []
                        for event in agent_run_sse(APP_NAME, user_id, st.session_state.session_id, user_message):
                            if event and 'content' in event and 'parts' in event['content']:
                                for part in event['content']['parts']:
                                    if 'text' in part:
                                        responses.append(part['text'])
                        if responses:
                            for response in responses:
                                st.write(response)
                        else:
                            st.error("No response received from the agent.")
                st.rerun()
        else:
            st.error("Could not load session details. Please try refreshing or creating a new session.")
    else:
        st.info("👈 Please select or create a session from the sidebar to start chatting.")

    st.markdown(
        f"""
        ---
        ### Configuration
        - **User ID**: `{st.session_state.user_name}`
        - **Local Agent URL**: `{BASE_URL}`
        - **App Name**: `{APP_NAME}`
        """
    )

if __name__ == "__main__":
    main()
