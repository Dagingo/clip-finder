import sys
import os
import json
import requests
from datetime import datetime, timedelta, timezone
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Canvas, Scrollbar
from PIL import Image, ImageTk
import io
import yt_dlp
from tkinter import font
from concurrent.futures import ThreadPoolExecutor

# --- Platform Specific Setup ---

# 1. DPI Awareness (Windows-specific)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        print("Attempted to set DPI awareness for Windows.")
    except Exception as e:
        print(f"Info: Could not set DPI awareness: {e}")

# 2. VLC Dependency Check
try:
    import vlc
except (ImportError, OSError) as e:
    vlc = None
    print(f"VLC library not found: {e}")
    def show_vlc_error():
        error_title = "VLC Installation Required"
        error_message = (
            "The VLC media player library is required for video previews but could not be found.\n\n"
            "Please install VLC and the Python-VLC library.\n\n"
            "On Debian/Ubuntu:\n"
            "sudo apt-get install vlc libvlc-dev\n"
            "pip install python-vlc\n\n"
            "On Fedora:\n"
            "sudo dnf install vlc vlc-devel\n"
            "pip install python-vlc\n\n"
            "On Arch Linux:\n"
            "sudo pacman -S vlc\n"
            "pip install python-vlc\n\n"
            "After installation, please restart the application."
        )
        # Using a simple Tk window to show the error as the main app might not be fully initialized.
        error_root = tk.Tk()
        error_root.withdraw() # Hide the main window
        messagebox.showerror(error_title, error_message)
        error_root.destroy()
        sys.exit(1) # Exit the application

    # We need to initialize Tk to show the messagebox, then exit.
    # This ensures the user sees the message even if the main app can't start.
    if __name__ == '__main__':
        show_vlc_error()
from tkinter import font # Import font module
from concurrent.futures import ThreadPoolExecutor


# Get the directory of the currently running script
script_dir = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(script_dir, 'twitch_presets.json')
RESULTS_FILE = os.path.join(script_dir, 'clip_results.txt')
PRESET_FILE = os.path.join(script_dir, 'twitch_presets.json') # Explicitly use absolute path
TOKEN_URL = 'https://id.twitch.tv/oauth2/token'
CLIPS_URL = 'https://api.twitch.tv/helix/clips'
CLIENT_ID = 'bigudl2pguod3yrnstzrcbsbvffqlu'
CLIENT_SECRET = 'crm33rwysrgvyctb0t31jhz6eyvi1h'

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Konfigurationsdatei: {e}")
            return {}
    else:
        messagebox.showerror("Fehler", f"{CONFIG_FILE} nicht gefunden. Bitte erstelle die Datei mit deinen API-Daten.")
        return {}

def get_access_token():
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    try:
        response = requests.post(TOKEN_URL, data=data)
        print("Response Status:", response.status_code)
        print("Response Text:", response.text)
        response.raise_for_status()
        token = response.json().get('access_token')
        if not token:
            raise ValueError("Kein Zugriffstoken im Antwort-JSON gefunden.")
        return token
    except requests.exceptions.RequestException as e:
        print(f"❌ Token-Fehler: {e}")
        print(f"Antwort-Inhalt: {response.text if 'response' in locals() else 'Keine Antwort'}")
        raise


def get_top_games(headers, limit=100):
    url = 'https://api.twitch.tv/helix/games/top'
    params = {'first': limit}
    response = requests.get(url, headers=headers, params=params)
    if response.ok:
        return response.json().get('data', [])
    return []


def get_game_id(game_name, headers):
    url = 'https://api.twitch.tv/helix/games'
    params = {'name': game_name}
    response = requests.get(url, headers=headers, params=params)
    if response.ok and response.json()['data']:
        return response.json()['data'][0]['id']
    return None


def get_user_id(username, headers):
    url = 'https://api.twitch.tv/helix/users'
    params = {'login': username}
    response = requests.get(url, headers=headers, params=params)
    if response.ok and response.json()['data']:
        return response.json()['data'][0]['id']
    return None

def fetch_clips_debug(preset, access_token):
    print("fetch_clips_debug gestartet")
    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {access_token}'
    }

    days = preset.get('time_range_days', 1)
    started_at = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    ended_at = datetime.now(timezone.utc).isoformat()

    base_params = {
        'first': 100,
        'started_at': started_at,
        'ended_at': ended_at
    }

    categories = preset.get('categories') or []
    channels = preset.get('channels') or []
    languages = preset.get('languages') or []

    print(f"[DEBUG] Token: {access_token[:5]}...")
    print(f"[DEBUG] Base Params: {base_params}")
    print(f"[DEBUG] Categories: {categories}")
    print(f"[DEBUG] Channels: {channels}")
    print(f"[DEBUG] Languages: {languages}")

    def _fetch_page(params):
        """Fetches a single page of clips and filters by language."""
        try:
            response = requests.get(CLIPS_URL, headers=headers, params=params, timeout=10)
            # print(f"[DEBUG] Request URL: {response.request.url}") # Optional: very verbose
            if response.ok:
                clips = response.json().get('data', [])
                if not languages:
                    return clips
                return [clip for clip in clips if clip.get('language') in languages]
            else:
                print(f"[DEBUG] API Error for {params}: {response.status_code} - {response.text}")
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching clips with params {params}: {e}")
        return []

    search_params_list = []
    if not categories and not channels:
        print("[DEBUG] Keine Kategorien oder Kanäle ausgewählt: Alle Top-Spiele durchsuchen.")
        top_games = get_top_games(headers)
        print(f"[DEBUG] Gefundene Top-Spiele: {[g['name'] for g in top_games]}")
        for game in top_games:
            params = base_params.copy()
            params['game_id'] = game['id']
            search_params_list.append(params)
    else:
        game_ids = {cat: get_game_id(cat, headers) for cat in categories}
        user_ids = {chan: get_user_id(chan, headers) for chan in channels}

        category_items = categories or [None]
        channel_items = channels or [None]

        for category_name in category_items:
            game_id = game_ids.get(category_name) if category_name else None
            if category_name and not game_id:
                print(f"Warnung: Spiel-ID für '{category_name}' nicht gefunden. Überspringe.")
                continue

            for channel_name in channel_items:
                broadcaster_id = user_ids.get(channel_name) if channel_name else None
                if channel_name and not broadcaster_id:
                    print(f"Warnung: Benutzer-ID für '{channel_name}' nicht gefunden. Überspringe.")
                    continue

                params = base_params.copy()
                if game_id:
                    params['game_id'] = game_id
                if broadcaster_id:
                    params['broadcaster_id'] = broadcaster_id

                if 'game_id' in params or 'broadcaster_id' in params:
                    search_params_list.append(params)

    if not search_params_list:
        print("[DEBUG] Keine gültigen Suchanfragen zu stellen.")
        return []

    all_clips = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_results = executor.map(_fetch_page, search_params_list)
        for clip_list in future_results:
            all_clips.extend(clip_list)

    unique_clips = {clip['id']: clip for clip in all_clips}.values()

    return sorted(list(unique_clips), key=lambda c: c['view_count'], reverse=True)

def get_direct_video_url(clip_url):
    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clip_url, download=False)
            return info.get('url')
    except Exception as e:
        print(f"[yt-dlp] Fehler: {e}")
        return None

def download_clip(clip_url, folder, log_func=None):
    if not os.path.exists(folder):
        os.makedirs(folder)
    ydl_opts = {
        'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            log_func(f"Lade herunter: {clip_url}" if log_func else f"Downloading: {clip_url}")
            ydl.download([clip_url])
            log_func(f"Download abgeschlossen: {clip_url}" if log_func else "Download complete")
    except Exception as e:
        log_func(f"Download-Fehler: {e}" if log_func else f"Download error: {e}")

class VLCPlayer:
    def __init__(self): # No longer needs parent for UI creation here
        if vlc is None:
            self.instance = None
            self.player = None
            return
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.videopanel = None # Will be created in setup_ui_in_frame
        self.control = None    # Will be created in setup_ui_in_frame

    def setup_ui_in_frame(self, parent_frame):
        if vlc is None: return
        # parent_frame is the dedicated container for VLC UI, child of PanedWindow

        # Video panel is a child of parent_frame
        self.videopanel = tk.Frame(parent_frame, bg='black', width=640, height=360)
        self.videopanel.grid(row=0, column=0, sticky='nsew')

        # Control panel is also a child of parent_frame
        self.control = ttk.Frame(parent_frame)
        self.control.grid(row=1, column=0, sticky='ew', pady=5)

        # Configure parent_frame's grid (this frame is the pane in PanedWindow)
        parent_frame.grid_rowconfigure(0, weight=1) # Video panel row should expand
        parent_frame.grid_columnconfigure(0, weight=1) # Video panel col should expand
        # Row 1 for controls has weight 0 by default, which is fine.

        ttk.Button(self.control, text="▶ Play", command=self.player.play).pack(side='left', padx=5)
        ttk.Button(self.control, text="⏸ Pause", command=self.player.pause).pack(side='left', padx=5)
        ttk.Button(self.control, text="⏹ Stop", command=self.player.stop).pack(side='left', padx=5)

    def set_media(self, url):
        if not self.videopanel:
            print("VLC videopanel not setup yet!")
            return
        media = self.instance.media_new(url)
        self.player.set_media(media)
        win_id = self.videopanel.winfo_id()
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(win_id)
        elif sys.platform.startswith('win'):
            self.player.set_hwnd(win_id)
        elif sys.platform.startswith('darwin'):
            self.player.set_nsobject(win_id)
        else:
            print("Warnung: Unbekanntes OS, VLC Player Fenster nicht richtig eingebettet.")

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Clip Downloader mit VLC-Vorschau")
        self.config = load_config()
        self.presets = self.load_presets()
        self.clips = []
        self.clip_vars = []
        self.thumb_imgs = []
        self.access_token = None
        self.current_preset = None
        self.vlc = VLCPlayer() if vlc else None # Initialize only if VLC is available

        # Attempt to set a default font
        try:
            default_font = font.nametofont("TkDefaultFont")
            # Using common fonts that tend to render better with scaling
            # Defaulting to Segoe UI for Windows, DejaVu Sans for others, then system default
            # Using point size (e.g., 10) can sometimes help with scaling
            families_to_try = ("Segoe UI", "DejaVu Sans", default_font.actual()["family"])
            chosen_family = default_font.actual()["family"] # Start with current default
            for family in families_to_try:
                if family in font.families():
                    chosen_family = family
                    break

            default_font.configure(family=chosen_family, size=10) # size in points
            self.root.option_add("*Font", default_font)
            print(f"Attempted to set default font to: {chosen_family}, 10pt")
        except Exception as e:
            print(f"Could not set default font: {e}")

        self.build_gui()
        self.obtain_access_token()

    def obtain_access_token(self):
        try:
            self.access_token = get_access_token()
            self.log("Access Token erhalten.")
        except Exception as e:
            messagebox.showerror("Token Fehler", f"Fehler beim Abrufen des Tokens: {e}")

    def load_presets(self):
        if os.path.exists(PRESET_FILE):
            try:
                return json.load(open(PRESET_FILE))
            except Exception:
                messagebox.showwarning("Warnung", f"{PRESET_FILE} ist beschädigt oder ungültig.")
                return {}
        return {}

    def save_presets(self):
        try:
            json.dump(self.presets, open(PRESET_FILE, 'w'), indent=4)
            self.log(f"Preset gespeichert.")
        except Exception as e:
            self.log(f"Fehler beim Speichern des Presets: {e}")

    def build_gui(self):
        # --- Dark Theme Styling ---
        dark_bg = "#2E2E2E"
        light_fg = "#D3D3D3" # Light Grey
        widget_bg = "#3C3C3C"
        entry_select_bg = "#555555" # Selection color for Entry/Text

        self.root.configure(bg=dark_bg)

        s = ttk.Style()
        s.theme_use('clam') # 'clam', 'alt', 'default', 'classic' are common ttk themes. 'clam' is often good for styling.

        # General widget styling
        s.configure('.', background=dark_bg, foreground=light_fg)
        s.configure('TFrame', background=dark_bg)
        s.configure('TLabel', background=dark_bg, foreground=light_fg)
        s.configure('TButton', background=widget_bg, foreground=light_fg) # May need to map states
        s.map('TButton', background=[('active', '#555555')])
        s.configure('TEntry', fieldbackground=widget_bg, foreground=light_fg, insertcolor=light_fg,
                    selectbackground=entry_select_bg, selectforeground=light_fg)
        s.configure('TCombobox', fieldbackground=widget_bg, foreground=light_fg, selectbackground=widget_bg,
                    selectforeground=light_fg, background=widget_bg)
        # For Combobox dropdown list (might need more specific handling if this doesn't cover it)
        self.root.option_add('*TCombobox*Listbox.background', widget_bg)
        self.root.option_add('*TCombobox*Listbox.foreground', light_fg)
        self.root.option_add('*TCombobox*Listbox.selectBackground', entry_select_bg)
        self.root.option_add('*TCombobox*Listbox.selectForeground', light_fg)

        s.configure('Vertical.TScrollbar', background=widget_bg, troughcolor=dark_bg, bordercolor=dark_bg, arrowcolor=light_fg)
        s.map('Vertical.TScrollbar', background=[('active', '#555555')])
        s.configure('Horizontal.TScrollbar', background=widget_bg, troughcolor=dark_bg, bordercolor=dark_bg, arrowcolor=light_fg)
        s.map('Horizontal.TScrollbar', background=[('active', '#555555')])

        s.configure('TCheckbutton', background=dark_bg, foreground=light_fg, indicatorcolor=widget_bg)
        s.map('TCheckbutton',
              background=[('active', dark_bg)],
              indicatorcolor=[('selected', light_fg), ('!selected', widget_bg)])

        # PanedWindow sash color (this is tricky with ttk, might need tk.PanedWindow or direct configure if supported)
        s.configure('TPanedwindow', background=dark_bg)
        s.configure('Sash', background=widget_bg, lightcolor=widget_bg, darkcolor=widget_bg, bordercolor=dark_bg)
        # --- End Dark Theme Styling ---

        # Master PanedWindow (horizontal: settings | clips_and_vlc_area)
        master_paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL) # sashrelief=tk.RAISED, sashwidth=6
        master_paned_window.grid(row=0, column=0, sticky='nsew')

        # Linke Seite: Einstellungen & Buttons (Pane 1 of master_paned_window)
        left_settings_pane = ttk.Frame(master_paned_window, padding=10)
        # left_settings_pane.grid(row=0, column=0, sticky='ns') # PanedWindow manages this
        master_paned_window.add(left_settings_pane, weight=0) # Settings pane, less resize weight initially

        ttk.Label(left_settings_pane, text="Preset:").pack(anchor='w')
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(left_settings_pane, textvariable=self.preset_var, values=list(self.presets.keys()))
        self.preset_combo.pack(fill='x')
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)

        self.save_btn = ttk.Button(left_settings_pane, text="Neues Preset speichern", command=self.save_preset)
        self.save_btn.pack(fill='x', pady=5)

        self.entries = {}
        labels = ["Zeitraum (Tage)", "Max Clips", "Kategorien (Komma)", "Kanäle (Komma)", "Sprachen (Komma)", "Download-Ordner"]
        for lbl in labels:
            ttk.Label(left_settings_pane, text=lbl + ":").pack(anchor='w')
            e = ttk.Entry(left_settings_pane)
            e.pack(fill='x')
            self.entries[lbl] = e

        ttk.Button(left_settings_pane, text="Ordner wählen", command=self.choose_folder).pack(fill='x', pady=5)
        ttk.Button(left_settings_pane, text="Clips suchen", command=self.fetch_thread).pack(fill='x', pady=10)
        ttk.Button(left_settings_pane, text="Herunterladen", command=self.download_thread).pack(fill='x')

        # Right Main Area PanedWindow (Clips | VLC) (Pane 2 of master_paned_window)
        clips_vlc_paned_window = ttk.PanedWindow(master_paned_window, orient=tk.HORIZONTAL)
        master_paned_window.add(clips_vlc_paned_window, weight=1) # This pane gets more resize weight

        # Clip List Area (Pane 1 of clips_vlc_paned_window)
        self.clip_list_display_frame = ttk.Frame(clips_vlc_paned_window, padding=5, width=300, height=400) # Removed style='DebugClip.TFrame'
        self.canvas = tk.Canvas(self.clip_list_display_frame, bg=dark_bg, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.clip_list_display_frame, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.clip_frame = ttk.Frame(self.canvas)
        self.clip_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.clip_frame, anchor='nw')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')
        clips_vlc_paned_window.add(self.clip_list_display_frame, weight=1)

        # VLC Player Area (Pane 2 of clips_vlc_paned_window)
        if self.vlc:
            vlc_pane_container = ttk.Frame(clips_vlc_paned_window, width=640, height=400) # Removed style='DebugVLC.TFrame'
            # It will inherit the TFrame style which is already dark_bg
            clips_vlc_paned_window.add(vlc_pane_container, weight=1)
            self.vlc.setup_ui_in_frame(vlc_pane_container)
        else:
            # If no VLC, add a placeholder frame with a message
            no_vlc_frame = ttk.Frame(clips_vlc_paned_window, width=640, height=400)
            ttk.Label(no_vlc_frame, text="VLC not found. Video preview is disabled.", style='TLabel').pack(pady=20, padx=10)
            clips_vlc_paned_window.add(no_vlc_frame, weight=1)

        # Log-Textfeld unten - now in row 1, under the master_paned_window
        self.log_text = tk.Text(self.root, height=8, bg=widget_bg, fg=light_fg, relief=tk.FLAT, selectbackground=entry_select_bg)
        self.log_text.grid(row=1, column=0, sticky='ew', padx=10, pady=5) # Spans the single column of root

        # Configure root window grid (now 1 main column, 2 rows)
        self.root.columnconfigure(0, weight=1) # Master PanedWindow takes all width
        self.root.rowconfigure(0, weight=1)    # Master PanedWindow takes most height
        self.root.rowconfigure(1, weight=0)    # Log row (fixed height)

    def log(self, msg):
        self.log_text.insert('end', msg + '\n')
        self.log_text.see('end')

    def on_preset_selected(self, event=None):
        name = self.preset_var.get()
        preset = self.presets.get(name, {})
        if not preset:
            self.log("Preset nicht gefunden.")
            return
        self.current_preset = preset
        self.entries["Zeitraum (Tage)"].delete(0, 'end')
        self.entries["Zeitraum (Tage)"].insert(0, preset.get('time_range_days', 7))

        self.entries["Max Clips"].delete(0, 'end')
        self.entries["Max Clips"].insert(0, preset.get('max_clips', 50))

        self.entries["Kategorien (Komma)"].delete(0, 'end')
        self.entries["Kategorien (Komma)"].insert(0, ','.join(preset.get('categories', [])))

        self.entries["Kanäle (Komma)"].delete(0, 'end')
        self.entries["Kanäle (Komma)"].insert(0, ','.join(preset.get('channels', [])))

        self.entries["Sprachen (Komma)"].delete(0, 'end')
        self.entries["Sprachen (Komma)"].insert(0, ','.join(preset.get('languages', [])))

        self.entries["Download-Ordner"].delete(0, 'end')
        self.entries["Download-Ordner"].insert(0, preset.get('download_folder', 'clips_downloaded'))

        self.save_btn.config(text="Preset speichern")

    def save_preset(self):
        name = self.preset_var.get().strip()
        if not name:
            messagebox.showwarning("Warnung", "Bitte Preset-Namen eingeben.")
            return
        self.presets[name] = self.get_preset()
        self.save_presets()
        self.save_btn.config(text="Preset speichern")

    def get_preset(self):
        return {
            'time_range_days': int(self.entries["Zeitraum (Tage)"].get() or 7),
            'max_clips': int(self.entries["Max Clips"].get() or 50),
            'categories': [c.strip() for c in self.entries["Kategorien (Komma)"].get().split(',') if c.strip()],
            'channels': [c.strip() for c in self.entries["Kanäle (Komma)"].get().split(',') if c.strip()],
            'languages': [l.strip() for l in self.entries["Sprachen (Komma)"].get().split(',') if l.strip()],
            'download_folder': self.entries["Download-Ordner"].get() or 'clips_downloaded'
        }

    def choose_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.entries["Download-Ordner"].delete(0, 'end')
            self.entries["Download-Ordner"].insert(0, d)

    def fetch_thread(self):
        if not self.access_token:
            self.log("Kein Zugriffstoken vorhanden. Bitte Programm neu starten.")
            return
        # Wenn kein Preset gewählt, das erste Preset nehmen
        if not self.current_preset:
            if self.presets:
                first_key = next(iter(self.presets))
                self.current_preset = self.presets[first_key]
                self.preset_var.set(first_key)
            else:
                self.log("Keine Presets vorhanden.")
                return
        self.log("Starte Clip-Abfrage")
        # Thread starten und Ergebnis in callback speichern und GUI aktualisieren
        def thread_func():
            try:
                clips = fetch_clips_debug(self.current_preset, self.access_token)
                # max_clips beachten
                max_clips = self.current_preset.get('max_clips', 50)
                self.clips = clips[:max_clips]
                self.clear_clip_list()
                self.show_clips()
                self.log(f"Clip-Abfrage abgeschlossen: {len(self.clips)} Clips gefunden.")
            except Exception as e:
                self.log(f"Fehler bei Clip-Abfrage: {e}")
        threading.Thread(target=thread_func, daemon=True).start()

    def clear_clip_list(self):
        for w in self.clip_frame.winfo_children():
            w.destroy()
        self.clip_vars.clear()
        self.thumb_imgs.clear()

    def show_clips(self):
        if not self.clips:
            self.log("Keine Clips gefunden.")
            return

        def _download_and_create_image(clip):
            """Downloads thumbnail, creates PhotoImage. Can be run in a thread."""
            try:
                url = clip['thumbnail_url'].split('-preview-')[0] + '.jpg'
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                im = Image.open(io.BytesIO(response.content)).resize((120, 68))
                img = ImageTk.PhotoImage(im)
                return clip['id'], img
            except Exception as e:
                # print(f"Could not load thumbnail for {clip.get('url')}: {e}") # Optional for debugging
                return clip['id'], None

        thumbnails = {}
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_img = executor.map(_download_and_create_image, self.clips)
            for clip_id, img in future_to_img:
                if img:
                    thumbnails[clip_id] = img

        self.log(f"Thumbnails geladen: {len(thumbnails)}/{len(self.clips)}")
        self.thumb_imgs.clear()

        for clip in self.clips:
            var = tk.BooleanVar()
            frame = ttk.Frame(self.clip_frame, relief='raised', padding=5)
            cb = ttk.Checkbutton(frame, variable=var)
            cb.pack(side='left')

            img = thumbnails.get(clip['id'])
            if img:
                lbl_img = tk.Label(frame, image=img)
                lbl_img.image = img
                lbl_img.pack(side='left', padx=5)
                self.thumb_imgs.append(img)

            created_at_str = clip.get('created_at', '')
            formatted_date = ''
            if created_at_str and isinstance(created_at_str, str):
                try:
                    if created_at_str.endswith('Z'):
                        created_at_str_modified = created_at_str[:-1] + '+00:00'
                    else:
                        created_at_str_modified = created_at_str
                    dt_obj = datetime.fromisoformat(created_at_str_modified)
                    formatted_date = dt_obj.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    formatted_date = 'Unknown Date'
            else:
                formatted_date = "No Date"

            title_with_date = f"{clip['title']} ({clip['broadcaster_name']}) [{clip['view_count']} Aufrufe] - {formatted_date}"
            ttk.Label(frame, text=title_with_date, wraplength=350).pack(side='left', padx=5)
            preview_btn = ttk.Button(frame, text="Vorschau", command=lambda u=clip['url']: self.play_clip(u))
            if not self.vlc:
                preview_btn.config(state='disabled')
            preview_btn.pack(side='right')
            frame.pack(fill='x', pady=3, padx=2)
            self.clip_vars.append((var, clip['url']))

        self.log(f"{len(self.clips)} Clips angezeigt.")

    def play_clip(self, url):
        if not self.vlc:
            self.log("VLC player not available.")
            return
        self.log(f"Hole direkten Videostream für {url}...")
        stream_url = get_direct_video_url(url)
        if stream_url:
            self.log(f"Starte Wiedergabe...")
            self.vlc.set_media(stream_url)
            self.vlc.player.play()
        else:
            self.log("Fehler: Direkter Videostream konnte nicht geladen werden.")


    def download_thread(self):
        threading.Thread(target=self.download_selected, daemon=True).start()

    def download_selected(self):
        folder_path = self.entries["Download-Ordner"].get() or 'clips_downloaded'
        if not os.path.isabs(folder_path):
            folder_path = os.path.join(script_dir, folder_path)

        selected_urls = [url for var, url in self.clip_vars if var.get()]
        if not selected_urls:
            self.log("❗ Keine Clips ausgewählt.")
            return

        self.log(f"Starte Download von {len(selected_urls)} Clips...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            # Use executor.map to download clips in parallel.
            # The lambda function calls download_clip for each url.
            # list() is used to ensure all tasks are executed before proceeding.
            list(executor.map(lambda url: download_clip(url, folder_path, self.log), selected_urls))

        self.log("Alle Downloads abgeschlossen oder versucht.")

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
