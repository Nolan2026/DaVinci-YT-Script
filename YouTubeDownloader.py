"""
YouTube -> DaVinci Resolve  (v3)

Install:
  1. pip install -U yt-dlp   (same Python that Resolve uses)
  2. Make sure ffmpeg is on your PATH.
  3. Copy this file to Resolve's Scripts/Utility folder:
       Windows: %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility
       macOS:   /Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility
       Linux:   ~/.local/share/DaVinciResolve/Fusion/Scripts/Utility
  4. Run from Resolve: Workspace > Scripts > YouTubeDownloader

What's new in v3:
  - Modern dark dialog, resolution picker as buttons (no dropdown)
  - Browse... folder picker + the folder is remembered for next runs
  - Live progress bar + percentage while downloading
  - Downloads run on a worker thread so the window never freezes
"""

import os
import re
import sys
import json
import subprocess
import tempfile
import threading

# ---------------------------------------------------------------- Resolve API
try:
    resolve  # type: ignore  # injected when run inside Resolve
except NameError:
    resolve = None

if resolve is None:
    try:
        import DaVinciResolveScript as dvr  # type: ignore
        resolve = dvr.scriptapp("Resolve")
    except Exception:
        try:
            import BlackmagicFusion as _bmd  # type: ignore
            resolve = _bmd.scriptapp("Resolve")
        except Exception:
            resolve = None

try:
    pm = resolve.GetProjectManager() if resolve else None
    project = pm.GetCurrentProject() if pm else None
    media_pool = project.GetMediaPool() if project else None
except Exception:
    pm = project = media_pool = None
try:
    media_storage = resolve.GetMediaStorage() if resolve else None
except Exception:
    media_storage = None


RESOLUTIONS = ["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
DEFAULT_RES = "1080p"

CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".resolve_youtube_downloader.json"
)


# ------------------------------------------------------------ saved settings
def load_settings():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_settings(**kw):
    data = load_settings()
    data.update(kw)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def default_download_dir():
    saved = load_settings().get("out_dir")
    if saved and os.path.isdir(saved):
        return saved
    path = os.path.join(os.path.expanduser("~"), "Downloads", "ResolveYouTube")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = tempfile.gettempdir()
    return path


# ------------------------------------------------------------------ download

def _find_node():
    """Return the path to node.exe / node, or None."""
    import shutil
    found = shutil.which("node") or shutil.which("node.exe")
    if found:
        return found
    # Common Windows location even when not on PATH
    candidates = [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
        os.path.expandvars(r"%APPDATA%\npm\node.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _find_ffmpeg():
    """Return the path to ffmpeg.exe / ffmpeg, or None."""
    import shutil
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    # Common locations
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%PROGRAMFILES(x86)%\ffmpeg\bin\ffmpeg.exe"),
        # winget (Gyan.FFmpeg) install path
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
            r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            r"\ffmpeg-9.0-full_build\bin\ffmpeg.exe"
        ),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def format_selector(choice, has_ffmpeg=True):
    if not has_ffmpeg:
        # Without ffmpeg we can't merge; grab the best single pre-merged file
        if choice == "Best":
            return "best"
        height = choice.replace("p", "")
        return f"best[height<={height}]/best"
    if choice == "Best":
        return "bestvideo*+bestaudio/best"
    height = choice.replace("p", "")
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"



def _find_ytdlp_cmd():
    """Return the best available command to invoke yt-dlp.

    Resolve's embedded Python may not have yt-dlp installed, so we:
    1. Try a standalone  yt-dlp / yt-dlp.exe  on PATH.
    2. Try common system Python locations that have yt-dlp.
    3. Fall back to sys.executable as a last resort.
    """
    import shutil

    # 1. standalone yt-dlp binary on PATH
    ytdlp_bin = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if ytdlp_bin:
        return [ytdlp_bin]

    # 2. Look for a system Python that can import yt_dlp
    candidates = []
    if sys.platform.startswith("win"):
        # Common Windows locations
        for base in [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python"),
            os.path.expandvars(r"%PROGRAMFILES%\Python"),
            os.path.expandvars(r"%APPDATA%\Python"),
            r"C:\Python311", r"C:\Python312", r"C:\Python310",
        ]:
            if os.path.isdir(base):
                for entry in os.listdir(base):
                    py = os.path.join(base, entry, "python.exe")
                    if os.path.isfile(py):
                        candidates.append(py)
        # Also try PATH pythons
        for name in ("python", "python3", "python3.11", "python3.12"):
            p = shutil.which(name)
            if p and p not in candidates:
                candidates.append(p)
    else:
        for name in ("python3", "python3.11", "python3.12", "python"):
            p = shutil.which(name)
            if p:
                candidates.append(p)

    probe = (
        "import importlib.util, sys; "
        "sys.exit(0 if importlib.util.find_spec('yt_dlp') else 1)"
    )
    creation = 0x08000000 if sys.platform.startswith("win") else 0
    for py in candidates:
        if py == sys.executable:
            continue  # skip Resolve's own Python
        try:
            ret = subprocess.run(
                [py, "-c", probe],
                timeout=5,
                creationflags=creation,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            if ret == 0:
                return [py, "-m", "yt_dlp"]
        except Exception:
            continue

    # 3. last resort – current interpreter (may or may not work)
    return [sys.executable, "-m", "yt_dlp"]


def yt_dlp_command(url, choice, out_dir):
    template = os.path.join(out_dir, "%(title).80s [%(id)s].%(ext)s")
    cmd_prefix = _find_ytdlp_cmd()

    node = _find_node()
    ffmpeg = _find_ffmpeg()

    cmd = [*cmd_prefix]

    # JavaScript runtime + EJS challenge solver – required for YouTube n-challenge (fixes 403)
    if node:
        cmd += ["--js-runtimes", f"node:{node}"]
        cmd += ["--remote-components", "ejs:github"]

    # ffmpeg – required for merging separate video+audio streams
    if ffmpeg:
        cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
        cmd += ["-f", format_selector(choice, has_ffmpeg=True)]
        cmd += ["--merge-output-format", "mp4"]
    else:
        # No ffmpeg: fall back to a pre-merged single-file format
        cmd += ["-f", format_selector(choice, has_ffmpeg=False)]

    # cookies.txt – fixes 429 / bot-check errors
    cookies_file = load_settings().get("cookies_file", "")
    if cookies_file and os.path.isfile(cookies_file):
        cmd += ["--cookies", cookies_file]

    cmd += [
        "--no-playlist",
        "--restrict-filenames",
        "--force-overwrites",
        "--newline",
        "--print", "after_move:filepath",
        "--no-simulate",
        "-o", template,
        url,
    ]
    return cmd


PCT_RE = re.compile(r"\[download\]\s+([\d.]+)%")


def download(url, choice, out_dir, log, progress=None):
    cmd = yt_dlp_command(url, choice, out_dir)
    log("Downloading: " + url)
    creation = 0x08000000 if sys.platform.startswith("win") else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        creationflags=creation,
    )
    last_path = None
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        m = PCT_RE.search(line)
        if m and progress:
            progress(float(m.group(1)))
            continue
        if os.path.isabs(line) and os.path.exists(line):
            last_path = line
        log(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("yt-dlp failed (exit code %s)" % proc.returncode)
    if not last_path:
        files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
        files = [f for f in files if os.path.isfile(f)]
        if not files:
            raise RuntimeError("Download finished but no file was found.")
        last_path = max(files, key=os.path.getmtime)
    if progress:
        progress(100.0)
    return last_path


def get_resolve_handles():
    """Grab fresh handles every time - cached ones go stale when the user
    switches project/page, which silently breaks the import."""
    r = resolve
    if r is None:
        try:
            import DaVinciResolveScript as dvr  # type: ignore
            r = dvr.scriptapp("Resolve")
        except Exception:
            r = None
    if r is None:
        return None, None, None
    try:
        proj = r.GetProjectManager().GetCurrentProject()
        pool = proj.GetMediaPool() if proj else None
    except Exception:
        proj = pool = None
    try:
        storage = r.GetMediaStorage()
    except Exception:
        storage = None
    return proj, pool, storage


def import_to_resolve(path, add_to_timeline, log):
    proj, pool, storage = get_resolve_handles()
    if proj is None:
        log("")
        log("No open DaVinci Resolve project found. The video is ready here:")
        log(path)
        return

    clips = None
    try:
        if pool is not None:
            try:
                root_folder = pool.GetRootFolder()
                if root_folder:
                    pool.SetCurrentFolder(root_folder)
            except Exception:
                pass
            clips = pool.ImportMedia([path])
        if not clips and storage is not None:
            clips = storage.AddItemListToMediaPool([path])
    except Exception as exc:
        log("Media Pool import blocked by Resolve: %s" % exc)
        clips = None

    if not clips:
        log("")
        log("Could not add it automatically. The video is ready here:")
        log(path)
        log("Just drag that file into your Media Pool.")
        return

    log("Added to Media Pool: " + os.path.basename(path))

    if add_to_timeline:
        try:
            timeline = proj.GetCurrentTimeline()
            if timeline is None:
                new_tl = pool.CreateTimelineFromClips("YouTube Timeline", clips)
                if new_tl:
                    try:
                        proj.SetCurrentTimeline(new_tl)
                    except Exception:
                        pass
                log("Created new timeline with the clip.")
            else:
                pool.AppendToTimeline(clips)
                log("Appended clip to the current timeline.")
        except Exception as exc:
            log("Could not append to timeline: %s" % exc)
            log("The clip is in the Media Pool - drag it to the timeline.")


def run_job(url, choice, out_dir, to_timeline, log, progress=None):
    try:
        if not url:
            log("Please paste a video URL first.")
            return
        out_dir = out_dir or default_download_dir()
        os.makedirs(out_dir, exist_ok=True)
        save_settings(out_dir=out_dir, resolution=choice, to_timeline=bool(to_timeline))
        path = download(url, choice, out_dir, log, progress)
        import_to_resolve(path, to_timeline, log)
        log("Done.")
    except Exception as exc:
        log("Error: %s" % exc)


# ------------------------------------------------------------------- Tk UI
BG      = "#12141a"
CARD    = "#1b1e26"
FIELD   = "#0e1015"
TEXT    = "#e8eaf0"
MUTED   = "#8b93a7"
ACCENT  = "#ff2d55"
ACCENT2 = "#ff5b7a"
BORDER  = "#2a2f3b"


def run_tk_ui():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        print("No UI toolkit available. Install Python with Tkinter support.")
        return

    settings = load_settings()

    root = tk.Tk()
    root.title("YouTube  ->  DaVinci Resolve")
    root.configure(bg=BG)
    root.geometry("720x620")
    root.minsize(660, 560)

    def card(parent, **kw):
        return tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, **kw)

    def label(parent, text, color=MUTED, size=9, bold=False, bg=CARD):
        return tk.Label(parent, text=text, bg=bg, fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    # ---- header
    header = tk.Frame(root, bg=BG)
    header.pack(fill="x", padx=22, pady=(20, 8))
    tk.Label(header, text="YouTube Downloader", bg=BG, fg=TEXT,
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(header, text="Grab a video and drop it straight into your project",
             bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")

    body = card(root)
    body.pack(fill="both", expand=True, padx=22, pady=(6, 18))
    inner = tk.Frame(body, bg=CARD)
    inner.pack(fill="both", expand=True, padx=18, pady=16)

    # ---- URL
    label(inner, "VIDEO URL", size=8, bold=True).pack(anchor="w")
    url_var = tk.StringVar()
    url_entry = tk.Entry(inner, textvariable=url_var, bg=FIELD, fg=TEXT,
                         insertbackground=ACCENT, relief="flat",
                         font=("Segoe UI", 11), highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT)
    url_entry.pack(fill="x", ipady=7, pady=(4, 14))
    url_entry.focus_set()

    # ---- resolution buttons
    label(inner, "RESOLUTION", size=8, bold=True).pack(anchor="w")
    res_row = tk.Frame(inner, bg=CARD)
    res_row.pack(fill="x", pady=(6, 16))

    chosen = {"res": settings.get("resolution", DEFAULT_RES)}
    if chosen["res"] not in RESOLUTIONS:
        chosen["res"] = DEFAULT_RES
    res_buttons = {}

    def paint_res():
        for name, btn in res_buttons.items():
            on = name == chosen["res"]
            btn.config(bg=ACCENT if on else FIELD,
                       fg="#ffffff" if on else MUTED,
                       highlightbackground=ACCENT if on else BORDER)

    def pick(name):
        chosen["res"] = name
        paint_res()
        save_settings(resolution=name)

    for name in RESOLUTIONS:
        b = tk.Button(res_row, text=name, relief="flat", bd=0, cursor="hand2",
                      font=("Segoe UI", 10, "bold"), padx=14, pady=8,
                      activebackground=ACCENT2, activeforeground="#ffffff",
                      highlightthickness=1,
                      command=lambda n=name: pick(n))
        b.pack(side="left", padx=(0, 8))
        res_buttons[name] = b
    paint_res()

    # ---- save location
    label(inner, "SAVE LOCATION", size=8, bold=True).pack(anchor="w")
    dir_row = tk.Frame(inner, bg=CARD)
    dir_row.pack(fill="x", pady=(6, 12))
    dir_var = tk.StringVar(value=default_download_dir())
    dir_entry = tk.Entry(dir_row, textvariable=dir_var, bg=FIELD, fg=TEXT,
                         insertbackground=ACCENT, relief="flat",
                         font=("Segoe UI", 10), highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT)
    dir_entry.pack(side="left", fill="x", expand=True, ipady=6)

    def browse():
        start = dir_var.get().strip() or default_download_dir()
        chosen_dir = filedialog.askdirectory(initialdir=start,
                                             title="Choose where to save videos")
        if chosen_dir:
            dir_var.set(chosen_dir)
            save_settings(out_dir=chosen_dir)
            log("Save location set to: " + chosen_dir)

    def open_folder():
        p = dir_var.get().strip()
        if not p or not os.path.isdir(p):
            log("That folder doesn't exist yet.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(p)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as exc:
            log("Could not open folder: %s" % exc)

    tk.Button(dir_row, text="Browse…", command=browse, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=TEXT, padx=14, pady=6,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="left", padx=(8, 0))
    tk.Button(dir_row, text="Open", command=open_folder, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=MUTED, padx=12, pady=6,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

    # ---- cookies file (fixes 429 / bot-check)
    label(inner, "COOKIES FILE  (optional — fixes 429 / bot errors)",
          size=8, bold=True).pack(anchor="w", pady=(8, 0))
    cookie_row = tk.Frame(inner, bg=CARD)
    cookie_row.pack(fill="x", pady=(4, 10))
    cookie_var = tk.StringVar(value=settings.get("cookies_file", ""))
    cookie_entry = tk.Entry(cookie_row, textvariable=cookie_var, bg=FIELD, fg=TEXT,
                            insertbackground=ACCENT, relief="flat",
                            font=("Segoe UI", 9), highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
    cookie_entry.pack(side="left", fill="x", expand=True, ipady=5)

    def browse_cookies():
        path = filedialog.askopenfilename(
            title="Select your cookies.txt file",
            filetypes=[("Netscape cookies", "*.txt"), ("All files", "*.*")],
        )
        if path:
            cookie_var.set(path)
            save_settings(cookies_file=path)
            log("Cookies file set: " + path)

    def clear_cookies():
        cookie_var.set("")
        save_settings(cookies_file="")
        log("Cookies file cleared.")

    tk.Button(cookie_row, text="Select…", command=browse_cookies, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=TEXT, padx=10, pady=5,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
    tk.Button(cookie_row, text="Clear", command=clear_cookies, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=MUTED, padx=10, pady=5,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))

    action_row = tk.Frame(inner, bg=CARD)
    action_row.pack(fill="x", pady=(0, 14))

    tl_var = tk.BooleanVar(value=bool(settings.get("to_timeline", True)))
    tk.Checkbutton(action_row, text="  Also append to current timeline",
                   variable=tl_var, bg=CARD, fg=TEXT, selectcolor=FIELD,
                   activebackground=CARD, activeforeground=TEXT, bd=0,
                   highlightthickness=0, anchor="w",
                   font=("Segoe UI", 10),
                   command=lambda: save_settings(to_timeline=tl_var.get())
                   ).pack(side="left")

    tk.Button(action_row, text="Close", command=root.destroy, relief="flat",
              bd=0, cursor="hand2", bg=CARD, fg=MUTED, padx=16, pady=9,
              activebackground=CARD, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="right", padx=(8, 0))

    go_btn = tk.Button(action_row, text="Download & Add", relief="flat", bd=0,
                       cursor="hand2", bg=ACCENT, fg="#ffffff", padx=22, pady=9,
                       activebackground=ACCENT2, activeforeground="#ffffff",
                       font=("Segoe UI", 10, "bold"))
    go_btn.pack(side="right")

    # ---- progress
    prog_wrap = tk.Frame(inner, bg=FIELD, height=6,
                         highlightbackground=BORDER, highlightthickness=1)
    prog_wrap.pack(fill="x")
    prog_wrap.pack_propagate(False)
    prog_bar = tk.Frame(prog_wrap, bg=ACCENT, width=0)
    prog_bar.place(x=0, y=0, relheight=1, relwidth=0)

    status_var = tk.StringVar(value="Ready")
    tk.Label(inner, textvariable=status_var, bg=CARD, fg=MUTED,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))

    def set_progress(pct):
        prog_bar.place_configure(relwidth=max(0.0, min(pct, 100.0)) / 100.0)
        status_var.set("Downloading… %.1f%%" % pct)

    # ---- log
    log_box = tk.Text(inner, height=9, bg=FIELD, fg="#b9c0d0", bd=0,
                      relief="flat", font=("Consolas", 9),
                      insertbackground=ACCENT, highlightthickness=1,
                      highlightbackground=BORDER, wrap="word")
    log_box.pack(fill="both", expand=True)

    def log(msg):
        log_box.insert("end", str(msg) + "\n")
        log_box.see("end")

    def start():
        url = url_var.get().strip()
        out_dir = dir_var.get().strip()
        if not url:
            status_var.set("Paste a YouTube URL first")
            log("Please paste a video URL first.")
            return
        go_btn.config(state="disabled", bg=BORDER, text="Working…")
        set_progress(0.0)
        res, to_tl = chosen["res"], tl_var.get()

        def finish():
            go_btn.config(state="normal", bg=ACCENT, text="Download & Add")
            status_var.set("Ready")

        def worker():
            run_job(url, res, out_dir, to_tl,
                    lambda m: root.after(0, log, m),
                    lambda p: root.after(0, set_progress, p))
            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    go_btn.config(command=start)
    root.bind("<Return>", lambda e: start())

    log("Saving to: " + dir_var.get())
    root.mainloop()


def main():
    run_tk_ui()


main()
