"""
YouTube / Instagram -> DaVinci Resolve  (v4)

Install:
  1. pip install -U yt-dlp   (same Python that Resolve uses)
  2. Make sure ffmpeg is on your PATH.
  3. Copy this file to Resolve's Scripts/Utility folder:
       Windows: %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility
       macOS:   /Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility
       Linux:   ~/.local/share/DaVinciResolve/Fusion/Scripts/Utility
  4. Run from Resolve: Workspace > Scripts > YouTubeDownloader

What's new in v4:
  - Instagram tab: paste a Reel / post URL and download directly
  - YouTube tab unchanged (resolution picker, cookies, timeline import)
  - Tab switcher in the header
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


def default_insta_dir():
    saved = load_settings().get("insta_out_dir")
    if saved and os.path.isdir(saved):
        return saved
    path = os.path.join(os.path.expanduser("~"), "Downloads", "ResolveInstagram")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = tempfile.gettempdir()
    return path


# ------------------------------------------------------------------ helpers

def _find_node():
    import shutil
    found = shutil.which("node") or shutil.which("node.exe")
    if found:
        return found
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
    import shutil
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%PROGRAMFILES(x86)%\ffmpeg\bin\ffmpeg.exe"),
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
        if choice == "Best":
            return "best"
        height = choice.replace("p", "")
        return f"best[height<={height}]/best"
    if choice == "Best":
        return "bestvideo*+bestaudio/best"
    height = choice.replace("p", "")
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"


def _find_ytdlp_cmd():
    import shutil
    ytdlp_bin = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if ytdlp_bin:
        return [ytdlp_bin]

    candidates = []
    if sys.platform.startswith("win"):
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
            continue
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

    return [sys.executable, "-m", "yt_dlp"]


# ------------------------------------------------------------------ YouTube download

def yt_dlp_command(url, choice, out_dir):
    template = os.path.join(out_dir, "%(title).80s [%(id)s].%(ext)s")
    cmd_prefix = _find_ytdlp_cmd()
    node   = _find_node()
    ffmpeg = _find_ffmpeg()

    cmd = [*cmd_prefix]

    if node:
        cmd += ["--js-runtimes", f"node:{node}"]
        cmd += ["--remote-components", "ejs:github"]

    if ffmpeg:
        cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
        cmd += ["-f", format_selector(choice, has_ffmpeg=True)]
        cmd += ["--merge-output-format", "mp4"]
    else:
        cmd += ["-f", format_selector(choice, has_ffmpeg=False)]

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


# ------------------------------------------------------------------ Instagram download

def insta_dlp_command(url, out_dir):
    """yt-dlp command for Instagram Reels / posts — no quality picker, no cookies."""
    template = os.path.join(out_dir, "%(uploader)s_%(id)s.%(ext)s")
    cmd_prefix = _find_ytdlp_cmd()
    ffmpeg = _find_ffmpeg()

    cmd = [*cmd_prefix]

    if ffmpeg:
        cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
        cmd += ["-f", "bestvideo+bestaudio/best"]
        cmd += ["--merge-output-format", "mp4"]
    else:
        cmd += ["-f", "best"]

    cmd += [
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


def download(url, choice, out_dir, log, progress=None, platform="youtube"):
    if platform == "instagram":
        cmd = insta_dlp_command(url, out_dir)
    else:
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


def run_job(url, choice, out_dir, to_timeline, log, progress=None, platform="youtube"):
    try:
        if not url:
            log("Please paste a video URL first.")
            return
        out_dir = out_dir or (default_insta_dir() if platform == "instagram" else default_download_dir())
        os.makedirs(out_dir, exist_ok=True)
        if platform == "youtube":
            save_settings(out_dir=out_dir, resolution=choice, to_timeline=bool(to_timeline))
        else:
            save_settings(insta_out_dir=out_dir)
        path = download(url, choice, out_dir, log, progress, platform=platform)
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
ACCENT  = "#ff2d55"       # YouTube / active tab
INSTA   = "#c13584"       # Instagram gradient mid
ACCENT2 = "#ff5b7a"
BORDER  = "#2a2f3b"
TAB_ACT = "#1f2330"       # active tab bg


def run_tk_ui():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        print("No UI toolkit available. Install Python with Tkinter support.")
        return

    settings = load_settings()

    root = tk.Tk()
    root.title("YouTube / Instagram  ->  DaVinci Resolve")
    root.configure(bg=BG)
    root.geometry("740x680")
    root.minsize(680, 600)

    # ---------------------------------------------------------------- helpers
    def card(parent, **kw):
        return tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, **kw)

    def label(parent, text, color=MUTED, size=9, bold=False, bg=CARD):
        return tk.Label(parent, text=text, bg=bg, fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    # ---------------------------------------------------------------- header
    header = tk.Frame(root, bg=BG)
    header.pack(fill="x", padx=22, pady=(18, 0))

    tk.Label(header, text="Media Downloader", bg=BG, fg=TEXT,
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(header, text="Download from YouTube or Instagram into your project",
             bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")

    # ---------------------------------------------------------------- TAB BAR
    tab_bar = tk.Frame(root, bg=BG)
    tab_bar.pack(fill="x", padx=22, pady=(14, 0))

    active_tab = {"name": "youtube"}   # mutable state

    tab_yt_btn  = None
    tab_ig_btn  = None

    def paint_tabs():
        for name, btn, accent_col in [
            ("youtube",   tab_yt_btn,  ACCENT),
            ("instagram", tab_ig_btn,  INSTA),
        ]:
            on = active_tab["name"] == name
            btn.config(
                bg=TAB_ACT if on else BG,
                fg=accent_col if on else MUTED,
                relief="flat",
                highlightbackground=accent_col if on else BORDER,
                highlightthickness=2 if on else 1,
            )

    def switch_tab(name):
        active_tab["name"] = name
        paint_tabs()
        if name == "youtube":
            insta_frame.pack_forget()
            yt_frame.pack(fill="both", expand=True, padx=22, pady=(8, 18))
        else:
            yt_frame.pack_forget()
            insta_frame.pack(fill="both", expand=True, padx=22, pady=(8, 18))

    tab_yt_btn = tk.Button(
        tab_bar, text="▶  YouTube", cursor="hand2",
        font=("Segoe UI", 10, "bold"), padx=18, pady=8,
        activebackground=TAB_ACT, activeforeground=ACCENT,
        bd=0, highlightthickness=1,
        command=lambda: switch_tab("youtube")
    )
    tab_yt_btn.pack(side="left", padx=(0, 6))

    tab_ig_btn = tk.Button(
        tab_bar, text="📷  Instagram", cursor="hand2",
        font=("Segoe UI", 10, "bold"), padx=18, pady=8,
        activebackground=TAB_ACT, activeforeground=INSTA,
        bd=0, highlightthickness=1,
        command=lambda: switch_tab("instagram")
    )
    tab_ig_btn.pack(side="left")

    # ================================================================ YOUTUBE FRAME
    yt_frame = card(root)

    yt_inner = tk.Frame(yt_frame, bg=CARD)
    yt_inner.pack(fill="both", expand=True, padx=18, pady=16)

    # -- URL
    label(yt_inner, "VIDEO URL", size=8, bold=True).pack(anchor="w")
    yt_url_var = tk.StringVar()
    yt_url_entry = tk.Entry(yt_inner, textvariable=yt_url_var, bg=FIELD, fg=TEXT,
                            insertbackground=ACCENT, relief="flat",
                            font=("Segoe UI", 11), highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
    yt_url_entry.pack(fill="x", ipady=7, pady=(4, 14))
    yt_url_entry.focus_set()

    # -- Resolution
    label(yt_inner, "RESOLUTION", size=8, bold=True).pack(anchor="w")
    res_row = tk.Frame(yt_inner, bg=CARD)
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

    # -- Save location
    label(yt_inner, "SAVE LOCATION", size=8, bold=True).pack(anchor="w")
    yt_dir_row = tk.Frame(yt_inner, bg=CARD)
    yt_dir_row.pack(fill="x", pady=(6, 12))
    yt_dir_var = tk.StringVar(value=default_download_dir())
    tk.Entry(yt_dir_row, textvariable=yt_dir_var, bg=FIELD, fg=TEXT,
             insertbackground=ACCENT, relief="flat",
             font=("Segoe UI", 10), highlightthickness=1,
             highlightbackground=BORDER, highlightcolor=ACCENT
             ).pack(side="left", fill="x", expand=True, ipady=6)

    def yt_browse():
        d = filedialog.askdirectory(initialdir=yt_dir_var.get() or default_download_dir(),
                                    title="Choose where to save YouTube videos")
        if d:
            yt_dir_var.set(d)
            save_settings(out_dir=d)
            yt_log("Save location set to: " + d)

    def yt_open_folder():
        p = yt_dir_var.get().strip()
        if not p or not os.path.isdir(p):
            yt_log("That folder doesn't exist yet.")
            return
        _open_folder(p)

    tk.Button(yt_dir_row, text="Browse…", command=yt_browse, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=TEXT, padx=14, pady=6,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="left", padx=(8, 0))
    tk.Button(yt_dir_row, text="Open", command=yt_open_folder, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=MUTED, padx=12, pady=6,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

    # -- Cookies
    label(yt_inner, "COOKIES FILE  (optional — fixes 429 / bot errors)",
          size=8, bold=True).pack(anchor="w", pady=(8, 0))
    cookie_row = tk.Frame(yt_inner, bg=CARD)
    cookie_row.pack(fill="x", pady=(4, 10))
    cookie_var = tk.StringVar(value=settings.get("cookies_file", ""))
    tk.Entry(cookie_row, textvariable=cookie_var, bg=FIELD, fg=TEXT,
             insertbackground=ACCENT, relief="flat",
             font=("Segoe UI", 9), highlightthickness=1,
             highlightbackground=BORDER, highlightcolor=ACCENT
             ).pack(side="left", fill="x", expand=True, ipady=5)

    def browse_cookies():
        path = filedialog.askopenfilename(
            title="Select your cookies.txt file",
            filetypes=[("Netscape cookies", "*.txt"), ("All files", "*.*")],
        )
        if path:
            cookie_var.set(path)
            save_settings(cookies_file=path)
            yt_log("Cookies file set: " + path)

    def clear_cookies():
        cookie_var.set("")
        save_settings(cookies_file="")
        yt_log("Cookies file cleared.")

    tk.Button(cookie_row, text="Select…", command=browse_cookies, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=TEXT, padx=10, pady=5,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
    tk.Button(cookie_row, text="Clear", command=clear_cookies, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=MUTED, padx=10, pady=5,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))

    # -- Action row
    yt_action = tk.Frame(yt_inner, bg=CARD)
    yt_action.pack(fill="x", pady=(0, 14))

    tl_var = tk.BooleanVar(value=bool(settings.get("to_timeline", True)))
    tk.Checkbutton(yt_action, text="  Also append to current timeline",
                   variable=tl_var, bg=CARD, fg=TEXT, selectcolor=FIELD,
                   activebackground=CARD, activeforeground=TEXT, bd=0,
                   highlightthickness=0, anchor="w",
                   font=("Segoe UI", 10),
                   command=lambda: save_settings(to_timeline=tl_var.get())
                   ).pack(side="left")

    tk.Button(yt_action, text="Close", command=root.destroy, relief="flat",
              bd=0, cursor="hand2", bg=CARD, fg=MUTED, padx=16, pady=9,
              activebackground=CARD, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="right", padx=(8, 0))

    yt_go_btn = tk.Button(yt_action, text="Download & Add", relief="flat", bd=0,
                          cursor="hand2", bg=ACCENT, fg="#ffffff", padx=22, pady=9,
                          activebackground=ACCENT2, activeforeground="#ffffff",
                          font=("Segoe UI", 10, "bold"))
    yt_go_btn.pack(side="right")

    # -- Progress
    yt_prog_wrap = tk.Frame(yt_inner, bg=FIELD, height=6,
                            highlightbackground=BORDER, highlightthickness=1)
    yt_prog_wrap.pack(fill="x")
    yt_prog_wrap.pack_propagate(False)
    yt_prog_bar = tk.Frame(yt_prog_wrap, bg=ACCENT, width=0)
    yt_prog_bar.place(x=0, y=0, relheight=1, relwidth=0)

    yt_status_var = tk.StringVar(value="Ready")
    tk.Label(yt_inner, textvariable=yt_status_var, bg=CARD, fg=MUTED,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 4))

    def yt_set_progress(pct):
        yt_prog_bar.place_configure(relwidth=max(0.0, min(pct, 100.0)) / 100.0)
        yt_status_var.set("Downloading… %.1f%%" % pct)

    # -- Log
    yt_log_box = tk.Text(yt_inner, height=7, bg=FIELD, fg="#b9c0d0", bd=0,
                         relief="flat", font=("Consolas", 9),
                         insertbackground=ACCENT, highlightthickness=1,
                         highlightbackground=BORDER, wrap="word")
    yt_log_box.pack(fill="both", expand=True)

    def yt_log(msg):
        yt_log_box.insert("end", str(msg) + "\n")
        yt_log_box.see("end")

    def yt_start():
        url = yt_url_var.get().strip()
        out_dir = yt_dir_var.get().strip()
        if not url:
            yt_status_var.set("Paste a YouTube URL first")
            yt_log("Please paste a video URL first.")
            return
        yt_go_btn.config(state="disabled", bg=BORDER, text="Working…")
        yt_set_progress(0.0)
        res, to_tl = chosen["res"], tl_var.get()

        def finish():
            yt_go_btn.config(state="normal", bg=ACCENT, text="Download & Add")
            yt_status_var.set("Ready")

        def worker():
            run_job(url, res, out_dir, to_tl,
                    lambda m: root.after(0, yt_log, m),
                    lambda p: root.after(0, yt_set_progress, p),
                    platform="youtube")
            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    yt_go_btn.config(command=yt_start)
    yt_log("Saving to: " + yt_dir_var.get())

    # ================================================================ INSTAGRAM FRAME
    insta_frame = card(root)

    ig_inner = tk.Frame(insta_frame, bg=CARD)
    ig_inner.pack(fill="both", expand=True, padx=18, pady=16)

    # -- Header note
    tk.Label(ig_inner,
             text="📷  Paste an Instagram Reel, post, or story URL below",
             bg=CARD, fg=MUTED, font=("Segoe UI", 10, "italic")
             ).pack(anchor="w", pady=(0, 12))

    # -- URL
    label(ig_inner, "INSTAGRAM URL", size=8, bold=True).pack(anchor="w")
    ig_url_var = tk.StringVar()
    ig_url_entry = tk.Entry(ig_inner, textvariable=ig_url_var, bg=FIELD, fg=TEXT,
                            insertbackground=INSTA, relief="flat",
                            font=("Segoe UI", 11), highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=INSTA)
    ig_url_entry.pack(fill="x", ipady=7, pady=(4, 18))

    # -- Save location
    label(ig_inner, "SAVE LOCATION", size=8, bold=True).pack(anchor="w")
    ig_dir_row = tk.Frame(ig_inner, bg=CARD)
    ig_dir_row.pack(fill="x", pady=(6, 16))
    ig_dir_var = tk.StringVar(value=default_insta_dir())
    tk.Entry(ig_dir_row, textvariable=ig_dir_var, bg=FIELD, fg=TEXT,
             insertbackground=INSTA, relief="flat",
             font=("Segoe UI", 10), highlightthickness=1,
             highlightbackground=BORDER, highlightcolor=INSTA
             ).pack(side="left", fill="x", expand=True, ipady=6)

    def ig_browse():
        d = filedialog.askdirectory(initialdir=ig_dir_var.get() or default_insta_dir(),
                                    title="Choose where to save Instagram videos")
        if d:
            ig_dir_var.set(d)
            save_settings(insta_out_dir=d)
            ig_log("Save location set to: " + d)

    def ig_open_folder():
        p = ig_dir_var.get().strip()
        if not p or not os.path.isdir(p):
            ig_log("That folder doesn't exist yet.")
            return
        _open_folder(p)

    tk.Button(ig_dir_row, text="Browse…", command=ig_browse, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=TEXT, padx=14, pady=6,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="left", padx=(8, 0))
    tk.Button(ig_dir_row, text="Open", command=ig_open_folder, relief="flat", bd=0,
              cursor="hand2", bg=FIELD, fg=MUTED, padx=12, pady=6,
              activebackground=BORDER, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

    # -- Action row
    ig_action = tk.Frame(ig_inner, bg=CARD)
    ig_action.pack(fill="x", pady=(0, 14))

    ig_tl_var = tk.BooleanVar(value=bool(settings.get("to_timeline", True)))
    tk.Checkbutton(ig_action, text="  Also append to current timeline",
                   variable=ig_tl_var, bg=CARD, fg=TEXT, selectcolor=FIELD,
                   activebackground=CARD, activeforeground=TEXT, bd=0,
                   highlightthickness=0, anchor="w",
                   font=("Segoe UI", 10),
                   ).pack(side="left")

    tk.Button(ig_action, text="Close", command=root.destroy, relief="flat",
              bd=0, cursor="hand2", bg=CARD, fg=MUTED, padx=16, pady=9,
              activebackground=CARD, activeforeground=TEXT,
              font=("Segoe UI", 10)).pack(side="right", padx=(8, 0))

    ig_go_btn = tk.Button(ig_action, text="Download & Add", relief="flat", bd=0,
                          cursor="hand2", bg=INSTA, fg="#ffffff", padx=22, pady=9,
                          activebackground="#9c2f6e", activeforeground="#ffffff",
                          font=("Segoe UI", 10, "bold"))
    ig_go_btn.pack(side="right")

    # -- Progress
    ig_prog_wrap = tk.Frame(ig_inner, bg=FIELD, height=6,
                            highlightbackground=BORDER, highlightthickness=1)
    ig_prog_wrap.pack(fill="x")
    ig_prog_wrap.pack_propagate(False)
    ig_prog_bar = tk.Frame(ig_prog_wrap, bg=INSTA, width=0)
    ig_prog_bar.place(x=0, y=0, relheight=1, relwidth=0)

    ig_status_var = tk.StringVar(value="Ready")
    tk.Label(ig_inner, textvariable=ig_status_var, bg=CARD, fg=MUTED,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 4))

    def ig_set_progress(pct):
        ig_prog_bar.place_configure(relwidth=max(0.0, min(pct, 100.0)) / 100.0)
        ig_status_var.set("Downloading… %.1f%%" % pct)

    # -- Log
    ig_log_box = tk.Text(ig_inner, height=10, bg=FIELD, fg="#b9c0d0", bd=0,
                         relief="flat", font=("Consolas", 9),
                         insertbackground=INSTA, highlightthickness=1,
                         highlightbackground=BORDER, wrap="word")
    ig_log_box.pack(fill="both", expand=True)

    def ig_log(msg):
        ig_log_box.insert("end", str(msg) + "\n")
        ig_log_box.see("end")

    def ig_start():
        url = ig_url_var.get().strip()
        out_dir = ig_dir_var.get().strip()
        if not url:
            ig_status_var.set("Paste an Instagram URL first")
            ig_log("Please paste an Instagram URL first.")
            return
        ig_go_btn.config(state="disabled", bg=BORDER, text="Working…")
        ig_set_progress(0.0)

        def finish():
            ig_go_btn.config(state="normal", bg=INSTA, text="Download & Add")
            ig_status_var.set("Ready")

        def worker():
            run_job(url, None, out_dir, ig_tl_var.get(),
                    lambda m: root.after(0, ig_log, m),
                    lambda p: root.after(0, ig_set_progress, p),
                    platform="instagram")
            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    ig_go_btn.config(command=ig_start)
    ig_log("Saving to: " + ig_dir_var.get())

    # ---------------------------------------------------------------- initial paint
    paint_tabs()
    switch_tab("youtube")   # start on YouTube tab

    root.mainloop()


def _open_folder(p):
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as exc:
        print("Could not open folder: %s" % exc)


def main():
    run_tk_ui()


main()
