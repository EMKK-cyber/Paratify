import sys
import os

# Windows'ta eski cmd.exe UTF-8 kutu çizgilerini/emojileri bozabiliyor,
# bu yüzden konsolu UTF-8 codepage'e geçiriyoruz (macOS/Linux'ta etkisiz).
if os.name == "nt":
    os.system("chcp 65001 > nul")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import subprocess
import time
import shutil
import random
import contextlib
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
import re
import requests
import urllib3
import html
import json

# Rich bileşenleri
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.prompt import Prompt, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.align import Align
from rich.layout import Layout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()
ytm = YTMusic()

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlists.json")

# Kalıcı Depolama için Yükleme Fonksiyonu
def load_playlists():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[bold red]Veritabanı okuma hatası, yeni veri oluşturuluyor: {e}[/]")
    return {
        "Liste 1": [],
        "Liste 2": [],
        "Liste 3": []
    }

# Kalıcı Depolama için Kaydetme Fonksiyonu
def save_playlists():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(playlists_db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        console.print(f"[bold red]Veritabanı kaydetme hatası: {e}[/]")

# Çoklu Oynatma Listesi Yönetimi
playlists_db = load_playlists()
active_playlist_name = list(playlists_db.keys())[0] if playlists_db else "Liste 1"
if active_playlist_name not in playlists_db:
    playlists_db[active_playlist_name] = []

current_track_index = -1

# ----------------------------------------------------------------
# TERMİNAL TUŞ YAKALAMA (Windows / macOS / Linux)
# ----------------------------------------------------------------
@contextlib.contextmanager
def raw_terminal():
    """Terminali 'ham' moda alır, böylece Enter'a basmadan tek tuş okuyabiliriz.
    Windows'ta bu gerekmiyor (msvcrt zaten anlık okuyor), o yüzden orada no-op."""
    if os.name == "nt" or not sys.stdin.isatty():
        yield
        return
    import termios, tty
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def get_key_nonblocking():
    """Bekletmeden (bloklamadan) basılan bir tuş varsa döner, yoksa None."""
    if os.name == "nt":
        try:
            import msvcrt
        except ImportError:
            return None
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode("utf-8", errors="ignore")
            except Exception:
                return None
        return None
    else:
        if not sys.stdin.isatty():
            return None
        import select
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1)
        return None

# ----------------------------------------------------------------
# TERMİNAL GÖRSEL ŞÖLEN (Simüle Edilmiş Ses Görselleştirici)
# ----------------------------------------------------------------
BAR_CHARS = "▁▂▃▄▅▆▇█"
_visualizer_levels = [0] * 42

def generate_visualizer_bars():
    """mpv'nin ham ses verisine erişimimiz yok (ayrı bir process), bu yüzden
    süreye/zamana duyarlı, göz alıcı bir 'sahte ama inandırıcı' bar animasyonu
    üretiyoruz — çoğu terminal müzik çaları bunu böyle yapar."""
    for i in range(len(_visualizer_levels)):
        delta = random.randint(-2, 3)
        _visualizer_levels[i] = max(0, min(len(BAR_CHARS) - 1, _visualizer_levels[i] + delta))
    bar_str = "".join(BAR_CHARS[lvl] for lvl in _visualizer_levels)
    return bar_str

# ----------------------------------------------------------------
# KILL SWITCH ("Panik Butonu") EFEKTİ
# ----------------------------------------------------------------
def kill_switch_effect():
    """Esc'e basılınca tetiklenen, hacker estetiğinde ani kapanış efekti."""
    clear_screen()
    console.print(Align.center(Text("⚠  CONNECTION LOST  ⚠", style="bold red on black")))
    time.sleep(0.35)
    clear_screen()

    fake_ips = [f"{random.randint(10,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}" for _ in range(6)]
    lines = [
        "[dim red]> killing audio stream...[/]",
        "[dim red]> flushing socket buffers...[/]",
    ]
    for ip in fake_ips:
        lines.append(f"[dim red]> connection to {ip}:443 terminated[/]")
    lines.append("[bold red]> session closed.[/]")

    for line in lines:
        console.print(line)
        time.sleep(0.06)
    time.sleep(0.5)
    clear_screen()

# ----------------------------------------------------------------
# SÖZLER (LYRICS)
# ----------------------------------------------------------------
GLITCH_CHARS = "!<>-_\\/{}=+*^?#$%&~"

def fetch_lyrics(video_id):
    """YTMusic'in resmi (lisanslı) sözler API'sinden mevcut şarkının sözlerini çeker."""
    try:
        watch_playlist = ytm.get_watch_playlist(video_id)
        browse_id = watch_playlist.get("lyrics")
        if not browse_id:
            return None
        lyrics_data = ytm.get_lyrics(browse_id)
        return lyrics_data.get("lyrics")
    except Exception:
        return None

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def draw_header():
    header_text = """
    ██████╗  █████╗ ██████╗  ██████╗  ██████╗████████╗██╗███████╗██╗   ██╗
    ██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝██║██╔════╝╚██╗ ██╔╝
    ██████╔╝███████║██████╔╝██║   ██║██║        ██║   ██║█████╗   ╚████╔╝ 
    ██╔═══╝ ██╔══██║██╔══██╗██║   ██║██║        ██║   ██║██╔══╝    ╚██╔╝  
    ██║     ██║  ██║██║  ██║╚██████╔╝╚██████╗   ██║   ██║██║        ██║   
    ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝   ╚═╝   ╚═╝╚═╝        ╚═╝   
    """
    console.print(Align.center(Text(header_text, style="bold red")))
    console.print(Align.center(Panel(Text(f"Paraotify v1.4.0 — Persistent Multi-Playlist Sync", style="bold green", justify="center"), border_style="red")))
    console.print("\n")

def display_playlist():
    """Mevcut aktif çalma listesini şık bir panelde gösterir"""
    active_list = playlists_db[active_playlist_name]
    if not active_list:
        return Panel(f"[dim white]'{active_playlist_name}' listesi boş. Müzik aratarak veya link ekleyerek doldurun![/]", title=f"[bold red]📋 ÇALMA LİSTESİ ({active_playlist_name})[/]", border_style="red")
    
    playlist_table = Table(show_header=False, box=None, expand=True)
    playlist_table.add_column("Index", style="dim", width=4)
    playlist_table.add_column("Track", style="white")
    
    for idx, track in enumerate(active_list):
        prefix = "▶ " if idx == current_track_index else f"{idx + 1}. "
        style = "bold green" if idx == current_track_index else "white"
        
        playlist_table.add_row(
            Text(prefix, style="bold green" if idx == current_track_index else "red"),
            Text(f"{track['title']} - {track['artist']}", style=style)
        )
        
    return Panel(playlist_table, title=f"[bold red]📋 ÇALMA LİSTESİ ({active_playlist_name} — {len(active_list)} Şarkı)[/]", border_style="red")

def select_or_create_playlist():
    """Kullanıcının mevcut listelerden birini seçmesini, temizlemesini veya yeni bir tane oluşturmasını sağlar"""
    global active_playlist_name
    
    while True:
        clear_screen()
        draw_header()
        
        console.print("[bold cyan]=== ÇALMA LİSTELERİ ===[/]\n")
        
        for idx, (name, songs) in enumerate(playlists_db.items(), 1):
            status = "[bold green](Aktif)[/]" if name == active_playlist_name else ""
            console.print(f"[white][{idx}][/] {name} [dim white]({len(songs)} Şarkı)[/] {status}")
            
        console.print("[white][n][/] Yeni Liste Oluştur")
        console.print("[white][d][/] Liste Sil")
        console.print("[white][g][/] Geri Dön")
        console.print("\n")
        
        choice = Prompt.ask("[bold red]Seçiminiz[/]").strip().lower()
        
        if choice == 'g':
            break
        elif choice == 'n':
            new_name = Prompt.ask("[bold red]Yeni listenin adını girin[/]").strip()
            if new_name:
                if new_name in playlists_db:
                    console.print("[bold red]❌ Bu isimde bir liste zaten mevcut![/]")
                    time.sleep(1.5)
                else:
                    playlists_db[new_name] = []
                    active_playlist_name = new_name
                    save_playlists()
                    console.print(f"[bold green]✔ '{new_name}' başarıyla oluşturuldu ve aktif hale getirildi![/]")
                    time.sleep(1.5)
                    break
        elif choice == 'd':
            delete_choice = Prompt.ask("[bold red]Silmek istediğiniz listenin numarasını girin[/]").strip()
            try:
                idx = int(delete_choice) - 1
                keys = list(playlists_db.keys())
                if 0 <= idx < len(keys):
                    target_key = keys[idx]
                    if len(playlists_db) <= 1:
                        console.print("[bold red]❌ Son kalan çalma listesini silemezsiniz![/]")
                        time.sleep(1.5)
                        continue
                    
                    del playlists_db[target_key]
                    if active_playlist_name == target_key:
                        active_playlist_name = list(playlists_db.keys())[0]
                    save_playlists()
                    console.print(f"[bold green]✔ '{target_key}' başarıyla silindi![/]")
                    time.sleep(1.5)
                else:
                    console.print("[bold red]❌ Geçersiz numara![/]")
                    time.sleep(1)
            except ValueError:
                console.print("[bold red]❌ Geçersiz seçim![/]")
                time.sleep(1)
        else:
            try:
                idx = int(choice) - 1
                keys = list(playlists_db.keys())
                if 0 <= idx < len(keys):
                    active_playlist_name = keys[idx]
                    console.print(f"[bold green]✔ Aktif liste '{active_playlist_name}' olarak değiştirildi![/]")
                    time.sleep(1.5)
                    break
                else:
                    console.print("[bold red]❌ Geçersiz seçim![/]")
                    time.sleep(1)
            except ValueError:
                console.print("[bold red]❌ Geçersiz seçim![/]")
                time.sleep(1)

def clean_track_title(title):
    """Spotify'dan gelen başlıkları YTMusic üzerinde daha iyi eşleşmesi için optimize eder"""
    # Remastered, Live, Deluxe Edition vb. gürültü çıkaran ifadeleri temizle
    title = re.sub(r'\(.*?Remastered.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\[.*?Remastered.*?\]', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\(.*?Live.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\(.*?Deluxe.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\(.*?Single.*?\)', '', title, flags=re.IGNORECASE)
    return title.strip()

def search_music(query):
    with Console().status("[bold red]YouTube Music veritabanında taranıyor...[/]", spinner="shark"):
        search_results = ytm.search(query, filter="songs")
    return search_results

def display_results(results):
    if not results:
        console.print(Panel("[bold red]❌ Eşleşen bir şarkı bulunamadı![/]", border_style="red"))
        return False

    table = Table(title="[bold green]🔍 Arama Sonuçları[/]", border_style="red", show_header=True, header_style="bold red")
    table.add_column("No", style="dim", width=4, justify="center")
    table.add_column("Şarkı Adı", style="bold white", width=30)
    table.add_column("Sanatçı", style="yellow", width=25)
    table.add_column("Albüm", style="cyan", width=20)
    table.add_column("Süre", style="green", justify="right")

    for idx, item in enumerate(results[:8], start=1):
        title = item.get('title', 'Bilinmeyen Şarkı')
        artists = ", ".join([a['name'] for a in item.get('artists', [])])
        album = item.get('album', {}).get('name', 'Single') if item.get('album') else 'Single'
        duration = item.get('duration', 'N/A')
        
        table.add_row(str(idx), title, artists, album, duration)

    console.print(table)
    return True

def get_stream_url(video_id):
    with Console().status("[bold cyan]Ses akışı çözümleniyor ve tamponlanıyor...[/]", spinner="dots"):
        ydl_opts = {
            'format': 'bestaudio[protocol=https]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 15,
        }
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                return info['url']
        except Exception as e:
            console.print(f"[bold red]Akış çözme hatası: {e}[/]")
            return None

def import_spotify_playlist(url):
    """Spotify çalma listelerini senkronize eder"""
    global playlists_db, active_playlist_name
    
    # URL içerisinden playlist ID'sini ayıklayalım
    playlist_id_match = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    if not playlist_id_match:
        console.print("[bold red]❌ Geçersiz Spotify çalma listesi linki![/]")
        time.sleep(2)
        return
        
    playlist_id = playlist_id_match.group(1)
    entries = []
    
    # Spotify'ın herkese açık embed (widget) adresi
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "tr,en-US;q=0.7,en;q=0.3"
    }
    
    try:
        with Console().status("[bold green]Spotify embed verileri kazınıyor...[/]", spinner="earth"):
            response = requests.get(embed_url, headers=headers, verify=False, timeout=15)
            
            if response.status_code == 200:
                # 1. YOL: __NEXT_DATA__
                next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>', response.text)
                if next_data_match:
                    try:
                        raw_json = html.unescape(next_data_match.group(1))
                        data = json.loads(raw_json)
                        props = data.get("props", {}).get("pageProps", {})
                        state = props.get("state", {})
                        tracks = state.get("playlist", {}).get("tracks", {}).get("items", [])
                        
                        for item in tracks:
                            track_info = item.get("track", {})
                            title = track_info.get("name")
                            artists = [a.get("name") for a in track_info.get("artists", [])]
                            if title:
                                entries.append((title, ", ".join(artists)))
                    except Exception:
                        pass

                # 2. YOL: resource
                if not entries:
                    resource_match = re.search(r'<script id="resource" type="application/json">([^<]+)</script>', response.text)
                    if resource_match:
                        try:
                            raw_json = html.unescape(resource_match.group(1))
                            data = json.loads(raw_json)
                            tracks = data.get("tracks", {}).get("items", [])
                            for t in tracks:
                                track_data = t.get("track", t)
                                title = track_data.get("name")
                                artists = [a.get("name") for a in track_data.get("artists", [])]
                                if title:
                                    entries.append((title, ", ".join(artists)))
                        except Exception:
                            pass
                            
    except Exception:
        pass

    # EĞER SPOTIFY BOT ENGELLERİ SÜREKLİ BLOKE EDİYORSA: MANUEL BYPASS MODU DEVREYE GİRER
    if not entries:
        console.print("\n[bold yellow]⚠ Spotify bot koruması aşılamadı. Manuel Bypass Modu devreye sokuluyor...[/]")
        console.print("[bold cyan]Bu yöntem %100 çalışır ve Spotify'ın engellemesi imkansızdır.[/]\n")
        
        console.print("[white]1.[/] Tarayıcından şu adrese git: [underline blue]https://open.spotify.com/playlist/" + playlist_id + "[/]")
        console.print("[white]2.[/] Sayfada boş bir yere sağ tıklayıp [bold]İncele (Inspect)[/] de ve [bold]Konsol (Console)[/] sekmesine tıkla.")
        console.print("[white]3.[/] Konsolun altındaki yazma yerine [bold]allow pasting[/] yazıp Enter'a basarak kilidi aç.")
        console.print("[white]4.[/] Aşağıdaki temiz kodu kopyala, konsola yapıştırıp [bold]Enter[/]'a bas:\n")
        
        js_code = """
"allow pasting"; "izin ver";
(function() {
    let playlistContainer = document.querySelector('[data-testid="playlist-tracklist"]') || 
                            document.querySelector('[role="grid"]');
    
    let songs = [];

    if (playlistContainer) {
        let tracks = playlistContainer.querySelectorAll('div[data-testid="tracklist-row"]');
        
        tracks.forEach(track => {
            let titleEl = track.querySelector('div[aria-colindex="2"] a') || 
                          track.querySelector('div[aria-colindex="2"] div') ||
                          track.querySelector('a[data-testid="internal-track-link"]');
            
            let title = titleEl ? titleEl.innerText.trim() : "";

            let artistEls = Array.from(track.querySelectorAll('a[href*="/artist/"]'));
            let artists = artistEls.map(a => a.innerText.trim()).join(', ');

            if (title) {
                songs.push({
                    title: title,
                    artist: artists || "Unknown Artist"
                });
            }
        });
    }

    if (songs.length > 0) {
        console.log(JSON.stringify(songs));
    } else {
        console.log("Şarkılar bulunamadı. Lütfen aktif bir çalma listesi sayfasında olduğunuzdan emin olun.");
    }
})();
        """
        console.print(f"[dim yellow]{js_code.strip()}[/]\n")
        
        console.print("[white]5.[/] Konsolda çıkan ve [bold green][{\"title\":...}][/] ile başlayan satırın tamamını kopyala.")
        console.print("[white]6.[/] Kopyaladığın o çıktıyı aşağıdaki alana yapıştır.\n")
        
        while True:
            user_input = input("JSON Çıktısını Buraya Yapıştır (İptal için 'q'): ").strip()
            if user_input.lower() == 'q':
                console.print("[bold red]❌ İşlem kullanıcı tarafından iptal edildi.[/]")
                time.sleep(2)
                return
                
            if "function()" in user_input or "querySelectorAll" in user_input:
                console.print("[bold red]❌ Hata: JS kodunun kendisini yapıştırdın![/]")
                console.print("[yellow]Lütfen önce bu kodu tarayıcı konsolunda çalıştırıp, konsolun ürettiği çıktıyı kopyala.[/]\n")
                continue
                
            if not user_input:
                console.print("[bold red]❌ Girdi boş olamaz.[/]")
                continue
                
            try:
                json_clean_match = re.search(r"(\[.*\])", user_input)
                if json_clean_match:
                    user_input = json_clean_match.group(1)
                    
                data = json.loads(user_input)
                for item in data:
                    title = item.get("title")
                    artist = item.get("artist", "")
                    if title:
                        entries.append((title, artist))
                if entries:
                    break
            except Exception as e:
                console.print(f"[bold red]❌ Geçersiz JSON formatı! (Hata: {e})[/]\n")

    # Şarkılar başarıyla alındıysa YTMusic eşleşmesini başlat
    total_songs = len(entries)
    console.print(f"\n[bold green]✔ Toplam {total_songs} şarkı başarıyla alındı! '{active_playlist_name}' listesi için YTMusic üzerinde aranıyor...[/]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="bold green"),
        TaskProgressColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task("[bold red]Kuyruğa ekleniyor...[/]", total=total_songs)
        
        for title, artist in entries:
            # Şarkı ismini temizle (Remastered vb. ifadeleri uçur)
            cleaned_title = clean_track_title(title)
            title_query = f"{cleaned_title} {artist}".strip()
            try:
                search_results = ytm.search(title_query, filter="songs")
                if search_results:
                    # En iyi eşleşmeyi bulmak için basit bir filtre
                    best_match = search_results[0]
                    playlists_db[active_playlist_name].append({
                        "title": best_match['title'],
                        "artist": ", ".join([a['name'] for a in best_match['artists']]),
                        "video_id": best_match['videoId'],
                        "duration": best_match.get('duration', 'N/A')
                    })
            except Exception:
                pass
            
            progress.advance(task)
            
    # Listeyi kalıcı olarak dosyaya kaydet
    save_playlists()
    console.print(f"\n[bold green]🎉 Başarılı! {len(playlists_db[active_playlist_name])} şarkı '{active_playlist_name}' çalma listene aktarıldı ve kaydedildi.[/]")
    time.sleep(2.5)

def build_play_card(track, bars):
    return Panel(
        Align.center(
            Text.from_markup(
                f"[bold red]ŞİMDİ OYNATILIYOR[/]\n\n"
                f"[bold white]🎵 Şarkı:[/] [green]{track['title']}[/]\n"
                f"[bold white]🎤 Sanatçı:[/] [yellow]{track['artist']}[/]\n\n"
                f"[bold green]{bars}[/]\n\n"
                f"[bold dim cyan]🔊 Kontroller:[/]\n"
                f"[dim white]q:[/] Sıradakine geç\n"
                f"[dim white]l:[/] 📜 Şarkı sözlerini göster/gizle\n"
                f"[dim white]Esc:[/] ⛔ Kill Switch (anında durdur ve menüye dön)\n"
                f"[dim white]Ctrl+C:[/] Çalmayı durdur ve menüye dön\n\n"
                f"[bold red]⚡ sys.audio: [pipewire][/]"
            )
        ),
        border_style="green",
        expand=True,
        subtitle="[bold red]fsociety audio engine v1.4[/]"
    )

def build_lyrics_card(track, revealed_text, glitch_tail, done):
    body = f"[bold magenta]SÖZLER — {track['title']}[/]\n\n{revealed_text}[dim red]{glitch_tail}[/]"
    if done:
        body += "\n\n[dim white](gizlemek için tekrar 'l'ye bas)[/]"
    return Panel(
        Text.from_markup(body),
        border_style="magenta",
        expand=True,
        title="[bold magenta]📜 lyrics.decrypt()[/]"
    )

def play_engine():
    """Çalma listesindeki şarkıları sırayla oynatan, canlı görselleştirmeli ana döngü"""
    global current_track_index

    if not shutil.which("mpv"):
        clear_screen()
        draw_header()
        console.print(Panel(
            "[bold red]❌ 'mpv' bulunamadı![/]\n\n"
            "[white]Paraotify sesi çalmak için mpv kullanır. Kurulum:[/]\n"
            "  [bold cyan]macOS:[/]    brew install mpv\n"
            "  [bold cyan]Linux:[/]    sudo apt install mpv   (veya dnf/pacman)\n"
            "  [bold cyan]Windows:[/]  choco install mpv   (veya winget install mpv.io.mpv)\n\n"
            "[dim white]Kurulumdan sonra terminali yeniden başlatman gerekebilir.[/]",
            border_style="red", title="[bold red]Eksik Bağımlılık[/]"
        ))
        time.sleep(3)
        return

    active_list = playlists_db[active_playlist_name]

    with raw_terminal():
        while current_track_index < len(active_list):
            track = active_list[current_track_index]
            stream_url = get_stream_url(track['video_id'])

            if not stream_url:
                current_track_index += 1
                continue

            cmd = ["mpv", "--no-video", "--force-window=no", stream_url]
            try:
                process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                console.print(f"[bold red]Oynatma hatası: {e}[/]")
                current_track_index += 1
                continue

            clear_screen()
            draw_header()

            layout = Layout()
            layout.split_row(
                Layout(name="now_playing", ratio=3),
                Layout(name="playlist_view", ratio=2)
            )
            layout["playlist_view"].update(display_playlist())

            lyrics_text = None
            lyrics_mode = False
            lyrics_revealed = 0
            lyrics_done_since = None
            panic = False

            try:
                with Live(layout, console=console, refresh_per_second=10, screen=False):
                    while process.poll() is None:
                        key = get_key_nonblocking()
                        if key:
                            if key == "\x1b":  # ESC -> Kill Switch
                                process.terminate()
                                panic = True
                                break
                            elif key.lower() == "q":  # Sıradakine geç
                                process.terminate()
                                break
                            elif key.lower() == "l":  # Sözleri göster/gizle
                                if not lyrics_mode:
                                    if lyrics_text is None:
                                        lyrics_text = fetch_lyrics(track['video_id']) or "Bu şarkı için söz bulunamadı."
                                    lyrics_mode = True
                                    lyrics_revealed = 0
                                    lyrics_done_since = None
                                else:
                                    lyrics_mode = False

                        if lyrics_mode:
                            if lyrics_revealed < len(lyrics_text):
                                lyrics_revealed = min(len(lyrics_text), lyrics_revealed + 3)
                                tail_len = min(6, len(lyrics_text) - lyrics_revealed)
                                glitch_tail = "".join(random.choice(GLITCH_CHARS) for _ in range(tail_len))
                                done = False
                            else:
                                glitch_tail = ""
                                done = True
                                if lyrics_done_since is None:
                                    lyrics_done_since = time.time()
                                elif time.time() - lyrics_done_since > 6:
                                    lyrics_mode = False
                            shown = lyrics_text[:lyrics_revealed].replace("[", "\\[")
                            layout["now_playing"].update(build_lyrics_card(track, shown, glitch_tail, done))
                        else:
                            bars = generate_visualizer_bars()
                            layout["now_playing"].update(build_play_card(track, bars))

                        time.sleep(0.1)
            except KeyboardInterrupt:
                process.terminate()
                console.print("\n[bold red]⏹️ Oynatma listesi durduruldu.[/]")
                return

            if panic:
                kill_switch_effect()
                console.print("[bold red]⛔ Kill Switch tetiklendi. Menüye dönülüyor.[/]")
                time.sleep(1)
                return

            current_track_index += 1

    if current_track_index >= len(active_list):
        current_track_index = -1

def create_mood_playlist():
    """Bir mood/anahtar kelimeye göre (ör. 'dark ambient', 'lo-fi for coding') otomatik liste oluşturur"""
    global playlists_db, active_playlist_name

    mood = Prompt.ask("[bold red]Mood / anahtar kelime gir[/] [dim white](ör: dark ambient, cyberpunk, lo-fi for coding)[/]").strip()
    if not mood:
        return

    with Console().status(f"[bold red]'{mood}' için YouTube Music taranıyor...[/]", spinner="shark"):
        try:
            results = ytm.search(mood, filter="songs")
        except Exception as e:
            console.print(f"[bold red]❌ Arama hatası: {e}[/]")
            time.sleep(1.5)
            return

    if not results:
        console.print("[bold red]❌ Bu anahtar kelime için sonuç bulunamadı.[/]")
        time.sleep(1.5)
        return

    max_count = min(len(results), 25)
    count = IntPrompt.ask(f"[bold red]Listeye kaç şarkı eklensin? (1-{max_count})[/]", default=min(10, max_count))
    count = max(1, min(count, max_count))

    default_name = mood.title()
    playlist_name = Prompt.ask("[bold red]Yeni listenin adı[/]", default=default_name).strip()
    if not playlist_name:
        playlist_name = default_name
    if playlist_name in playlists_db:
        console.print("[bold red]❌ Bu isimde bir liste zaten var![/]")
        time.sleep(1.5)
        return

    new_tracks = []
    for item in results[:count]:
        video_id = item.get("videoId")
        if not video_id:
            continue
        new_tracks.append({
            "title": item.get("title", "Bilinmeyen Şarkı"),
            "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
            "video_id": video_id,
            "duration": item.get("duration", "N/A")
        })

    playlists_db[playlist_name] = new_tracks
    active_playlist_name = playlist_name
    save_playlists()
    console.print(f"\n[bold green]✔ '{playlist_name}' listesi {len(new_tracks)} şarkıyla oluşturuldu ve aktif hale getirildi![/]")
    time.sleep(2)

def manage_track_list():
    """Aktif listedeki şarkıları sıralama, silme veya favorilere ekleme ekranı"""
    global playlists_db, active_playlist_name, current_track_index

    while True:
        clear_screen()
        draw_header()

        active_list = playlists_db[active_playlist_name]
        console.print(display_playlist())

        if not active_list:
            console.print("\n[dim white]Liste boş, yönetilecek bir şey yok.[/]")
            time.sleep(1.2)
            return

        console.print("\n[bold cyan]=== ŞARKI YÖNETİMİ ===[/]")
        console.print("[dim white]Bir şarkı numarası gir (yukarı/aşağı taşı, sil, favorile), 'g' ile geri dön.[/]\n")

        choice = Prompt.ask("[bold red]Şarkı numarası veya 'g'[/]").strip().lower()
        if choice == 'g':
            return

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(active_list)):
                raise ValueError
        except ValueError:
            console.print("[bold red]❌ Geçersiz seçim![/]")
            time.sleep(1)
            continue

        track = active_list[idx]
        clear_screen()
        draw_header()
        console.print(Panel(
            f"[bold white]{track['title']}[/]\n[yellow]{track['artist']}[/]",
            title=f"[bold red]#{idx + 1}[/]", border_style="red"
        ))
        console.print("[white][u][/] ⬆  Yukarı Taşı")
        console.print("[white][d][/] ⬇  Aşağı Taşı")
        console.print("[white][f][/] ⭐ Favorilere Ekle")
        console.print("[white][x][/] 🗑  Sil")
        console.print("[white][g][/] Geri Dön\n")

        action = Prompt.ask("[bold red]İşlem[/]", choices=["u", "d", "f", "x", "g"])

        if action == 'u':
            if idx > 0:
                active_list[idx - 1], active_list[idx] = active_list[idx], active_list[idx - 1]
                save_playlists()
        elif action == 'd':
            if idx < len(active_list) - 1:
                active_list[idx + 1], active_list[idx] = active_list[idx], active_list[idx + 1]
                save_playlists()
        elif action == 'f':
            if "Favoriler" not in playlists_db:
                playlists_db["Favoriler"] = []
            already = any(t.get('video_id') == track.get('video_id') for t in playlists_db["Favoriler"])
            if already:
                console.print("[dim white]Zaten favorilerde.[/]")
            else:
                playlists_db["Favoriler"].append(track)
                console.print("[bold green]✔ Favorilere eklendi![/]")
            save_playlists()
            time.sleep(1)
        elif action == 'x':
            del active_list[idx]
            if current_track_index == idx:
                current_track_index = -1
            elif current_track_index > idx:
                current_track_index -= 1
            save_playlists()
            console.print("[bold red]🗑 Şarkı silindi.[/]")
            time.sleep(1)

def main():
    global current_track_index, active_playlist_name
    
    while True:
        clear_screen()
        draw_header()
        
        console.print(display_playlist())
        console.print("\n")
        
        # Seçenekler listesi
        console.print("[bold red][1][/] Tekil Müzik Ara ve Aktif Listeye Ekle")
        console.print("[bold red][2][/] Spotify / YouTube Çalma Listesi Senkronize Et (Link Yapıştır)")
        console.print("[bold red][3][/] Çalma Listelerini Yönet (Seç / Değiştir / Yeni / Sil)")
        console.print("[bold red][6][/] 🌙 Mood/Anahtar Kelimeye Göre Otomatik Liste Oluştur")
        
        active_list = playlists_db[active_playlist_name]
        if active_list:
            console.print("[bold red][4][/] Aktif Çalma Listesini Başlat")
            console.print("[bold red][5][/] Aktif Çalma Listesini Temizle")
            console.print("[bold red][7][/] 🛠  Aktif Listedeki Şarkıları Yönet (Sırala / Sil / Favorile)")
        console.print("[bold red][q][/] Çıkış")
        console.print("\n")
        
        choice_options = ["1", "2", "3", "6", "q"]
        if active_list:
            choice_options.extend(["4", "5", "7"])
            
        choice = Prompt.ask("[bold red]Seçiminiz[/]", choices=choice_options)
        
        if choice == 'q':
            console.print("[bold red]Sistem kapatılıyor. fsociety out.[/]")
            break
            
        elif choice == '1':
            query = Prompt.ask("[bold red]Müzik Ara[/]")
            if not query.strip():
                continue
                
            results = search_music(query)
            
            clear_screen()
            draw_header()
            
            if display_results(results):
                selection = IntPrompt.ask("[bold red]Listeye eklemek istediğin şarkının numarasını gir[/]", choices=[str(i) for i in range(1, len(results[:8]) + 1)])
                
                selected_song = results[selection - 1]
                video_id = selected_song['videoId']
                title = selected_song['title']
                artist = ", ".join([a['name'] for a in selected_song['artists']])
                duration = selected_song.get('duration', 'N/A')
                
                playlists_db[active_playlist_name].append({
                    "title": title,
                    "artist": artist,
                    "video_id": video_id,
                    "duration": duration
                })
                
                save_playlists()
                console.print(f"\n[bold green]✔ '{title} - {artist}' '{active_playlist_name}' listesine başarıyla eklendi ve kaydedildi![/]")
                time.sleep(1.5)
                
        elif choice == '2':
            url = Prompt.ask("[bold red]Spotify veya YouTube Oynatma Listesi Linkini Yapıştır[/]")
            if not url.strip():
                continue
            import_spotify_playlist(url)
                
        elif choice == '3':
            select_or_create_playlist()

        elif choice == '6':
            create_mood_playlist()
                
        elif choice == '4':
            if active_list:
                current_track_index = 0
                play_engine()
                
        elif choice == '5':
            playlists_db[active_playlist_name].clear()
            current_track_index = -1
            save_playlists()
            console.print(f"\n[bold red]🗑️ '{active_playlist_name}' listesi temizlendi.[/]")
            time.sleep(1)

        elif choice == '7':
            manage_track_list()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Uygulama kapatıldı. fsociety out.[/]")