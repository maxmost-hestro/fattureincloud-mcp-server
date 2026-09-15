#!/usr/bin/env python3
"""
FattureInCloud OAuth2 Setup Script
Esegui una volta per ottenere i token di accesso.
"""

import http.server
import urllib.parse
import webbrowser
import requests
import threading
import time
import os
from pathlib import Path

# OAuth2 endpoints
AUTH_URL = "https://api-v2.fattureincloud.it/oauth/authorize"
TOKEN_URL = "https://api-v2.fattureincloud.it/oauth/token"
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

# Scopes necessari per analisi fatture e pagamenti
SCOPES = [
    "issued_documents:r",    # Lettura fatture emesse
    "received_documents:r",  # Lettura fatture ricevute (passive)
    "entities:r",            # Lettura clienti/fornitori
    "settings:r",            # Lettura impostazioni
    "situation:r",           # Situazione contabile
    "cashbook:r",            # Prima nota (get_cashbook_entries) - aggiunto 2026-09-16
    "taxes:r",               # F24 (get_f24_list) - aggiunto 2026-09-16
]


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler per catturare il callback OAuth2."""

    def do_GET(self):
        if self.path.startswith("/callback"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "code" in params:
                self.server.auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("""
                    <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Autorizzazione completata!</h1>
                    <p>Puoi chiudere questa finestra e tornare al terminale.</p>
                    </body></html>
                """.encode('utf-8'))
            else:
                error = params.get("error", ["Unknown error"])[0]
                error_desc = params.get("error_description", [""])[0]
                self.server.auth_code = None
                self.server.error = f"{error}: {error_desc}"
                self.send_response(400)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"""
                    <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Errore</h1>
                    <p>{error}: {error_desc}</p>
                    </body></html>
                """.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Silenzio i log


def start_server():
    """Avvia il server HTTP in background."""
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)
    server.auth_code = None
    server.error = None
    server.timeout = 120  # 2 minuti timeout
    return server


def get_auth_code_automatic(client_id: str) -> str | None:
    """Metodo automatico con server locale."""

    # Avvia server PRIMA di aprire il browser
    print("\n   Avvio server locale su porta 8080...")
    try:
        server = start_server()
    except OSError as e:
        print(f"   Errore: porta 8080 già in uso. {e}")
        return None

    # Costruisci URL di autorizzazione
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n   Apro il browser...")
    print(f"   URL: {auth_url}\n")

    # Apri browser dopo un attimo
    time.sleep(0.5)
    webbrowser.open(auth_url)

    print("   In attesa dell'autorizzazione (timeout: 2 minuti)...")

    # Aspetta la risposta
    server.handle_request()

    if server.auth_code:
        print("   Autorizzazione ricevuta!")
        return server.auth_code
    else:
        print(f"   Errore: {server.error}")
        return None


def get_auth_code_manual(client_id: str) -> str | None:
    """Metodo manuale: l'utente copia il code dalla URL."""

    # Costruisci URL - per manual flow usiamo urn:ietf:wg:oauth:2.0:oob come redirect
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",  # Out-of-band redirect
        "scope": " ".join(SCOPES),
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n   Apri questo URL nel browser:")
    print(f"   {auth_url}")
    print(f"\n   Dopo l'autorizzazione, FattureInCloud mostrerà un codice.")

    webbrowser.open(auth_url)

    code = input("\n   Incolla qui il codice di autorizzazione: ").strip()

    if code:
        return code
    return None


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str, manual_mode: bool = False) -> dict | None:
    """Scambia l'authorization code per access e refresh token."""

    print("\n3. Scambio code per tokens...")

    redirect_uri = "urn:ietf:wg:oauth:2.0:oob" if manual_mode else REDIRECT_URI

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    try:
        response = requests.post(TOKEN_URL, data=data)

        if response.status_code == 200:
            tokens = response.json()
            print("   Tokens ottenuti!")
            return tokens
        else:
            print(f"   Errore HTTP {response.status_code}")
            print(f"   Risposta: {response.text}")
            return None
    except Exception as e:
        print(f"   Errore: {e}")
        return None


def get_company_id(access_token: str) -> tuple[int, str] | None:
    """Ottieni l'ID e nome dell'azienda."""

    print("\n4. Recupero informazioni azienda...")

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(
            "https://api-v2.fattureincloud.it/user/companies",
            headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            companies = data.get("data", {}).get("companies", [])

            if not companies:
                print("   Nessuna azienda trovata!")
                return None

            if len(companies) == 1:
                company = companies[0]
                print(f"   Azienda trovata: {company['name']}")
                return company["id"], company["name"]

            # Più aziende: chiedi quale usare
            print("\n   Aziende disponibili:")
            for i, c in enumerate(companies, 1):
                print(f"   {i}. {c['name']} (ID: {c['id']})")

            while True:
                try:
                    choice = int(input("\n   Scegli il numero dell'azienda: ")) - 1
                    if 0 <= choice < len(companies):
                        company = companies[choice]
                        return company["id"], company["name"]
                except ValueError:
                    pass
                print("   Scelta non valida, riprova.")
        else:
            print(f"   Errore HTTP {response.status_code}")
            print(f"   Risposta: {response.text}")
            return None
    except Exception as e:
        print(f"   Errore: {e}")
        return None


def save_env(client_id: str, client_secret: str, tokens: dict, company_id: int, company_name: str):
    """Salva le credenziali nel file .env"""

    env_path = Path(__file__).parent / ".env"

    env_content = f"""# FattureInCloud MCP Server Configuration
# Generato automaticamente da auth_setup.py

# OAuth2 App Credentials
FIC_CLIENT_ID={client_id}
FIC_CLIENT_SECRET={client_secret}

# Access Tokens
FIC_ACCESS_TOKEN={tokens['access_token']}
FIC_REFRESH_TOKEN={tokens.get('refresh_token', '')}

# Company Info
FIC_COMPANY_ID={company_id}
FIC_COMPANY_NAME={company_name}
"""

    env_path.write_text(env_content)
    print(f"\n5. Credenziali salvate in: {env_path}")


def main(client_id: str = None, client_secret: str = None):
    print("=" * 60)
    print("  FattureInCloud OAuth2 Setup")
    print("=" * 60)

    if not client_id or not client_secret:
        print("""
Prima di procedere, assicurati di aver creato un'app su:
https://developers.fattureincloud.it

IMPORTANTE: La Redirect URI dell'app deve essere:
  http://localhost:8080/callback

Ti serviranno:
- Client ID
- Client Secret
""")

        client_id = input("Inserisci Client ID: ").strip()
        if not client_id:
            print("Client ID richiesto!")
            return

        client_secret = input("Inserisci Client Secret: ").strip()
        if not client_secret:
            print("Client Secret richiesto!")
            return
    else:
        print(f"\n   Client ID: {client_id[:8]}...")
        print(f"   Client Secret: {client_secret[:8]}...")

    # Scegli metodo
    print("\nMetodo di autorizzazione:")
    print("1. Automatico (server locale) - Consigliato")
    print("2. Manuale (copia codice)")

    method = input("\nScegli [1/2]: ").strip() or "1"

    manual_mode = method == "2"

    # Step 1: Get authorization code
    print("\n" + "-" * 40)
    print("1. AUTORIZZAZIONE")
    print("-" * 40)

    if manual_mode:
        code = get_auth_code_manual(client_id)
    else:
        code = get_auth_code_automatic(client_id)

    if not code:
        print("\nAutorizzazione fallita.")
        print("\nSuggerimenti:")
        print("- Verifica che la Redirect URI nell'app sia: http://localhost:8080/callback")
        print("- Prova il metodo manuale (opzione 2)")
        return

    # Step 2: Exchange for tokens
    print("\n" + "-" * 40)
    print("2. SCAMBIO TOKENS")
    print("-" * 40)

    tokens = exchange_code_for_tokens(client_id, client_secret, code, manual_mode)
    if not tokens:
        print("\nScambio tokens fallito. Riprova.")
        return

    # Step 3: Get company ID
    print("\n" + "-" * 40)
    print("3. SELEZIONE AZIENDA")
    print("-" * 40)

    company_info = get_company_id(tokens["access_token"])
    if not company_info:
        print("\nRecupero azienda fallito. Riprova.")
        return

    company_id, company_name = company_info

    # Step 4: Save to .env
    save_env(client_id, client_secret, tokens, company_id, company_name)

    print("\n" + "=" * 60)
    print("  SETUP COMPLETATO!")
    print("=" * 60)

    server_path = Path(__file__).parent / "server.py"

    print(f"""
Prossimi passi:

1. Aggiungi a ~/.claude/settings.json nella sezione "mcpServers":

   "fattureincloud": {{
       "command": "python3",
       "args": ["{server_path}"]
   }}

2. Riavvia Claude Code

3. Prova: "Mostrami il riepilogo pagamenti"
""")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        # Modalità non-interattiva: python auth_setup.py CLIENT_ID CLIENT_SECRET
        main(client_id=sys.argv[1], client_secret=sys.argv[2])
    else:
        main()
