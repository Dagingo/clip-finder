import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Canvas, Scrollbar
from PIL import Image, ImageTk
import io
import vlc
import yt_dlp

CONFIG_FILE = 'twitch_presets.json'
RESULTS_FILE = 'clip_results.txt'
PRESET_FILE = CONFIG_FILE  # falls du nur eine Datei für Presets nutzt
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

    results = []

    print(f"[DEBUG] Token: {access_token}")
    print(f"[DEBUG] Base Params: {base_params}")
    print(f"[DEBUG] Categories: {categories}")
    print(f"[DEBUG] Channels: {channels}")
    print(f"[DEBUG] Languages: {languages}")

    if not categories and not channels:
        print("[DEBUG] Keine Kategorien oder Kanäle ausgewählt: Alle Top-Spiele durchsuchen.")
        top_games = get_top_games(headers)
        print(f"[DEBUG] Gefundene Top-Spiele: {[g['name'] for g in top_games]}")
        for game in top_games:
            game_id = game['id']
            params = base_params.copy()
            params['game_id'] = game_id
            print(f"[DEBUG] Request URL: {CLIPS_URL}")
            print(f"[DEBUG] Request Params: {params}")
            print(f"[DEBUG] Request Headers: {headers}")
            response = requests.get(CLIPS_URL, headers=headers, params=params)
            print(f"[DEBUG] Response Status: {response.status_code}")
            print(f"[DEBUG] Response Text: {response.text}")
            if response.ok:
                for clip in response.json().get('data', []):
                    if not languages or clip['language'] in languages:
                        results.append(clip)
        return sorted(results, key=lambda c: c['view_count'], reverse=True)

    for category in categories or [None]:
        game_id = get_game_id(category, headers) if category else None

        for channel in channels or [None]:
            broadcaster_id = get_user_id(channel, headers) if channel else None

            params = base_params.copy()
            if game_id:
                params['game_id'] = game_id
            if broadcaster_id:
                params['broadcaster_id'] = broadcaster_id

            print(f"[DEBUG] Request URL: {CLIPS_URL}")
            print(f"[DEBUG] Request Params: {params}")
            print(f"[DEBUG] Request Headers: {headers}")
            response = requests.get(CLIPS_URL, headers=headers, params=params)
            print(f"[DEBUG] Response Status: {response.status_code}")
            print(f"[DEBUG] Response Text: {response.text}")
            if response.ok:
                for clip in response.json().get('data', []):
                    if not languages or clip['language'] in languages:
                        results.append(clip)

    return sorted(results, key=lambda c: c['view_count'], reverse=True)

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
    def __init__(self, parent):
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        self.videopanel = tk.Frame(self.parent, bg='black', width=640, height=360)
        self.videopanel.grid(row=0, column=2, sticky='nsew', padx=10, pady=10)
        self.parent.grid_columnconfigure(2, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)

        self.control = ttk.Frame(self.parent)
        self.control.grid(row=1, column=2, sticky='ew', padx=10)

        ttk.Button(self.control, text="▶ Play", command=self.player.play).pack(side='left', padx=5)
        ttk.Button(self.control, text="⏸ Pause", command=self.player.pause).pack(side='left', padx=5)
        ttk.Button(self.control, text="⏹ Stop", command=self.player.stop).pack(side='left', padx=5)

        self.parent.update()  # Warten, bis Videopanel da ist

    def set_media(self, url):
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
        self.vlc = VLCPlayer(self.root)
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
        # Linke Seite: Einstellungen & Buttons
        left = ttk.Frame(self.root, padding=10)
        left.grid(row=0, column=0, sticky='ns')

        ttk.Label(left, text="Preset:").pack(anchor='w')
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(left, textvariable=self.preset_var, values=list(self.presets.keys()))
        self.preset_combo.pack(fill='x')
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)

        self.save_btn = ttk.Button(left, text="Neues Preset speichern", command=self.save_preset)
        self.save_btn.pack(fill='x', pady=5)

        self.entries = {}
        labels = ["Zeitraum (Tage)", "Max Clips", "Kategorien (Komma)", "Kanäle (Komma)", "Sprachen (Komma)", "Download-Ordner"]
        for lbl in labels:
            ttk.Label(left, text=lbl + ":").pack(anchor='w')
            e = ttk.Entry(left)
            e.pack(fill='x')
            self.entries[lbl] = e

        ttk.Button(left, text="Ordner wählen", command=self.choose_folder).pack(fill='x', pady=5)
        ttk.Button(left, text="Clips suchen", command=self.fetch_thread).pack(fill='x', pady=10)
        ttk.Button(left, text="Herunterladen", command=self.download_thread).pack(fill='x')

        # Rechte Seite: Clip-Liste mit Scrollbar
        right = ttk.Frame(self.root, padding=10)
        right.grid(row=0, column=1, sticky='nsew')

        self.canvas = tk.Canvas(right)
        self.scrollbar = ttk.Scrollbar(right, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.clip_frame = ttk.Frame(self.canvas)
        self.clip_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.clip_frame, anchor='nw')

        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')

        # Log-Textfeld unten
        self.log_text = tk.Text(self.root, height=8)
        self.log_text.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=5)

        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

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
        for clip in self.clips:
            var = tk.BooleanVar()
            frame = ttk.Frame(self.clip_frame, relief='raised', padding=5)
            cb = ttk.Checkbutton(frame, variable=var)
            cb.pack(side='left')

            # Thumbnail laden
            try:
                url = clip['thumbnail_url'].split('-preview-')[0] + '.jpg'
                im = Image.open(io.BytesIO(requests.get(url, timeout=5).content)).resize((120, 68))
                img = ImageTk.PhotoImage(im)
                lbl_img = tk.Label(frame, image=img)
                lbl_img.image = img
                lbl_img.pack(side='left', padx=5)
                self.thumb_imgs.append(img)  # Referenz behalten
            except Exception:
                pass

            title = f"{clip['title']} ({clip['broadcaster_name']}) [{clip['view_count']} Aufrufe]"
            ttk.Label(frame, text=title, wraplength=300).pack(side='left', padx=5)

            ttk.Button(frame, text="Vorschau", command=lambda u=clip['url']: self.play_clip(u)).pack(side='right')

            frame.pack(fill='x', pady=3, padx=2)
            self.clip_vars.append((var, clip['url']))

        self.log(f"{len(self.clips)} Clips angezeigt.")

    def play_clip(self, url):
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
        folder = self.entries["Download-Ordner"].get() or 'clips_downloaded'
        selected = [url for var, url in self.clip_vars if var.get()]
        if not selected:
            self.log("❗ Keine Clips ausgewählt.")
            return
        for url in selected:
            download_clip(url, folder, self.log)

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
