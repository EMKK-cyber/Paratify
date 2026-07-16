# Paraotify

Reklamsız, kendi barındırdığın bir müzik çalar. Spotify çalma listelerini YouTube
Music üzerinden bulup çalar. İki arayüzü var:

- **`app.py`** — Terminal (CLI) sürümü, `mpv` ile çalar, canlı görselleştirici ve
  "hacker" temalı ekstralar (Kill Switch, şarkı sözü decrypt efekti) içerir.
- **`paraotify_gui.py`** — PyQt6 masaüstü arayüzü, dahili ses motoruyla çalar.

İkisi de aynı `playlists.json` dosyasını paylaşır, birinde eklediğin şarkı diğerinde de görünür.

---

## 0. Python bilmiyorum, sadece uygulamayı indirmek istiyorum

Kod yazmana/Python kurmana gerek yok. **[Releases](../../releases)** sayfasından
işletim sistemine uygun hazır dosyayı indir:

| İşletim Sistemi | İndirilecek dosya |
|---|---|
| Windows | `Paraotify.exe` (çift tıkla çalıştır) |
| macOS | `Paraotify-macOS.zip` → içini çıkar → `Paraotify.app`'i çalıştır |
| Linux | `Paraotify-x86_64.AppImage` → `chmod +x` yapıp çift tıkla |

> **macOS notu:** Uygulama imzasız olduğu için ilk açılışta Gatekeeper uyarı verebilir.
> Finder'da uygulamaya **sağ tık → Aç** diyerek bu uyarıyı bir kereliğine aşabilirsin.
>
> **Linux notu:** AppImage'ı çalıştırılabilir yapmak için terminalde
> `chmod +x Paraotify-x86_64.AppImage` çalıştırman gerekebilir.
>
> Bu dosyalar depoya her `v1.0.0` gibi bir **tag/release** atıldığında GitHub'ın
> kendi sunucularında otomatik olarak derlenir (bkz. `.github/workflows/build.yml`).
> Henüz bir Release yoksa, aşağıdaki "Kaynak koddan çalıştırma" bölümünü izleyebilir
> ya da Actions sekmesinden workflow'u elle tetikleyip derlemeleri indirebilirsin.

---

## 1. Gereksinimler (kaynak koddan çalıştırmak/geliştirmek için)

- **Python 3.9+** (hepsi test edilebilir sürümler için 3.10+ önerilir)
- **pip**
- CLI için ek olarak: **mpv** (medya oynatıcı)

## 2. Kurulum

Önce depoyu klonla ve sanal ortam (virtual environment) oluştur — bu adım Windows,
macOS ve Linux'ta aynıdır:

```bash
git clone <repo-url>
cd paraotify

python3 -m venv venv          # Windows'ta: python -m venv venv
```

### Sanal ortamı aktive et

| İşletim Sistemi | Komut |
|---|---|
| Windows (PowerShell) | `venv\Scripts\Activate.ps1` |
| Windows (cmd.exe) | `venv\Scripts\activate.bat` |
| macOS / Linux | `source venv/bin/activate` |

### Python bağımlılıklarını kur

```bash
pip install -r requirements.txt
```

### `mpv` kur (sadece CLI/`app.py` için gerekli)

| İşletim Sistemi | Komut |
|---|---|
| macOS | `brew install mpv` |
| Ubuntu / Debian | `sudo apt install mpv` |
| Fedora | `sudo dnf install mpv` |
| Arch | `sudo pacman -S mpv` |
| Windows | `choco install mpv` veya `winget install mpv.io.mpv` (veya [mpv.io](https://mpv.io/installation/) üzerinden manuel indir ve PATH'e ekle) |

> GUI sürümü (`paraotify_gui.py`) `mpv` gerektirmez, sesi doğrudan Qt'nin kendi
> ses motoruyla (`QtMultimedia`) çalar.

## 3. Çalıştırma

```bash
# CLI (terminal) sürümü
python app.py

# GUI (masaüstü) sürümü
python paraotify_gui.py
```

> Windows'ta bazen `python` yerine `py` komutunu kullanman gerekebilir.

---

## Sorun Giderme

**Windows'ta terminalde kutu çizgileri/emoji bozuk görünüyor**
`app.py` başlangıçta otomatik olarak konsolu UTF-8'e (`chcp 65001`) geçirmeye
çalışır. Yine de sorun yaşarsan Windows Terminal veya PowerShell 7+ kullanmanı
öneririz (eski `cmd.exe` UTF-8 desteği sınırlıdır).

**CLI'da "mpv bulunamadı" hatası**
`mpv`'nin kurulu ve PATH'e ekli olduğundan emin ol, terminali/PowerShell'i
kapatıp yeniden aç.

**GUI'de ses gelmiyor (Linux)**
`PyQt6-Qt6` bazı Linux dağıtımlarında ek codec/GStreamer paketleri isteyebilir:
```bash
sudo apt install gstreamer1.0-libav gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
```

**GUI hiç açılmıyor (Linux, "xcb platform plugin" hatası)**
Gerekli sistem kütüphaneleri eksik olabilir:
```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0
```

**macOS'ta "mpv çalıştırılamadı çünkü geliştiricisi doğrulanamadı"**
Terminalden `xattr -d com.apple.quarantine $(which mpv)` çalıştırarak Gatekeeper
karantinasını kaldırabilirsin, ya da Homebrew ile kurmak bu sorunu genelde
yaşatmaz.

---

## Notlar

- `playlists.json` ve `playlist_icons.json` senin kişisel verilerindir, `.gitignore`
  ile depoya dahil edilmez — herkes kendi kopyasını oluşturur.
- Spotify çalma listesi senkronizasyonu, Spotify'ın herkese açık embed sayfasını
  kullanır; Spotify sayfa yapısını değiştirirse senkron kırılabilir — bu durumda
  uygulama otomatik olarak "Manuel Bypass Modu"na geçer.

## Özellikler

- Spotify çalma listesi senkronizasyonu + tekil şarkı arama
- 🌙 Mood/anahtar kelimeye göre otomatik liste oluşturma ("dark ambient", "lo-fi for coding"...)
- Canlı ses görselleştirici (CLI'da terminalde, GUI'de bar animasyonu)
- ⛔ Kill Switch — Esc / panik butonu ile müziği anında durdurma
- 📜 Şarkı sözleri — daktilo/"decrypt" efektiyle (YTMusic'in resmi sözler API'sinden)
- GUI'de sürükle-bırak ile şarkı sıralama, sağ tık ile silme/favorileme
- Çoklu çalma listesi, özel simge ve yeniden adlandırma desteği
- Akış hatalarında (ör. "Demuxing failed" / bağlantı kopması) otomatik yeniden bağlanma

## Kendi bilgisayarında .exe / .app / AppImage üretme

Genelde buna gerek yok — Releases sayfasından hazır dosyayı indirmen yeterli.
Ama kendi makinende de derlemek istersen:

```bash
pip install -r requirements-build.txt

# GUI
pyinstaller --onefile --windowed --name Paraotify paraotify_gui.py

# CLI
pyinstaller --onefile --console --name Paraotify-CLI app.py
```

Üretilen dosya `dist/` klasöründe olur. **Önemli:** PyInstaller derlediği işletim
sistemi için dosya üretir — yani Windows'ta çalıştırırsan `.exe`, macOS'ta `.app`,
Linux'ta binary üretir. Üç platform için üç dosya istiyorsan (kendi bilgisayarınla
tek başına mümkün değil) `.github/workflows/build.yml` içindeki otomatik GitHub
Actions derlemesini kullanman gerekir — bir tag push ettiğinde GitHub'ın kendi
Windows/macOS/Linux sunucularında otomatik olarak üçü de derlenir.

