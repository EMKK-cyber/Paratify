import sys
import json
import re
import threading
import html
import os
import random
import requests
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QListWidget, QProgressBar, QMessageBox, QDialog, 
                             QTextEdit, QListWidgetItem, QMenu, QFrame, QSlider,
                             QGraphicsOpacityEffect, QScrollArea, QAbstractItemView,
                             QSpinBox)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import (Qt, QSize, pyqtSignal, QObject, QPropertyAnimation,
                          QEasingCurve, QUrl, QThread, QTimer, QRectF)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# ----------------------------------------------------------------
# VERİTABANI DOSYASI
# ----------------------------------------------------------------
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlists.json")
ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist_icons.json")

DEFAULT_ICON = "🎵"
ICON_CHOICES = ["🎵", "🔥", "💚", "🎧", "⭐", "🌙", "🎤", "📀", "🎸", "🎹"]

# Tüm YTMusic aramaları için tek örnek (app.py ile aynı yaklaşım)
ytm = YTMusic()


def duration_to_seconds(duration_str):
    """'3:45' gibi bir metni saniyeye çevirir. Ayrıştıramazsa 0 döner."""
    try:
        parts = [int(p) for p in str(duration_str).split(":")]
        seconds = 0
        for p in parts:
            seconds = seconds * 60 + p
        return seconds
    except (ValueError, TypeError):
        return 0

# Sinyaller için yardımcı sınıf
class WorkerSignals(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

# ----------------------------------------------------------------
# 1. BYPASS DIALOG (Sihirli JS Kodu ve Adımlı Kılavuz)
# ----------------------------------------------------------------
SPOTIFY_JS_SCRAPE_CODE = """
(function() {
    let tracks = [];
    document.querySelectorAll('[data-testid="tracklist-row"]').forEach(row => {
        let titleEl = row.querySelector('a[href*="/track/"]');
        let artistEls = row.querySelectorAll('a[href*="/artist/"]');
        if (titleEl) {
            let title = titleEl.innerText;
            let artists = Array.from(artistEls).map(a => a.innerText).join(', ');
            tracks.push({title: title, artist: artists});
        }
    });
    if (tracks.length === 0) {
        alert("Hata: Şarkılar bulunamadı! Lütfen çalma listesi sayfasında olduğunuzdan emin olun.");
    } else {
        let jsonStr = JSON.stringify(tracks, null, 2);
        copy(jsonStr);
        alert(tracks.length + " adet şarkı başarıyla kopyalandı! Şimdi programa dönüp kutuya yapıştırabilirsiniz.");
        console.log(jsonStr);
    }
})();
"""

class BypassDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result_data = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Spotify Güvenlik Duvarı Bypass - Adımlı Rehber")
        self.setMinimumSize(550, 500)
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #e0e0e0; }
            QLabel { color: #e0e0e0; font-family: 'Segoe UI', Arial; }
            QTextEdit { 
                background-color: #1e1e1e; 
                color: #ffffff; 
                border: 1px solid #333; 
                border-radius: 6px; 
                padding: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)

        guide_label = QLabel()
        guide_label.setTextFormat(Qt.TextFormat.RichText)
        guide_label.setText(
            "<h2 style='color: #1DB954; margin-bottom: 5px;'>Spotify Engeline Takıldık!</h2>"
            "<p style='font-size: 13px;'>Hiç panik yapma, bu engeli aşmak sadece 30 saniyeni alacak. Aşağıdaki adımları sırayla takip et:</p>"
            "<ol style='font-size: 12px; line-height: 18px;'>"
            "   <li>Tarayıcından (Chrome, Edge vb.) <b>Spotify çalma listeni</b> aç.</li>"
            "   <li>Klavyenden <b>F12</b> tuşuna basıp (veya sağ tıklayıp İncele diyerek) <b>Console (Konsol)</b> sekmesine geç.</li>"
            "   <li>Aşağıdaki yeşil butona basarak sihirli kodumuzu kopyala, tarayıcı konsoluna yapıştır ve <b>Enter</b>'a bas.</li>"
            "   <li>Tarayıcının senin için kopyaladığı veriyi aşağıdaki metin alanına yapıştır!</li>"
            "</ol>"
        )
        guide_label.setWordWrap(True)
        layout.addWidget(guide_label)

        self.btn_copy_js = QPushButton("🔗 Tarayıcı İçin Sihirli Kodu Kopyala")
        self.btn_copy_js.setStyleSheet("""
            QPushButton {
                background-color: #1DB954; 
                color: white; 
                font-weight: bold; 
                border-radius: 8px; 
                padding: 10px;
                font-size: 13px;
                border: none;
            }
            QPushButton:hover { background-color: #1ed760; }
        """)
        self.btn_copy_js.clicked.connect(self.copy_javascript_to_clipboard)
        layout.addWidget(self.btn_copy_js)

        layout.addWidget(QLabel("<b>Elde ettiğin çıktıyı buraya yapıştır:</b>"))
        self.txt_input = QTextEdit()
        self.txt_input.setPlaceholderText('[{"title": "Şarkı Adı", "artist": "Sanatçı"}, ...]\nŞeklindeki veriyi buraya yapıştırın.')
        layout.addWidget(self.txt_input)

        btn_layout = QHBoxLayout()
        self.btn_confirm = QPushButton("Listeyi Senkronize Et")
        self.btn_confirm.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; font-weight: bold; padding: 10px; border-radius: 6px; border: none; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.btn_confirm.clicked.connect(self.accept_data)
        
        self.btn_cancel = QPushButton("İptal Et")
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: #333; color: white; padding: 10px; border-radius: 6px; border: none; }
            QPushButton:hover { background-color: #444; }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_confirm)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def copy_javascript_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(SPOTIFY_JS_SCRAPE_CODE)
        self.btn_copy_js.setText("✓ Kod Panoya Kopyalandı!")
        self.btn_copy_js.setStyleSheet("""
            QPushButton { background-color: #2ecc71; color: white; font-weight: bold; border-radius: 8px; padding: 10px; border: none;}
        """)
        QMessageBox.information(self, "Kod Kopyalandı", "Sihirli JS kodu panoya kopyalandı.\nŞimdi tarayıcı konsoluna gidip yapıştırabilirsin!")

    def accept_data(self):
        data = self.txt_input.toPlainText().strip()
        if not data:
            QMessageBox.warning(self, "Uyarı", "Lütfen tarayıcıdan aldığınız çıktıyı yapıştırın!")
            return
        self.result_data = data
        self.accept()


# ----------------------------------------------------------------
# 1C. TEKİL ŞARKI ARAMA (SearchWorker + SearchDialog)
# ----------------------------------------------------------------
class SearchWorker(QThread):
    finished_search = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            results = ytm.search(self.query, filter="songs")
            self.finished_search.emit(results[:15] if results else [])
        except Exception as e:
            self.error.emit(str(e))


class SearchDialog(QDialog):
    """Kullanıcının tekil bir şarkı arayıp aktif çalma listesine ekleyebildiği pencere."""
    track_added = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.setWindowTitle("➕ Şarkı Ara ve Ekle")
        self.setMinimumSize(480, 520)
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #e0e0e0; }
            QLabel { color: #e0e0e0; font-family: 'Segoe UI', Arial; }
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 8px;
                color: white;
            }
            QLineEdit:focus { border: 1px solid #1DB954; }
            QPushButton {
                background-color: #1DB954;
                color: black;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 14px;
                border: none;
            }
            QPushButton:hover { background-color: #1ed760; }
            QPushButton:disabled { background-color: #333; color: #777; }
            QListWidget {
                background-color: #1a1a1e;
                border: 1px solid #2a2a30;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin-bottom: 2px;
                color: #e0e0e0;
            }
            QListWidget::item:hover {
                background-color: #1DB954;
                color: black;
            }
        """)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Şarkı adı veya sanatçı yaz...")
        self.input.returnPressed.connect(self.do_search)
        self.btn_search = QPushButton("🔍 Ara")
        self.btn_search.clicked.connect(self.do_search)
        search_row.addWidget(self.input)
        search_row.addWidget(self.btn_search)
        layout.addLayout(search_row)

        self.status_label = QLabel("Aramak istediğin şarkıyı yaz ve Enter'a bas.")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self.on_result_clicked)
        layout.addWidget(self.results_list)

        self.btn_close = QPushButton("Kapat")
        self.btn_close.setStyleSheet("QPushButton { background-color: #333; color: white; } QPushButton:hover { background-color: #444; }")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)

    def do_search(self):
        query = self.input.text().strip()
        if not query:
            return

        self.btn_search.setEnabled(False)
        self.status_label.setText("🔎 Aranıyor...")
        self.results_list.clear()

        self.worker = SearchWorker(query)
        self.worker.finished_search.connect(self.on_results)
        self.worker.error.connect(self.on_search_error)
        self.worker.start()

    def on_results(self, results):
        self.btn_search.setEnabled(True)
        self.results_list.clear()

        if not results:
            self.status_label.setText("❌ Sonuç bulunamadı.")
            return

        for r in results:
            video_id = r.get("videoId")
            if not video_id:
                continue
            title = r.get("title", "Bilinmeyen Şarkı")
            artists = ", ".join([a["name"] for a in r.get("artists", [])])
            duration = r.get("duration", "N/A")
            item = QListWidgetItem(f"🎵  {title}  —  {artists}   ·   {duration}")
            item.setData(Qt.ItemDataRole.UserRole, {
                "title": title,
                "artist": artists,
                "video_id": video_id,
                "duration": duration
            })
            self.results_list.addItem(item)

        self.status_label.setText(f"✔ {self.results_list.count()} sonuç bulundu — eklemek için tıkla.")

    def on_search_error(self, message):
        self.btn_search.setEnabled(True)
        self.status_label.setText(f"❌ Arama hatası: {message}")

    def on_result_clicked(self, item):
        track = item.data(Qt.ItemDataRole.UserRole)
        if not track:
            return
        self.track_added.emit(track)
        self.status_label.setText(f"✔ '{track['title']}' listeye eklendi!")


# ----------------------------------------------------------------
# 1D. TERMİNAL-TARZI GÖRSEL ŞÖLEN (Simüle Edilmiş Bar Visualizer)
# ----------------------------------------------------------------
class VisualizerWidget(QWidget):
    """mpv/QtMultimedia'nın ham ses verisine erişimimiz olmadığı için, çalma durumuna
    duyarlı, göz alıcı bir 'sahte ama inandırıcı' bar animasyonu üretiyoruz."""

    def __init__(self, bars=32, parent=None):
        super().__init__(parent)
        self.num_bars = bars
        self.levels = [1] * bars
        self.active = False
        self.setFixedHeight(34)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start(self):
        self.active = True
        self.timer.start(90)

    def stop(self):
        self.active = False
        self.timer.stop()
        self.levels = [1] * self.num_bars
        self.update()

    def tick(self):
        for i in range(self.num_bars):
            delta = random.randint(-3, 4)
            self.levels[i] = max(1, min(10, self.levels[i] + delta))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        gap = 3
        bar_w = max(2.0, (w - gap * (self.num_bars - 1)) / self.num_bars)
        color = QColor("#1DB954") if self.active else QColor("#2a2a30")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        x = 0.0
        for lvl in self.levels:
            bar_h = h * (lvl / 10.0)
            painter.drawRoundedRect(QRectF(x, h - bar_h, bar_w, bar_h), 2, 2)
            x += bar_w + gap
        painter.end()


# ----------------------------------------------------------------
# 1E. MOOD / ANAHTAR KELİME OTOMATİK LİSTE (MoodWorker + MoodDialog)
# ----------------------------------------------------------------
class MoodWorker(QThread):
    finished_search = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            results = ytm.search(self.query, filter="songs")
            self.finished_search.emit(results[:25] if results else [])
        except Exception as e:
            self.error.emit(str(e))


class MoodDialog(QDialog):
    """Bir mood/anahtar kelimeye göre (ör. 'dark ambient', 'lo-fi for coding') otomatik liste oluşturur."""
    playlist_created = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.results = []
        self.setWindowTitle("🌙 Mood Listesi Oluştur")
        self.setMinimumSize(440, 260)
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
            QLineEdit, QSpinBox {
                background-color: #1e1e1e; border: 1px solid #333; border-radius: 6px;
                padding: 8px; color: white;
            }
            QLineEdit:focus, QSpinBox:focus { border: 1px solid #1DB954; }
            QPushButton {
                background-color: #1DB954; color: black; font-weight: bold;
                border-radius: 6px; padding: 8px 14px; border: none;
            }
            QPushButton:hover { background-color: #1ed760; }
            QPushButton:disabled { background-color: #333; color: #777; }
        """)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Mood / anahtar kelime</b> <span style='color:#888;'>(ör: dark ambient, cyberpunk, lo-fi for coding)</span>"))

        self.input = QLineEdit()
        self.input.setPlaceholderText("dark ambient...")
        self.input.returnPressed.connect(self.do_search)
        layout.addWidget(self.input)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Kaç şarkı eklensin?"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 25)
        self.count_spin.setValue(10)
        count_row.addWidget(self.count_spin)
        layout.addLayout(count_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.btn_create = QPushButton("🌙 Listeyi Oluştur")
        self.btn_create.clicked.connect(self.do_search)
        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.setStyleSheet("QPushButton { background-color: #333; color: white; } QPushButton:hover { background-color: #444; }")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_create)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    def do_search(self):
        query = self.input.text().strip()
        if not query:
            return
        self.btn_create.setEnabled(False)
        self.status_label.setText("🔎 Taranıyor...")
        self.worker = MoodWorker(query)
        self.worker.finished_search.connect(self.on_results)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_results(self, results):
        self.btn_create.setEnabled(True)
        if not results:
            self.status_label.setText("❌ Sonuç bulunamadı.")
            return

        count = min(self.count_spin.value(), len(results))
        tracks = []
        for item in results[:count]:
            video_id = item.get("videoId")
            if not video_id:
                continue
            tracks.append({
                "title": item.get("title", "Bilinmeyen Şarkı"),
                "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
                "video_id": video_id,
                "duration": item.get("duration", "N/A")
            })

        playlist_name = self.input.text().strip().title()
        self.playlist_created.emit(playlist_name, tracks)
        self.accept()

    def on_error(self, message):
        self.btn_create.setEnabled(True)
        self.status_label.setText(f"❌ Hata: {message}")


# ----------------------------------------------------------------
# 1F. SÖZLER (LYRICS) — LyricsWorker + LyricsDialog (Daktilo/Glitch Efekti)
# ----------------------------------------------------------------
GLITCH_CHARS = "!<>-_/{}=+*^?#$%&~"

class LyricsWorker(QThread):
    fetched = pyqtSignal(str)

    def __init__(self, video_id):
        super().__init__()
        self.video_id = video_id

    def run(self):
        try:
            watch_playlist = ytm.get_watch_playlist(self.video_id)
            browse_id = watch_playlist.get("lyrics")
            if not browse_id:
                self.fetched.emit("")
                return
            data = ytm.get_lyrics(browse_id)
            self.fetched.emit(data.get("lyrics", "") or "")
        except Exception:
            self.fetched.emit("")


class LyricsDialog(QDialog):
    """Çalan şarkının sözlerini YTMusic'in resmi (lisanslı) API'sinden çekip
    daktilo + 'brute-force decrypt' efektiyle gösterir."""

    def __init__(self, track, parent=None):
        super().__init__(parent)
        self.track = track
        self.full_lyrics = ""
        self.revealed = 0
        self.setWindowTitle(f"📜 Sözler — {track.get('title', '')}")
        self.setMinimumSize(460, 540)
        self.setStyleSheet("""
            QDialog { background-color: #0b0b0d; }
            QLabel { color: #eaeaea; }
            QScrollArea { border: none; background: transparent; }
            QPushButton {
                background-color: #1f1f24; border: 1px solid #2e2e38; border-radius: 6px;
                padding: 8px 14px; font-weight: bold; color: #ffffff;
            }
            QPushButton:hover { background-color: #2e2e38; border-color: #1DB954; }
        """)

        layout = QVBoxLayout(self)
        title = QLabel(
            f"<b style='color:#1DB954; font-size:15px;'>{html.escape(track.get('title', ''))}</b><br>"
            f"<span style='color:#888; font-size:11px;'>{html.escape(track.get('artist', ''))}</span>"
        )
        layout.addWidget(title)

        self.status_label = QLabel("🔎 Sözler aranıyor...")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.body_label = QLabel("")
        self.body_label.setTextFormat(Qt.TextFormat.RichText)
        self.body_label.setWordWrap(True)
        self.body_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body_label.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 13px;")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.body_label)
        layout.addWidget(scroll_area)

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

        self.worker = LyricsWorker(track.get("video_id", ""))
        self.worker.fetched.connect(self.on_fetched)
        self.worker.start()

    def on_fetched(self, lyrics):
        if not lyrics:
            self.status_label.setText("❌ Bu şarkı için söz bulunamadı.")
            return
        self.full_lyrics = lyrics
        self.status_label.setText("📜 decrypt() çalışıyor...")
        self.revealed = 0
        self.timer.start(15)

    def tick(self):
        if self.revealed >= len(self.full_lyrics):
            self.timer.stop()
            self.status_label.setText(f"✔ {html.escape(self.track.get('title', ''))}")
            self.body_label.setText(html.escape(self.full_lyrics).replace("\n", "<br>"))
            return
        self.revealed = min(len(self.full_lyrics), self.revealed + 3)
        shown = html.escape(self.full_lyrics[:self.revealed]).replace("\n", "<br>")
        glitch_len = min(8, len(self.full_lyrics) - self.revealed)
        glitch = "".join(random.choice(GLITCH_CHARS) for _ in range(glitch_len))
        self.body_label.setText(f"{shown}<span style='color:#ff3b3b;'>{glitch}</span>")

    def closeEvent(self, event):
        self.timer.stop()
        if self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(300)
        event.accept()


# ----------------------------------------------------------------
# 1B. STREAM RESOLVE WORKER (Şarkı Akış Adresini Arka Planda Çözer)
# ----------------------------------------------------------------
class StreamResolveWorker(QThread):
    resolved = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, video_id):
        super().__init__()
        self.video_id = video_id

    def run(self):
        ydl_opts = {
            # DASH/HLS parçalı akışlar yerine önce düz/progressive HTTPS akışı dene —
            # "Demuxing failed -5" hatasının en sık nedeni Google'ın parçalı akışı
            # ortasında kesmesi/throttle etmesi. Düz https bulunamazsa normale düş.
            'format': 'bestaudio[protocol=https]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 15,
        }
        video_url = f"https://www.youtube.com/watch?v={self.video_id}"
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                self.resolved.emit(info['url'])
        except Exception as e:
            self.failed.emit(str(e))


# ----------------------------------------------------------------
# 2. SYNC WORKER (Arka Planda Senkronizasyon İşçisi)
# ----------------------------------------------------------------
class SyncWorker(threading.Thread):
    def __init__(self, url, signals):
        super().__init__()
        self.url = url
        self.signals = signals
        self.daemon = True

    def run(self):
        playlist_id_match = re.search(r"playlist/([a-zA-Z0-9]+)", self.url)
        if not playlist_id_match:
            self.signals.error.emit("Geçersiz Spotify çalma listesi linki!")
            return

        playlist_id = playlist_id_match.group(1)
        entries = []
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            response = requests.get(embed_url, headers=headers, timeout=15)
            if response.status_code == 200:
                next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>', response.text)
                if next_data_match:
                    raw_json = html.unescape(next_data_match.group(1))
                    data = json.loads(raw_json)
                    tracks = data.get("props", {}).get("pageProps", {}).get("state", {}).get("playlist", {}).get("tracks", {}).get("items", [])
                    for item in tracks:
                        track_info = item.get("track", {})
                        title = track_info.get("name")
                        artists = [a.get("name") for a in track_info.get("artists", [])]
                        if title:
                            entries.append((title, ", ".join(artists)))
        except Exception as e:
            print(f"Hata: {e}")

        if not entries:
            self.signals.finished.emit([])
            return

        matched_tracks = []
        total = len(entries)
        for idx, (title, artist) in enumerate(entries):
            query = f"{title} {artist}".strip()
            try:
                search_results = ytm.search(query, filter="songs")
                if search_results:
                    best_match = search_results[0]
                    matched_tracks.append({
                        "title": best_match.get("title", title),
                        "artist": ", ".join([a["name"] for a in best_match.get("artists", [])]) or artist,
                        "video_id": best_match["videoId"],
                        "duration": best_match.get("duration", "N/A")
                    })
            except Exception as e:
                print(f"Eşleşme hatası ({query}): {e}")

            self.signals.progress.emit(idx + 1, total)

        self.signals.finished.emit(matched_tracks)


# ----------------------------------------------------------------
# 3. ANA UYGULAMA PENCERESİ (ParaotifyGUI)
# ----------------------------------------------------------------
class ParaotifyGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # Veritabanını RAM'e yükle (JSON dosyasından)
        self.load_database()
        self.load_icons()
        
        # Eğer liste boşsa varsayılan bir liste oluştur
        if not self.playlists_db:
            self.playlists_db = {"Favorilerim": []}
            self.playlist_icons.setdefault("Favorilerim", DEFAULT_ICON)
            
        self.active_playlist_name = list(self.playlists_db.keys())[0]
        
        self.is_playing = False
        self.current_duration = 225  # Şarkı yüklenene kadar varsayılan
        self.current_position = 0
        self.current_track_index = -1
        self.timer = None
        self.stream_worker = None
        self.retry_count = 0  # Akış hatalarında otomatik yeniden bağlanma sayacı

        # Gerçek ses çalma motoru
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.on_player_position_changed)
        self.player.durationChanged.connect(self.on_player_duration_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.player.errorOccurred.connect(self.on_player_error)

        self.init_ui()

    def load_database(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as file:
                    self.playlists_db = json.load(file)
            except Exception as e:
                print(f"Veritabanı okuma hatası: {e}")
                self.playlists_db = {}
        else:
            self.playlists_db = {}

    def save_database(self):
        try:
            with open(DB_FILE, "w", encoding="utf-8") as file:
                json.dump(self.playlists_db, file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Veritabanı kaydetme hatası: {e}")

    def load_icons(self):
        if os.path.exists(ICON_FILE):
            try:
                with open(ICON_FILE, "r", encoding="utf-8") as file:
                    self.playlist_icons = json.load(file)
                    return
            except Exception as e:
                print(f"Simge okuma hatası: {e}")
        self.playlist_icons = {}

    def save_icons(self):
        try:
            with open(ICON_FILE, "w", encoding="utf-8") as file:
                json.dump(self.playlist_icons, file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Simge kaydetme hatası: {e}")

    def create_emoji_icon(self, emoji, size=22):
        """Bir emojiden QListWidgetItem için kullanılabilir bir QIcon üretir (Spotify tarzı liste ikonu)."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont()
        font.setPointSize(int(size * 0.62))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
        painter.end()
        return QIcon(pixmap)

    def init_ui(self):
        self.setWindowTitle("Paraotify - Music Player & Sync")
        self.setMinimumSize(950, 600)
        
        # SİBER/KARANLIK STİL SAYFASI (Güzelleştirilmiş UI)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0c0c0e;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', Helvetica, Arial;
            }
            QFrame#left_panel {
                background-color: #131316;
                border-right: 1px solid #1f1f24;
            }
            QFrame#player_panel {
                background-color: #0c0c0e;
            }
            QListWidget {
                background-color: #18181c;
                border: 1px solid #232329;
                border-radius: 8px;
                padding: 5px;
                color: #ffffff;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListWidget::item:hover {
                background-color: #232329;
            }
            QListWidget::item:selected {
                background-color: #1DB954;
                color: black;
                font-weight: bold;
            }
            QListWidget#track_list::item {
                padding: 0px;
                margin-bottom: 3px;
                border-radius: 8px;
            }
            QListWidget#track_list::item:selected {
                background: transparent;
            }
            QListWidget#track_list::item:hover {
                background-color: #1c1c20;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #2e2e38;
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #1DB954;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QLineEdit {
                background-color: #18181c;
                border: 1px solid #282830;
                border-radius: 6px;
                padding: 8px;
                color: white;
            }
            QLineEdit:focus {
                border: 1px solid #1DB954;
            }
            QPushButton {
                background-color: #1f1f24;
                border: 1px solid #2e2e38;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: bold;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #2e2e38;
                border-color: #1DB954;
            }
            QPushButton#toggle_sidebar_btn {
                background-color: #1DB954;
                color: black;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#toggle_sidebar_btn:hover {
                background-color: #1ed760;
            }
            QPushButton#play_btn {
                background-color: #1DB954;
                color: black;
                font-size: 16px;
                border: none;
                border-radius: 20px;
                min-width: 40px;
                max-width: 40px;
                min-height: 40px;
                max-height: 40px;
            }
            QPushButton#play_btn:hover {
                background-color: #1ed760;
                border: 2px solid white;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #282828;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #1DB954;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #1ed760;
                width: 14px;
                height: 14px;
                border-radius: 7px;
            }
        """)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ----------------------------------------------------------------
        # 4. SOL PANEL (Kapatılabilir Çalma Listesi Bölümü)
        # ----------------------------------------------------------------
        self.left_panel = QFrame()
        self.left_panel.setObjectName("left_panel")
        self.left_panel.setMaximumWidth(240)
        self.left_panel_layout = QVBoxLayout(self.left_panel)
        self.left_panel_layout.setContentsMargins(15, 15, 15, 15)
        self.left_panel_layout.setSpacing(10)

        self.left_panel_layout.addWidget(QLabel("<b style='font-size: 14px; color: #1DB954;'>ÇALMA LİSTELERİM</b>"))
        
        self.playlist_list = QListWidget()
        self.playlist_list.setIconSize(QSize(20, 20))
        self.playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self.show_playlist_context_menu)
        self.refresh_playlist_sidebar()
        self.playlist_list.currentItemChanged.connect(self.on_playlist_item_changed)
        self.playlist_list.itemChanged.connect(self.on_playlist_renamed)
        self.left_panel_layout.addWidget(self.playlist_list)

        self.left_panel_layout.addWidget(QLabel("<b>Yeni Çalma Listesi:</b>"))
        self.new_playlist_input = QLineEdit()
        self.new_playlist_input.setPlaceholderText("Liste adı girin...")
        self.left_panel_layout.addWidget(self.new_playlist_input)
        
        self.btn_add_playlist = QPushButton("＋ Liste Oluştur")
        self.btn_add_playlist.clicked.connect(self.create_playlist)
        self.left_panel_layout.addWidget(self.btn_add_playlist)

        self.left_panel_layout.addWidget(QLabel("<span style='font-size: 11px; color: #555;'>Çift tıkla yeniden adlandır, sağ tıkla simge değiştir/sil.</span>"))

        main_layout.addWidget(self.left_panel)

        # ----------------------------------------------------------------
        # 5. SAĞ PANEL (Ana Oynatıcı, Şarkı Listesi ve İlerleme Barı)
        # ----------------------------------------------------------------
        self.right_panel = QFrame()
        self.right_panel.setObjectName("player_panel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(20, 15, 20, 20)
        right_layout.setSpacing(15)

        top_bar_layout = QHBoxLayout()
        
        self.btn_toggle_sidebar = QPushButton("☰")
        self.btn_toggle_sidebar.setObjectName("toggle_sidebar_btn")
        self.btn_toggle_sidebar.setToolTip("Paneli Göster / Gizle")
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        top_bar_layout.addWidget(self.btn_toggle_sidebar)

        self.link_input = QLineEdit()
        self.link_input.setPlaceholderText("Spotify Çalma Listesi Linkini Buraya Yapıştırın...")
        top_bar_layout.addWidget(self.link_input)

        self.btn_sync = QPushButton("⚡ Senkronize Et")
        self.btn_sync.clicked.connect(self.start_sync)
        top_bar_layout.addWidget(self.btn_sync)

        self.btn_search_add = QPushButton("➕ Şarkı Ara")
        self.btn_search_add.setToolTip("Tekil bir şarkı arayıp aktif listeye ekle")
        self.btn_search_add.clicked.connect(self.open_search_dialog)
        top_bar_layout.addWidget(self.btn_search_add)

        self.btn_mood = QPushButton("🌙 Mood Listesi")
        self.btn_mood.setToolTip("Anahtar kelimeye göre otomatik liste oluştur")
        self.btn_mood.clicked.connect(self.open_mood_dialog)
        top_bar_layout.addWidget(self.btn_mood)

        self.btn_panic = QPushButton("⛔")
        self.btn_panic.setFixedWidth(40)
        self.btn_panic.setToolTip("Kill Switch (Esc) — müziği anında durdurur")
        self.btn_panic.setStyleSheet("""
            QPushButton { background-color: #2a1010; border: 1px solid #ff3b3b; color: #ff3b3b; }
            QPushButton:hover { background-color: #ff3b3b; color: black; }
        """)
        self.btn_panic.clicked.connect(self.trigger_kill_switch)
        top_bar_layout.addWidget(self.btn_panic)
        
        right_layout.addLayout(top_bar_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #222; border-radius: 4px; text-align: center; height: 15px; }
            QProgressBar::chunk { background-color: #1DB954; }
        """)
        right_layout.addWidget(self.progress_bar)

        self.lbl_playlist_title = QLabel(f"<b style='font-size: 18px;'>{self.playlist_icons.get(self.active_playlist_name, DEFAULT_ICON)} {self.active_playlist_name}</b>")
        right_layout.addWidget(self.lbl_playlist_title)

        self.track_list = QListWidget()
        self.track_list.setObjectName("track_list")
        self.track_list.itemClicked.connect(self.on_track_clicked)
        self.track_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.track_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.track_list.model().rowsMoved.connect(self.on_tracks_reordered)
        self.track_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_list.customContextMenuRequested.connect(self.show_track_context_menu)
        self.track_list.setToolTip("Sürükle-bırak ile sırala, sağ tıkla sil/favorile")
        self.track_list_opacity = QGraphicsOpacityEffect(self.track_list)
        self.track_list_opacity.setOpacity(1.0)
        self.track_list.setGraphicsEffect(self.track_list_opacity)
        right_layout.addWidget(self.track_list)

        # ----------------------------------------------------------------
        # 6. MEDYA OYNATICI VE İLERLETME BARI
        # ----------------------------------------------------------------
        self.player_controls_frame = QFrame()
        self.player_controls_frame.setStyleSheet("""
            QFrame {
                background-color: #131316;
                border-radius: 12px;
                padding: 12px;
                border: 1px solid #1f1f24;
            }
        """)
        player_layout = QVBoxLayout(self.player_controls_frame)
        player_layout.setSpacing(8)

        self.lbl_current_track = QLabel("<span style='font-size: 14px; font-weight: bold; color: #ffffff;'>Şarkı Çalınmıyor</span>")
        self.lbl_current_artist = QLabel("<span style='font-size: 11px; color: #888;'>Sanatçı</span>")
        player_layout.addWidget(self.lbl_current_track)
        player_layout.addWidget(self.lbl_current_artist)

        self.visualizer = VisualizerWidget()
        player_layout.addWidget(self.visualizer)

        slider_layout = QHBoxLayout()
        self.lbl_time_current = QLabel("0:00")
        self.lbl_time_current.setStyleSheet("font-size: 11px; color: #888; border: none;")
        
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, self.current_duration)
        self.time_slider.setValue(0)
        self.time_slider.sliderMoved.connect(self.on_slider_moved)
        self.time_slider.sliderReleased.connect(self.on_slider_released)

        self.lbl_time_total = QLabel("3:45")
        self.lbl_time_total.setStyleSheet("font-size: 11px; color: #888; border: none;")

        slider_layout.addWidget(self.lbl_time_current)
        slider_layout.addWidget(self.time_slider)
        slider_layout.addWidget(self.lbl_time_total)
        player_layout.addLayout(slider_layout)

        buttons_layout = QHBoxLayout()
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setStyleSheet("border: none; font-size: 20px; color: #888;")
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.clicked.connect(self.play_previous_track)
        
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("play_btn")
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_next = QPushButton("⏭")
        self.btn_next.setStyleSheet("border: none; font-size: 20px; color: #888;")
        self.btn_next.setFixedWidth(40)
        self.btn_next.clicked.connect(self.play_next_track)

        buttons_layout.addWidget(self.btn_prev)
        buttons_layout.addWidget(self.btn_play)
        buttons_layout.addWidget(self.btn_next)

        self.btn_lyrics = QPushButton("📜")
        self.btn_lyrics.setFixedWidth(40)
        self.btn_lyrics.setToolTip("Çalan şarkının sözlerini göster")
        self.btn_lyrics.setStyleSheet("border: none; font-size: 16px; color: #888;")
        self.btn_lyrics.clicked.connect(self.open_lyrics_dialog)
        buttons_layout.addWidget(self.btn_lyrics)
        player_layout.addLayout(buttons_layout)

        right_layout.addWidget(self.player_controls_frame)

        main_layout.addWidget(self.right_panel)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.refresh_track_list()

    # ----------------------------------------------------------------
    # 7. FONKSİYONLAR & ETKİLEŞİM YÖNETİMİ
    # ----------------------------------------------------------------
    
    def toggle_sidebar(self):
        target_width = 0 if self.left_panel.maximumWidth() > 0 else 240

        self.sidebar_anim = QPropertyAnimation(self.left_panel, b"maximumWidth")
        self.sidebar_anim.setDuration(220)
        self.sidebar_anim.setStartValue(self.left_panel.maximumWidth())
        self.sidebar_anim.setEndValue(target_width)
        self.sidebar_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.sidebar_anim.start()

        if target_width == 0:
            self.btn_toggle_sidebar.setText("☰")
            self.btn_toggle_sidebar.setToolTip("Paneli Göster")
        else:
            self.btn_toggle_sidebar.setText("✕")
            self.btn_toggle_sidebar.setToolTip("Paneli Gizle")

    def refresh_playlist_sidebar(self):
        """Sol paneldeki liste widget'ını playlists_db + playlist_icons'a göre yeniden çizer."""
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        for name in self.playlists_db.keys():
            item = QListWidgetItem(name)
            item.setIcon(self.create_emoji_icon(self.playlist_icons.get(name, DEFAULT_ICON)))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.playlist_list.addItem(item)

            if name == getattr(self, "active_playlist_name", None):
                self.playlist_list.setCurrentItem(item)

        if self.playlist_list.currentRow() < 0 and self.playlist_list.count() > 0:
            self.playlist_list.setCurrentRow(0)
        self.playlist_list.blockSignals(False)

    def create_playlist(self):
        name = self.new_playlist_input.text().strip()
        if not name:
            return
        if name in self.playlists_db:
            QMessageBox.warning(self, "Hata", "Bu isimde bir liste zaten mevcut!")
            return
        self.playlists_db[name] = []
        self.playlist_icons[name] = DEFAULT_ICON
        self.refresh_playlist_sidebar()
        self.new_playlist_input.clear()
        self.save_database()  # Yeni liste oluştuğunda hemen kaydet
        self.save_icons()

    def on_playlist_item_changed(self, current_item, previous_item):
        if current_item is None:
            return
        playlist_name = current_item.data(Qt.ItemDataRole.UserRole)
        if playlist_name:
            self.active_playlist_name = playlist_name
            icon = self.playlist_icons.get(playlist_name, DEFAULT_ICON)
            self.lbl_playlist_title.setText(f"<b style='font-size: 18px;'>{icon} {playlist_name}</b>")
            self.refresh_track_list()

    def on_playlist_renamed(self, item):
        old_name = item.data(Qt.ItemDataRole.UserRole)
        new_name = item.text().strip()

        if old_name is None:
            return

        if new_name == old_name:
            return

        if not new_name or new_name in self.playlists_db:
            QMessageBox.warning(self, "Hata", "Geçersiz veya zaten kullanılan bir liste adı!")
            self.playlist_list.blockSignals(True)
            item.setText(old_name)
            self.playlist_list.blockSignals(False)
            return

        # Sıralamayı koruyarak sözlük anahtarını yeniden adlandır
        new_db = {}
        for key, value in self.playlists_db.items():
            new_db[new_name if key == old_name else key] = value
        self.playlists_db = new_db

        if old_name in self.playlist_icons:
            self.playlist_icons[new_name] = self.playlist_icons.pop(old_name)

        if self.active_playlist_name == old_name:
            self.active_playlist_name = new_name
            icon = self.playlist_icons.get(new_name, DEFAULT_ICON)
            self.lbl_playlist_title.setText(f"<b style='font-size: 18px;'>{icon} {new_name}</b>")

        self.playlist_list.blockSignals(True)
        item.setData(Qt.ItemDataRole.UserRole, new_name)
        self.playlist_list.blockSignals(False)

        self.save_database()
        self.save_icons()

    def show_playlist_context_menu(self, position):
        item = self.playlist_list.itemAt(position)
        if item is None:
            return

        menu = QMenu(self)
        action_rename = menu.addAction("✏️ Yeniden Adlandır")
        icon_menu = menu.addMenu("🎨 Simge Değiştir")
        icon_actions = {}
        for emoji in ICON_CHOICES:
            act = icon_menu.addAction(emoji)
            icon_actions[act] = emoji
        menu.addSeparator()
        action_delete = menu.addAction("🗑️ Sil")

        chosen = menu.exec(self.playlist_list.mapToGlobal(position))
        if chosen is None:
            return

        if chosen == action_rename:
            self.playlist_list.editItem(item)
        elif chosen == action_delete:
            self.delete_playlist(item)
        elif chosen in icon_actions:
            self.change_playlist_icon(item, icon_actions[chosen])

    def change_playlist_icon(self, item, emoji):
        name = item.data(Qt.ItemDataRole.UserRole)
        self.playlist_icons[name] = emoji
        self.playlist_list.blockSignals(True)
        item.setIcon(self.create_emoji_icon(emoji))
        self.playlist_list.blockSignals(False)
        self.save_icons()

    def delete_playlist(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        if len(self.playlists_db) <= 1:
            QMessageBox.warning(self, "Hata", "Son kalan çalma listesini silemezsiniz!")
            return

        confirm = QMessageBox.question(
            self, "Listeyi Sil", f"'{name}' çalma listesini silmek istediğinizden emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        del self.playlists_db[name]
        self.playlist_icons.pop(name, None)

        if self.active_playlist_name == name:
            self.active_playlist_name = list(self.playlists_db.keys())[0]

        self.save_database()
        self.save_icons()
        self.refresh_playlist_sidebar()
        self.refresh_track_list()

    def build_track_row_widget(self, index, track, is_playing):
        """Spotify tarzı bir şarkı satırı: [# / ▶] [Başlık + Sanatçı] .......... [Süre]"""
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 12, 6)
        layout.setSpacing(12)

        marker = QLabel("▶" if is_playing else str(index + 1))
        marker.setFixedWidth(22)
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setStyleSheet(
            f"color: {'#1DB954' if is_playing else '#777'}; font-weight: bold; "
            f"font-size: 12px; border: none; background: transparent;"
        )
        layout.addWidget(marker)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title_color = "#1DB954" if is_playing else "#ffffff"
        title_label = QLabel(track.get("title", "Bilinmeyen Şarkı"))
        title_label.setStyleSheet(f"color: {title_color}; font-weight: 600; font-size: 13px; border: none; background: transparent;")
        subtitle_label = QLabel(track.get("artist", ""))
        subtitle_label.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        layout.addLayout(text_box, 1)

        duration_label = QLabel(str(track.get("duration", "")))
        duration_label.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(duration_label)

        if is_playing:
            row.setStyleSheet("background-color: rgba(29, 185, 84, 0.14); border-radius: 8px;")
        else:
            row.setStyleSheet("background: transparent;")

        return row

    def refresh_track_list(self):
        self.track_list.clear()
        tracks = self.playlists_db.get(self.active_playlist_name, [])
        for idx, t in enumerate(tracks):
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(0, 54))
            list_item.setData(Qt.ItemDataRole.UserRole, t)
            self.track_list.addItem(list_item)
            row_widget = self.build_track_row_widget(idx, t, idx == self.current_track_index)
            self.track_list.setItemWidget(list_item, row_widget)
        self.animate_track_list_fade()

    def animate_track_list_fade(self):
        self.track_fade_anim = QPropertyAnimation(self.track_list_opacity, b"opacity")
        self.track_fade_anim.setDuration(220)
        self.track_fade_anim.setStartValue(0.0)
        self.track_fade_anim.setEndValue(1.0)
        self.track_fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.track_fade_anim.start()

    def toggle_play(self):
        active_list = self.playlists_db.get(self.active_playlist_name, [])
        if not active_list:
            QMessageBox.warning(self, "Hata", "Bu çalma listesinde henüz şarkı yok!")
            return

        # Henüz hiçbir şarkı yüklenmediyse listenin başından başlat
        if self.current_track_index == -1:
            self.play_track_at(0)
            return

        if self.is_playing:
            self.player.pause()
            self.is_playing = False
            self.btn_play.setText("▶")
        else:
            self.player.play()
            self.is_playing = True
            self.btn_play.setText("⏸")

    def on_track_clicked(self, item):
        index = self.track_list.row(item)
        self.play_track_at(index)

    def play_previous_track(self):
        if self.current_track_index > 0:
            self.play_track_at(self.current_track_index - 1)

    def play_next_track(self):
        active_list = self.playlists_db.get(self.active_playlist_name, [])
        if self.current_track_index + 1 < len(active_list):
            self.play_track_at(self.current_track_index + 1)

    def play_track_at(self, index):
        active_list = self.playlists_db.get(self.active_playlist_name, [])
        if not (0 <= index < len(active_list)):
            return

        track = active_list[index]
        video_id = track.get("video_id", "")
        if not video_id or video_id.startswith("manual_id_") or video_id.startswith("dummy_id_"):
            QMessageBox.warning(self, "Hata", "Bu şarkı için gerçek bir YouTube eşleşmesi bulunamadı, çalınamıyor.")
            return

        self.current_track_index = index
        self.retry_count = 0
        self.player.stop()
        self.is_playing = False
        self.btn_play.setText("▶")

        self.lbl_current_track.setText(f"<span style='font-size: 14px; font-weight: bold; color: #1DB954;'>{track['title']}</span>")
        self.lbl_current_artist.setText(f"<span style='font-size: 11px; color: #888;'>{track['artist']}</span>")
        self.current_duration = duration_to_seconds(track.get("duration", 0)) or 225
        self.time_slider.setRange(0, self.current_duration)
        self.lbl_time_total.setText(track.get("duration", "0:00"))
        self.refresh_track_list()  # Çalan satırı yeşille vurgula

        # Akış adresini arka planda çöz (UI'yi kilitlememek için)
        self.btn_play.setEnabled(False)
        self.stream_worker = StreamResolveWorker(video_id)
        self.stream_worker.resolved.connect(self.on_stream_resolved)
        self.stream_worker.failed.connect(self.on_stream_failed)
        self.stream_worker.start()

    def on_stream_resolved(self, stream_url):
        self.retry_count = 0
        self.btn_play.setEnabled(True)
        self.player.setSource(QUrl(stream_url))
        self.player.play()
        self.is_playing = True
        self.btn_play.setText("⏸")

    def on_stream_failed(self, error_message):
        self.btn_play.setEnabled(True)
        QMessageBox.critical(self, "Akış Hatası", f"Şarkı çözümlenemedi: {error_message}")

    def on_player_error(self, error, error_string):
        """YouTube akış linkleri kısa ömürlü olduğu için çalma sırasında ('Demuxing
        failed -5 I/O hatası' gibi) bağlantı kopabiliyor. Burada linki otomatik olarak
        yeniden çözüp kaldığı yerden devam ettirmeyi deniyoruz."""
        if error == QMediaPlayer.Error.NoError:
            return
        if self.current_track_index == -1:
            return

        active_list = self.playlists_db.get(self.active_playlist_name, [])
        if not (0 <= self.current_track_index < len(active_list)):
            return

        if self.retry_count < 2:
            self.retry_count += 1
            self._resume_position_after_retry = self.current_position
            video_id = active_list[self.current_track_index].get("video_id")
            if not video_id:
                return

            self.lbl_current_artist.setText(
                f"<span style='font-size: 11px; color: #f39c12;'>⚠ Bağlantı koptu, yeniden bağlanılıyor... ({self.retry_count}/2)</span>"
            )
            self.stream_worker = StreamResolveWorker(video_id)
            self.stream_worker.resolved.connect(self.on_stream_resolved_after_retry)
            self.stream_worker.failed.connect(self.on_stream_failed)
            self.stream_worker.start()
        else:
            self.retry_count = 0
            QMessageBox.warning(
                self, "Akış Hatası",
                f"Şarkı çalınamadı ({error_string}). Sıradaki şarkıya geçiliyor."
            )
            self.play_next_track()

    def on_stream_resolved_after_retry(self, stream_url):
        self.player.setSource(QUrl(stream_url))
        self.player.play()
        resume_pos = getattr(self, "_resume_position_after_retry", 0)
        if resume_pos > 0:
            self.player.setPosition(resume_pos * 1000)
        self.is_playing = True
        self.btn_play.setText("⏸")
        track = self.playlists_db.get(self.active_playlist_name, [])[self.current_track_index]
        self.lbl_current_artist.setText(f"<span style='font-size: 11px; color: #888;'>{track['artist']}</span>")

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.visualizer.start()
        else:
            self.visualizer.stop()

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.play_next_track()

    def on_player_position_changed(self, position_ms):
        position = position_ms // 1000
        self.current_position = position
        if not self.time_slider.isSliderDown():
            self.time_slider.setValue(position)
        minutes = position // 60
        seconds = position % 60
        self.lbl_time_current.setText(f"{minutes}:{seconds:02d}")

    def on_player_duration_changed(self, duration_ms):
        if duration_ms > 0:
            self.current_duration = duration_ms // 1000
            self.time_slider.setRange(0, self.current_duration)

    def on_slider_moved(self, value):
        minutes = value // 60
        seconds = value % 60
        self.lbl_time_current.setText(f"{minutes}:{seconds:02d}")

    def on_slider_released(self):
        self.current_position = self.time_slider.value()
        self.player.setPosition(self.current_position * 1000)

    def open_search_dialog(self):
        dialog = SearchDialog(self)
        dialog.track_added.connect(self.add_track_to_active_playlist)
        dialog.exec()

    def add_track_to_active_playlist(self, track):
        self.playlists_db[self.active_playlist_name].append(track)
        self.save_database()
        self.refresh_track_list()

    def open_mood_dialog(self):
        dialog = MoodDialog(self)
        dialog.playlist_created.connect(self.add_mood_playlist)
        dialog.exec()

    def add_mood_playlist(self, name, tracks):
        if not name:
            name = "Mood Listesi"
        original_name = name
        suffix = 2
        while name in self.playlists_db:
            name = f"{original_name} ({suffix})"
            suffix += 1

        self.playlists_db[name] = tracks
        self.playlist_icons[name] = "🌙"
        self.active_playlist_name = name
        self.save_database()
        self.save_icons()
        self.refresh_playlist_sidebar()
        self.lbl_playlist_title.setText(f"<b style='font-size: 18px;'>🌙 {name}</b>")
        self.refresh_track_list()
        QMessageBox.information(self, "Başarılı", f"'{name}' listesi {len(tracks)} şarkıyla oluşturuldu!")

    def open_lyrics_dialog(self):
        active_list = self.playlists_db.get(self.active_playlist_name, [])
        if not (0 <= self.current_track_index < len(active_list)):
            QMessageBox.information(self, "Bilgi", "Önce bir şarkı çalman gerekiyor.")
            return
        track = active_list[self.current_track_index]
        dialog = LyricsDialog(track, self)
        dialog.exec()

    def trigger_kill_switch(self):
        """Panik butonu / Esc — müziği anında keser ve 'CONNECTION LOST' efekti gösterir."""
        self.player.stop()
        self.is_playing = False
        self.btn_play.setText("▶")
        self.visualizer.stop()

        central = self.centralWidget()
        overlay = QLabel("⚠  CONNECTION LOST  ⚠", central)
        overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay.setStyleSheet("""
            background-color: rgba(8, 0, 0, 235);
            color: #ff3b3b;
            font-size: 26px;
            font-weight: bold;
            letter-spacing: 2px;
        """)
        overlay.setGeometry(central.rect())
        overlay.show()
        overlay.raise_()

        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        effect.setOpacity(1.0)

        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(1500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(overlay.deleteLater)
        self._killswitch_overlay = overlay
        self._killswitch_anim = anim
        anim.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.trigger_kill_switch()
        else:
            super().keyPressEvent(event)

    def on_tracks_reordered(self, *args):
        """Kullanıcı bir şarkıyı sürükle-bırakla taşıdığında playlists_db'yi yeni sıraya göre günceller."""
        active_list = self.playlists_db.get(self.active_playlist_name, [])
        playing_video_id = None
        if 0 <= self.current_track_index < len(active_list):
            playing_video_id = active_list[self.current_track_index].get("video_id")

        new_order = []
        for i in range(self.track_list.count()):
            item = self.track_list.item(i)
            track_data = item.data(Qt.ItemDataRole.UserRole)
            if track_data:
                new_order.append(track_data)

        if len(new_order) != len(active_list):
            return  # beklenmedik bir durum, dokunma

        self.playlists_db[self.active_playlist_name] = new_order

        if playing_video_id:
            for i, t in enumerate(new_order):
                if t.get("video_id") == playing_video_id:
                    self.current_track_index = i
                    break

        self.save_database()
        self.refresh_track_list()

    def show_track_context_menu(self, position):
        item = self.track_list.itemAt(position)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if not track:
            return

        menu = QMenu(self)
        action_favorite = menu.addAction("⭐ Favorilere Ekle")
        action_delete = menu.addAction("🗑️ Listeden Sil")
        chosen = menu.exec(self.track_list.mapToGlobal(position))

        if chosen == action_favorite:
            self.add_track_to_favorites(track)
        elif chosen == action_delete:
            self.delete_track(item, track)

    def add_track_to_favorites(self, track):
        if "Favoriler" not in self.playlists_db:
            self.playlists_db["Favoriler"] = []
            self.playlist_icons["Favoriler"] = "⭐"
            self.refresh_playlist_sidebar()
            self.save_icons()

        already = any(t.get("video_id") == track.get("video_id") for t in self.playlists_db["Favoriler"])
        if already:
            QMessageBox.information(self, "Bilgi", "Bu şarkı zaten favorilerde.")
            return

        self.playlists_db["Favoriler"].append(track)
        self.save_database()
        QMessageBox.information(self, "Başarılı", f"'{track['title']}' favorilere eklendi!")

    def delete_track(self, item, track):
        active_list = self.playlists_db.get(self.active_playlist_name, [])
        row = self.track_list.row(item)
        if not (0 <= row < len(active_list)):
            return

        del active_list[row]

        if self.current_track_index == row:
            self.player.stop()
            self.is_playing = False
            self.btn_play.setText("▶")
            self.current_track_index = -1
        elif self.current_track_index > row:
            self.current_track_index -= 1

        self.save_database()
        self.refresh_track_list()

    def start_sync(self):
        url = self.link_input.text().strip()
        if not url:
            return

        self.btn_sync.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.signals = WorkerSignals()
        self.signals.progress.connect(self.on_sync_progress)
        self.signals.finished.connect(self.on_sync_finished)
        self.signals.error.connect(self.on_sync_error)

        self.worker = SyncWorker(url, self.signals)
        self.worker.start()

    def on_sync_progress(self, current, total):
        val = int((current / total) * 100)
        self.progress_bar.setValue(val)

    def on_sync_error(self, err_msg):
        self.progress_bar.setVisible(False)
        self.btn_sync.setEnabled(True)
        QMessageBox.critical(self, "Hata", err_msg)

    def on_sync_finished(self, tracks):
        self.progress_bar.setVisible(False)
        self.btn_sync.setEnabled(True)

        if not tracks:
            dialog = BypassDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                raw_json = dialog.result_data
                try:
                    json_clean_match = re.search(r"(\[.*\])", raw_json, re.DOTALL)
                    if json_clean_match:
                        raw_json = json_clean_match.group(1)
                    
                    data = json.loads(raw_json)
                    entries = []
                    for item in data:
                        title = item.get("title")
                        artist = item.get("artist", "")
                        if title:
                            entries.append((title, artist))
                    
                    if entries:
                        self.process_bypass_entries(entries)
                except Exception as e:
                    QMessageBox.critical(self, "Hata", f"JSON işlenirken hata oluştu: {e}")
            return

        self.playlists_db[self.active_playlist_name].extend(tracks)
        self.save_database() # Şarkı eklendiğinde kaydet
        self.refresh_track_list()
        self.link_input.clear()
        QMessageBox.information(self, "Başarılı", f"{len(tracks)} adet şarkı başarıyla eklendi!")

    def process_bypass_entries(self, entries):
        matched = []
        for title, artist in entries:
            query = f"{title} {artist}".strip()
            try:
                search_results = ytm.search(query, filter="songs")
                if search_results:
                    best_match = search_results[0]
                    matched.append({
                        "title": best_match.get("title", title),
                        "artist": ", ".join([a["name"] for a in best_match.get("artists", [])]) or artist,
                        "video_id": best_match["videoId"],
                        "duration": best_match.get("duration", "N/A")
                    })
            except Exception as e:
                print(f"Eşleşme hatası ({query}): {e}")

        self.playlists_db[self.active_playlist_name].extend(matched)
        self.save_database() # Manuel bypass sonrası listeyi kaydet
        self.refresh_track_list()
        QMessageBox.information(self, "Başarılı", f"{len(matched)} adet şarkı manuel olarak başarıyla eklendi!")

    # UYGULAMA KAPATILDIĞINDA TETİKLENEN ÇIKIŞ FONKSİYONU
    def closeEvent(self, event):
        # 1. Değişiklikleri son kez veritabanına yaz
        self.save_database()

        # 2. Çalan varsa ses motorunu ve görselleştiriciyi durdur
        self.player.stop()
        self.visualizer.stop()

        # 3. Devam eden arka plan işçilerini bekletmeden bitir (daemon thread'ler zaten süreci kilitlemez)
        if self.stream_worker and self.stream_worker.isRunning():
            self.stream_worker.terminate()
            self.stream_worker.wait(500)

        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParaotifyGUI()
    window.show()
    sys.exit(app.exec())