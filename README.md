# 🎬 YouTube → DaVinci Resolve Downloader

A DaVinci Resolve utility script that lets you download any YouTube video and instantly import it into your Media Pool — all from inside Resolve.

---

## ✨ Features

- 🎯 Paste a YouTube URL → downloads directly into your project
- 📐 Resolution picker: Best, 2160p, 1440p, 1080p, 720p, 480p, 360p
- 📁 Custom save folder (remembered across sessions)
- 📊 Live progress bar while downloading
- 🎞️ Auto-imports into Media Pool & appends to current timeline
- 🍪 Cookies support to fix 429 / bot-check errors
- 🖥️ Works on Windows, macOS, and Linux

---

## 📋 Requirements

| Tool | Required | Purpose |
|------|----------|---------|
| Python 3.8+ | ✅ Yes | Runs the script |
| yt-dlp | ✅ Yes | Downloads from YouTube |
| ffmpeg | ⚠️ Recommended | Merges video + audio for best quality |
| Node.js | ⚠️ Optional | Fixes YouTube 403 / n-challenge errors |

---

## 🚀 Step-by-Step Installation

### Step 1 — Install yt-dlp

**Windows (PowerShell / CMD):**
```bash
pip install -U yt-dlp
```

**macOS / Linux (Terminal):**
```bash
pip3 install -U yt-dlp
```

> ✅ Verify it works:
> ```bash
> yt-dlp --version
> ```

---

### Step 2 — Install ffmpeg (Recommended)

**Windows — using winget (easiest):**
```bash
winget install Gyan.FFmpeg
```

**Windows — using Chocolatey:**
```bash
choco install ffmpeg
```

**macOS — using Homebrew:**
```bash
brew install ffmpeg
```

**Ubuntu / Debian Linux:**
```bash
sudo apt update && sudo apt install ffmpeg -y
```

**Fedora / RHEL Linux:**
```bash
sudo dnf install ffmpeg -y
```

> ✅ Verify it works:
> ```bash
> ffmpeg -version
> ```

---

### Step 3 — Install Node.js (Optional but recommended)

Node.js fixes YouTube 403 errors caused by the n-challenge. Without it, some videos may fail.

**Windows — using winget:**
```bash
winget install OpenJS.NodeJS
```

**Windows — using Chocolatey:**
```bash
choco install nodejs
```

**macOS — using Homebrew:**
```bash
brew install node
```

**Ubuntu / Debian Linux:**
```bash
sudo apt install nodejs npm -y
```

> ✅ Verify it works:
> ```bash
> node --version
> ```

---

### Step 4 — Copy the Script to DaVinci Resolve

Copy `YouTubeDownloader.py` to the Resolve **Utility** scripts folder.

**Windows — PowerShell:**
```powershell
# Create the folder if it doesn'\''t exist
New-Item -ItemType Directory -Force -Path "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"

# Copy the script
Copy-Item "YouTubeDownloader.py" "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\"
```

**macOS — Terminal:**
```bash
# Create the folder if it doesn't exist
mkdir -p "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"

# Copy the script
cp YouTubeDownloader.py "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/"
```

**Linux — Terminal:**
```bash
# Create the folder if it doesn't exist
mkdir -p ~/.local/share/DaVinciResolve/Fusion/Scripts/Utility

# Copy the script
cp YouTubeDownloader.py ~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/
```

---

### Step 5 — Run It Inside DaVinci Resolve

1. Open **DaVinci Resolve**
2. Go to **Workspace → Scripts → Utility → YouTubeDownloader**
3. Paste a YouTube URL and click **Download & Add** 🎉

---

## 🪟 Script Folder Paths (Reference)

| OS | Path |
|----|------|
| Windows | `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility` |
| macOS | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility` |
| Linux | `~/.local/share/DaVinciResolve/Fusion/Scripts/Utility` |

---

## 🍪 Fixing 429 / Bot-Check Errors (Cookies)

If YouTube blocks downloads with a **429** or **Sign in** error:

1. Install the **"Get cookies.txt LOCALLY"** browser extension
2. Export your YouTube cookies as `cookies.txt`
3. In the script UI, click **Select…** next to *Cookies File* and point to the file

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| `yt-dlp: command not found` | Run `pip install -U yt-dlp` again; make sure pip is on PATH |
| Video downloads but no audio | Install `ffmpeg` (Step 2) |
| 403 / n-challenge error | Install `Node.js` (Step 3) |
| Script not showing in Resolve | Check the script is in the correct **Utility** folder for your OS |
| Clip not added to Media Pool | Make sure a project is open in Resolve before downloading |

---

## 📄 License

MIT — free to use, share, and modify.
