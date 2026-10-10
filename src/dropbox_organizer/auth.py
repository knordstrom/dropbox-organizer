import json
import os
import dropbox
from dropbox.oauth import DropboxOAuth2FlowNoRedirect

_PKCE_STATE_PATH = os.path.expanduser("~/.dropbox_organizer_pkce_state")


class DropboxAuthManager:
    def __init__(self, app_key: str, token_path: str):
        self.app_key = app_key
        self.token_path = token_path

    def authenticate(self) -> dropbox.Dropbox:
        token = self._load_token()
        if token:
            dbx = dropbox.Dropbox(oauth2_refresh_token=token, app_key=self.app_key)
            try:
                dbx.users_get_current_account()
                return dbx
            except Exception:
                pass  # Token invalid, re-authenticate

        token = self._run_pkce_flow()
        self._save_token(token)
        return dropbox.Dropbox(oauth2_refresh_token=token, app_key=self.app_key)

    def start_pkce_flow(self) -> str:
        """Generate the authorization URL and persist PKCE state for finish_pkce_flow."""
        auth_flow = DropboxOAuth2FlowNoRedirect(
            self.app_key,
            use_pkce=True,
            token_access_type="offline",
        )
        auth_url = auth_flow.start()
        with open(_PKCE_STATE_PATH, "w") as f:
            json.dump({"code_verifier": auth_flow.code_verifier}, f)
        return auth_url

    def finish_pkce_flow(self, code: str) -> str:
        """Exchange *code* using the saved PKCE state. Returns the refresh token."""
        if not os.path.exists(_PKCE_STATE_PATH):
            raise RuntimeError("No pending auth flow. Run 'auth' first to generate a URL.")
        with open(_PKCE_STATE_PATH) as f:
            state = json.load(f)
        os.remove(_PKCE_STATE_PATH)

        auth_flow = DropboxOAuth2FlowNoRedirect(
            self.app_key,
            use_pkce=True,
            token_access_type="offline",
        )
        auth_flow.code_verifier = state["code_verifier"]
        result = auth_flow.finish(code)
        return result.refresh_token

    def _load_token(self) -> str | None:
        if os.path.exists(self.token_path):
            with open(self.token_path) as f:
                return f.read().strip() or None
        return None

    def _save_token(self, refresh_token: str):
        os.makedirs(os.path.dirname(self.token_path) or ".", exist_ok=True)
        with open(self.token_path, "w") as f:
            f.write(refresh_token)
        os.chmod(self.token_path, 0o600)

    def _run_pkce_flow(self) -> str:
        auth_flow = DropboxOAuth2FlowNoRedirect(
            self.app_key,
            use_pkce=True,
            token_access_type="offline",
        )
        auth_url = auth_flow.start()
        print("\nDropbox authorization required.")
        print(f"1. Visit this URL:\n\n   {auth_url}\n")
        print("2. Click 'Allow', then copy the authorization code.")
        code = input("3. Paste the code here: ").strip()
        result = auth_flow.finish(code)
        return result.refresh_token
