#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, time, webbrowser, datetime as dt, threading, shutil, subprocess, socket, re, tempfile
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

# ---------- Config & state ----------
BASE_URL = os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu").rstrip("/")
TOKEN = os.environ.get("CANVAS_TOKEN", "")
USER_TZ = os.environ.get("TZ", "America/New_York")
UA = os.environ.get("CANVAS_UA", "canvas-tui/0.5 (textual)")
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))
MAX_RETRIES = int(os.environ.get("HTTP_MAX_RETRIES", "5"))
BACKOFF_FACTOR = float(os.environ.get("HTTP_BACKOFF", "0.4"))

DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "7"))
PAST_HOURS = int(os.environ.get("PAST_HOURS", "72"))
REFRESH_COOLDOWN = float(os.environ.get("REFRESH_COOLDOWN", "2.0"))
AUTO_REFRESH_SEC = int(os.environ.get("AUTO_REFRESH_SEC", "300"))
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR")
DEFAULT_BLOCK_MIN = int(os.environ.get("DEFAULT_BLOCK_MIN", "60"))
EXPORT_DIR = os.path.expanduser(os.environ.get("EXPORT_DIR", "~/.local/share/canvas-tui"))
EXPORT_ICS = os.path.join(EXPORT_DIR, "canvas.ics")
OPEN_AFTER_DL = os.environ.get("OPEN_AFTER_DL", "0") == "1"
CALCURSE_IMPORT = os.environ.get("CALCURSE_IMPORT", "0") == "1"

# Announcements separate window (defaults ±14 days)
ANN_PAST_DAYS = int(os.environ.get("ANN_PAST_DAYS", "14"))
ANN_FUTURE_DAYS = int(os.environ.get("ANN_FUTURE_DAYS", "14"))

CONFIG_DIR = os.path.expanduser("~/.config/canvas-tui")
CONFIG_TOML = os.path.join(CONFIG_DIR, "config.toml")
CONFIG_JSON = os.path.join(CONFIG_DIR, "config.json")
STATE_PATH = os.path.join(EXPORT_DIR, "state.json")

if not TOKEN:
    print("ERROR: Set CANVAS_TOKEN env var.", file=sys.stderr)
    sys.exit(1)

def _ensure_dirs():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

def _load_config():
    global DAYS_AHEAD, REFRESH_COOLDOWN, AUTO_REFRESH_SEC, DOWNLOAD_DIR, DEFAULT_BLOCK_MIN, PAST_HOURS, ANN_PAST_DAYS, ANN_FUTURE_DAYS
    try:
        import tomllib  # 3.11+
        cfg = None
        if os.path.exists(CONFIG_TOML):
            with open(CONFIG_TOML, "rb") as f: cfg = tomllib.load(f)
        elif os.path.exists(CONFIG_JSON):
            with open(CONFIG_JSON, "r", encoding="utf-8") as f: cfg = json.load(f)
        if not cfg: return
        DAYS_AHEAD = int(cfg.get("days_ahead", DAYS_AHEAD))
        REFRESH_COOLDOWN = float(cfg.get("refresh_cooldown", REFRESH_COOLDOWN))
        AUTO_REFRESH_SEC = int(cfg.get("auto_refresh_sec", AUTO_REFRESH_SEC))
        DOWNLOAD_DIR = cfg.get("download_dir", DOWNLOAD_DIR)
        DEFAULT_BLOCK_MIN = int(cfg.get("default_block_min", DEFAULT_BLOCK_MIN))
        PAST_HOURS = int(cfg.get("past_hours", PAST_HOURS))
        ANN_PAST_DAYS = int(cfg.get("ann_past_days", ANN_PAST_DAYS))
        ANN_FUTURE_DAYS = int(cfg.get("ann_futuredays", ANN_FUTURE_DAYS)) if "ann_futuredays" in cfg else int(cfg.get("ann_future_days", ANN_FUTURE_DAYS))
    except Exception:
        pass

_ensure_dirs(); _load_config()

def _load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_state(st: Dict[str, Any]) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE_PATH)

STATE = _load_state()
STATE.setdefault("visibility", {})
STATE.setdefault("priority", {})
STATE.setdefault("bucket", {})
STATE.setdefault("pomo_end_ts", None)
STATE.setdefault("cache_items", [])
STATE.setdefault("cache_announcements", [])

# ---------- HTTP ----------
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

S = requests.Session()
S.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": UA,
    "Accept": "application/json"
})
retry = Retry(
    total=MAX_RETRIES, connect=MAX_RETRIES, read=MAX_RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
    respect_retry_after_header=True,
)
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
S.mount("https://", adapter); S.mount("http://", adapter)

# ---------- Helpers ----------
def _iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_link_header(link_value: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not link_value: return out
    parts = [p.strip() for p in link_value.split(",")]
    for part in parts:
        if ";" not in part: continue
        url_part, *params = part.split(";")
        url = url_part.strip().lstrip("<").rstrip(">")
        rel = None
        for p in params:
            if "rel=" in p:
                rel = p.split("=", 1)[1].strip().strip('"')
                break
        if rel: out[rel] = url
    return out

def get_all(url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    while True:
        r = S.get(url, params=params, timeout=HTTP_TIMEOUT)
        if r.status_code == 401:
            raise SystemExit("Unauthorized (401). Check CANVAS_TOKEN.")
        r.raise_for_status()
        page = r.json()
        if not page:
            pass
        elif isinstance(page, list): items.extend(page)
        else: items.append(page)
        links = parse_link_header(r.headers.get("Link", ""))
        if "next" in links:
            url = links["next"]; params = {}
        else:
            break
    return items

def absolute_url(html_url: str) -> str:
    if html_url.startswith(("http://", "https://")): return html_url
    return urljoin(BASE_URL, html_url)

def sanitize(s: str) -> str:
    s = re.sub(r"[\\/:\*\?\"<>\|]+", "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "untitled"

def local_dt(iso_str: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso_str.replace("Z","+00:00")).astimezone(ZoneInfo(USER_TZ))

def _fmt_local(ts_iso: str) -> str:
    t = local_dt(ts_iso)
    try:   return t.strftime("%-m/%-d/%Y %H:%M")  # linux
    except Exception: return t.strftime("%m/%d/%Y %H:%M")

def rel_time(target: dt.datetime) -> str:
    now = dt.datetime.now(ZoneInfo(USER_TZ))
    s = int((target-now).total_seconds())
    sign = 1 if s >= 0 else -1
    s = abs(s)
    d, h, m = s//86400, (s%86400)//3600, (s%3600)//60
    if sign>0:
        if d>0: return f"in {d}d {h}h"
        if h>0: return f"in {h}h {m}m"
        return f"in {m}m"
    else:
        if d>0: return f"{d}d {h}h ago"
        if h>0: return f"{h}h {m}m ago"
        return f"{m}m ago"

def get_download_dir() -> str:
    if DOWNLOAD_DIR: return os.path.expanduser(DOWNLOAD_DIR)
    xdg = os.path.expanduser("~/.config/user-dirs.dirs")
    if os.path.exists(xdg):
        with open(xdg,"r",encoding="utf-8") as f:
            for line in f:
                if line.startswith("XDG_DOWNLOAD_DIR"):
                    val = line.split("=",1)[1].strip().strip('"')
                    val = val.replace("$HOME", os.path.expanduser("~"))
                    return val
    return os.path.expanduser("~/Downloads")

def _notify(summary: str, body: str = ""):
    if shutil.which("notify-send"):
        try: subprocess.Popen(["notify-send", summary, body])
        except Exception: pass
    else:
        try: print("\a", end="", flush=True)
        except Exception: pass

# ---------- Canvas fetch ----------
def fetch_planner_items_window() -> List[Dict[str, Any]]:
    now = dt.datetime.now(ZoneInfo(USER_TZ))
    start = _iso(now - dt.timedelta(hours=PAST_HOURS))
    end = _iso((now + dt.timedelta(days=DAYS_AHEAD)).replace(hour=23, minute=59, second=59, microsecond=0))
    url = urljoin(BASE_URL, "/api/v1/planner/items")
    params = {"start_date": start, "end_date": end, "per_page": 100}
    return get_all(url, params)

def fetch_course_name(course_id: int) -> Tuple[str, str]:
    url = urljoin(BASE_URL, f"/api/v1/courses/{course_id}")
    r = S.get(url, timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        j = r.json()
        return j.get("course_code") or "", j.get("name") or ""
    return "", ""

def fetch_assignment_details(course_id: int, assignment_id: int) -> Dict[str, Any]:
    url = urljoin(BASE_URL, f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    r = S.get(url, timeout=HTTP_TIMEOUT); r.raise_for_status()
    return r.json()

def fetch_submission(course_id: int, assignment_id: int) -> Optional[Dict[str, Any]]:
    url = urljoin(BASE_URL, f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self")
    r = S.get(url, timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        return r.json()
    return None

def fetch_discussion_or_announcement(course_id: int, topic_id: int) -> Optional[Dict[str, Any]]:
    url = urljoin(BASE_URL, f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}")
    r = S.get(url, params={"include[]": ["all_dates", "sections", "sections_user_count"]}, timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        return r.json()
    return None

def fetch_course_syllabus(course_id: int) -> Optional[str]:
    url = urljoin(BASE_URL, f"/api/v1/courses/{course_id}")
    r = S.get(url, params={"include[]": "syllabus_body"}, timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        return (r.json() or {}).get("syllabus_body")
    return None

def search_course_files(course_id: int, term: str) -> List[Dict[str, Any]]:
    url = urljoin(BASE_URL, f"/api/v1/courses/{course_id}/files")
    params = {"search_term": term, "per_page": 50}
    try:
        return get_all(url, params)
    except Exception:
        return []

def fetch_current_courses() -> Dict[int, Tuple[str, str]]:
    url = urljoin(BASE_URL, "/api/v1/courses")
    params = {"enrollment_state": "active", "per_page": 100}
    courses = get_all(url, params)
    out: Dict[int, Tuple[str, str]] = {}
    for c in courses:
        cid = c.get("id")
        if cid:
            out[int(cid)] = (c.get("course_code") or str(cid), c.get("name") or "")
    return out

def fetch_announcements_window(course_ids: List[int]) -> List[Dict[str, Any]]:
    now = dt.datetime.now(ZoneInfo(USER_TZ))
    start = _iso(now - dt.timedelta(days=ANN_PAST_DAYS))
    end = _iso((now + dt.timedelta(days=ANN_FUTURE_DAYS)).replace(hour=23, minute=59, second=59, microsecond=0))
    url = urljoin(BASE_URL, "/api/v1/announcements")
    params: Dict[str, Any] = {"start_date": start, "end_date": end, "per_page": 100}
    params["context_codes[]"] = [f"course_{cid}" for cid in course_ids]
    return get_all(url, params)

# ---------- Keys ----------
def stable_item_key(course_id, plannable_id, ptype) -> str:
    return f"{int(course_id) if course_id else ''}:{int(plannable_id) if plannable_id else ''}:{(ptype or '').lower()}"

def item_key_legacy(course_id, plannable_id, ptype, title) -> str:
    return f"{course_id}:{plannable_id}:{ptype}:{abs(hash(title))}"

def migrate_visibility_keys_if_needed(items: List[Dict[str, Any]]):
    vis = STATE.get("visibility", {})
    moved = 0
    for it in items:
        legacy = it.get("_legacy_key")
        stable = it["key"]
        if legacy and legacy in vis and stable not in vis:
            vis[stable] = vis[legacy]
            moved += 1
    if moved:
        for it in items:
            lk = it.get("_legacy_key")
            if lk and lk in vis:
                vis.pop(lk, None)
        STATE["visibility"] = vis
        _save_state(STATE)

# ---------- Normalize ----------
def best_due(pl: Dict[str, Any], ptype: str) -> Optional[str]:
    for k in ("due_at","lock_at","todo_date","start_at","end_at","published_at","posted_at","created_at","available_at"):
        v = pl.get(k)
        if v: return v
    return None

def normalize_items(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    course_ids = sorted({x.get("course_id") for x in raw if x.get("course_id")})
    course_cache: Dict[int, Tuple[str, str]] = {}
    for cid in course_ids:
        try: course_cache[cid] = fetch_course_name(int(cid))
        except Exception: course_cache[cid] = ("","")

    out = []
    for x in raw:
        ptype = (x.get("plannable_type") or "").lower()
        pl = x.get("plannable") or {}
        if ptype == "discussion_topic" and (pl.get("is_announcement") or x.get("is_announcement") or pl.get("announcement")):
            ptype = "announcement"
        due_iso = best_due(pl, ptype) or ""
        due_local = _fmt_local(due_iso) if due_iso else ""
        rel = rel_time(local_dt(due_iso)) if due_iso else ""
        course_id = x.get("course_id")
        course_code, course_name = course_cache.get(course_id, ("",""))
        sub = x.get("submissions")
        flags = []
        if isinstance(sub, dict):
            for flag in ("missing","late","graded","excused","submitted","with_feedback","needs_grading"):
                if sub.get(flag) is True: flags.append(flag)
        url_abs = absolute_url(x.get("html_url","/"))
        points = pl.get("points_possible") if ptype=="assignment" else None
        title = pl.get("title") or pl.get("name") or "(untitled)"
        legacy_key = item_key_legacy(course_id, x.get("plannable_id"), ptype, title)
        key = stable_item_key(course_id, x.get("plannable_id"), ptype)
        out.append({
            "key": key,
            "_legacy_key": legacy_key,
            "ptype": ptype,
            "title": title,
            "course_code": course_code or str(course_id or ""),
            "course_name": course_name,
            "due_at": due_local,
            "due_rel": rel,
            "due_iso": due_iso,
            "url": url_abs,
            "course_id": course_id,
            "plannable_id": x.get("plannable_id"),
            "points": points,
            "status_flags": flags,
            "raw_plannable": pl,
        })

    def sortkey(it):
        try: return dt.datetime.strptime(it["due_at"], "%m/%d/%Y %H:%M")
        except Exception: return dt.datetime.max
    out.sort(key=sortkey)
    return out

def normalize_announcements(raw: List[Dict[str, Any]], course_cache: Dict[int, Tuple[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in raw:
        course_id = a.get("course_id")
        if not course_id:
            m = re.search(r"course_(\d+)", str(a.get("context_code","")))
            if m: course_id = int(m.group(1))
        code, name = course_cache.get(course_id, ("", ""))
        title = a.get("title") or (a.get("message") or "").strip()[:60] or "(announcement)"
        ts = a.get("posted_at") or a.get("delayed_post_at") or a.get("created_at") or ""
        url_abs = absolute_url(a.get("html_url") or a.get("url") or "/")
        out.append({
            "key": stable_item_key(course_id, a.get("id"), "announcement"),
            "ptype": "announcement",
            "title": title,
            "course_code": code or str(course_id or ""),
            "course_name": name,
            "due_at": _fmt_local(ts) if ts else "",
            "due_rel": rel_time(local_dt(ts)) if ts else "",
            "due_iso": ts,
            "url": url_abs,
            "course_id": course_id,
            "plannable_id": a.get("id"),
            "points": None,
            "status_flags": [],
            "raw_plannable": a,
        })
    # newest first
    def sortkey(it):
        try: return dt.datetime.strptime(it["due_at"], "%m/%d/%Y %H:%M")
        except Exception: return dt.datetime.min
    out.sort(key=sortkey, reverse=True)
    return out

# ---------- Warm cache helpers ----------
def _serialize_simple(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    keep = ("key","ptype","title","course_code","course_name","due_at","due_rel","due_iso","url","course_id","plannable_id","points","status_flags","raw_plannable")
    out = []
    for it in items:
        out.append({k: it.get(k) for k in keep})
    return out

def _fetch_all_data_sync() -> Tuple[Dict[int, Tuple[str,str]], List[Dict[str,Any]], List[Dict[str,Any]]]:
    course_cache = fetch_current_courses()
    raw = fetch_planner_items_window()
    all_items = normalize_items(raw)
    items = [it for it in all_items if it["ptype"] not in ("announcement","calendar_event","planner_note")]
    items = CanvasTUI._apply_past_filter_static(items)
    ann_raw = []
    try:
        ann_raw = fetch_announcements_window(list(course_cache.keys()))
    except Exception:
        ann_raw = []
    announcements = normalize_announcements(ann_raw, course_cache)
    return course_cache, items, announcements

# ---------- TUI ----------
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Input, Button, RichLog
from textual.containers import Horizontal, Vertical
from textual.screen import Screen, ModalScreen
from textual.events import Key

# --- Modal prompts ---
class InputPrompt(ModalScreen[str]):
    BINDINGS = [("enter","accept","OK"), ("escape","cancel","Cancel")]
    def __init__(self, title: str, placeholder: str = "", default: str = ""):
        super().__init__()
        self._title = title; self._placeholder = placeholder; self._default = default
    def compose(self) -> ComposeResult:
        yield Static(self._title, id="prompt-title")
        self.inp = Input(placeholder=self._placeholder, value=self._default, id="prompt-input")
        yield self.inp
        with Horizontal(id="prompt-buttons"):
            yield Button("OK", id="ok")
            yield Button("Cancel", id="cancel")
    def on_mount(self): self.inp.focus()
    def on_button_pressed(self, ev: Button.Pressed):
        self.dismiss(self.inp.value.strip() if ev.button.id == "ok" else "")
    def on_input_submitted(self, _ev: Input.Submitted):
        self.dismiss(self.inp.value.strip())
    def action_accept(self): self.dismiss(self.inp.value.strip())
    def action_cancel(self): self.dismiss("")

class ConfirmPath(ModalScreen[Tuple[bool, str]]):
    BINDINGS = [("enter","accept","Download"), ("escape","cancel","Cancel")]
    def __init__(self, msg: str, default_path: str):
        super().__init__(); self.msg = msg; self.default_path = default_path
    def compose(self) -> ComposeResult:
        yield Static(self.msg)
        self.inp = Input(value=self.default_path); yield self.inp
        with Horizontal():
            yield Button("Download", id="yes"); yield Button("Cancel", id="no")
    def on_mount(self): self.inp.focus()
    def on_button_pressed(self, ev: Button.Pressed):
        self.dismiss((ev.button.id == "yes", self.inp.value.strip() if ev.button.id == "yes" else ""))
    def on_input_submitted(self, _ev: Input.Submitted):
        self.dismiss((True, self.inp.value.strip()))
    def action_accept(self): self.dismiss((True, self.inp.value.strip()))
    def action_cancel(self): self.dismiss((False, ""))

class LoadingScreen(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        yield Static("[b]Loading Canvas data…[/b]\n[dim]Please wait[/dim]")

# --- Details Screen (assignments/discussions generic) ---
class DetailsScreen(Screen):
    BINDINGS = [("backspace", "pop", "Back"), ("escape","pop","Back"), ("w", "download", "Download"), ("enter", "open", "Open")]
    def __init__(self, owner_app, item: Dict[str, Any]):
        super().__init__()
        self._owner = owner_app
        self.item = item
        self.links: List[Tuple[str,str]] = []
        self._loaded = False
    def compose(self) -> ComposeResult:
        with Vertical():
            self.head = Static(id="d-head"); yield self.head
            self.body = RichLog(highlight=True, wrap=True, id="d-body"); yield self.body
            self.link_table = DataTable(zebra_stripes=True, id="d-links"); yield self.link_table
            yield Footer()
    def on_mount(self):
        it = self.item
        self.head.update(f"[b]{it['title']}[/b] ({it['course_code']} — {it['course_name']})")
        self.link_table.clear(columns=True); self.link_table.add_columns("Label","URL")
        self.body.write("[dim]Loading details…[/dim]")
        threading.Thread(target=self._load_details, daemon=True).start()
    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop(); self.app.pop_screen()
    def _load_details(self):
        it = self.item
        ad = sub = disc = None
        try:
            if it["ptype"] == "assignment" and it["course_id"] and it["plannable_id"]:
                ad = fetch_assignment_details(int(it["course_id"]), int(it["plannable_id"]))
                sub = fetch_submission(int(it["course_id"]), int(it["plannable_id"]))
            elif it["ptype"] in ("discussion","discussion_topic","announcement") and it["course_id"] and it["plannable_id"]:
                disc = fetch_discussion_or_announcement(int(it["course_id"]), int(it["plannable_id"]))
        except Exception:
            pass
        self.app.call_from_thread(self._render_details, ad, sub, disc)
    def _render_details(self, ad, sub, disc):
        self.body.clear(); self.link_table.clear(columns=True); self.link_table.add_columns("Label","URL")
        it = self.item
        due = it["due_at"] or "-"; rel = it["due_rel"] or "-"; pts = it["points"] if it["points"] is not None else "-"
        score_line = ""
        if sub and sub.get("score") is not None and it["points"]:
            sc = float(sub.get("score")); pct = (100.0*sc/float(it["points"])) if it["points"] else 0.0
            score_line = f" • Score: {sc:.2f}/{float(it['points']):.2f} ({pct:.0f}%)"
        self.links = [("Open in browser", it["url"])]
        lines = [f"Type: {it['ptype']} • When: {due} ({rel}) • Points: {pts}{score_line}",
                 f"Status: {', '.join(it['status_flags']) if it['status_flags'] else '-'}",
                 f"URL: {it['url']}"]
        if ad:
            desc = (ad.get("description") or "").replace("\r","").replace("<br>","\n").replace("<br/>","\n")
            desc = re.sub(r"<[^>]+>", "", desc)
            if desc: lines += ["", desc]
            for a in ad.get("attachments",[]) or []:
                lbl = a.get("display_name") or a.get("filename") or "file"
                url = a.get("url") or a.get("download_url") or a.get("href") or ""
                if url: self.links.append((lbl, url))
        if disc:
            msg_html = disc.get("message") or ""
            text = re.sub(r"<[^>]+>", "", msg_html.replace("<br>","\n").replace("<br/>","\n"))
            if text: lines += ["", text]
            for a in (disc.get("attachments") or []):
                lbl = a.get("display_name") or a.get("filename") or "file"
                url = a.get("url") or a.get("download_url") or a.get("html_url") or ""
                if url: self.links.append((lbl, url))
        for lab, url in self.links: self.link_table.add_row(lab, url)
        self.body.write("\n".join(lines))
        if self.links:
            try: self.link_table.cursor_coordinate=(0,0)
            except Exception: pass
        self._loaded = True
    def _selected_link(self) -> Optional[str]:
        if self.link_table.cursor_row is None or not self.links: return None
        return self.links[self.link_table.cursor_row][1]
    def action_open(self):
        url = self._selected_link() or self.item.get("url")
        if not url: return
        try: webbrowser.open(url, new=2)
        except Exception: pass
    def action_download(self):
        if not self._loaded: return
        self._owner._async_download_from_links(self.item, self.links)  # type: ignore
    def action_pop(self): self.app.pop_screen()

# --- Syllabus Screen (single-line list + right preview) ---
class SyllabiScreen(Screen):
    # Use unique action name to avoid App's Enter binding
    BINDINGS = [("backspace", "pop", "Back"), ("escape","pop","Back"),
                ("enter", "syl_open", "Preview/View"), ("w", "save", "Save"),
                ("b","browser","Open in browser"), ("v","view_native","Open native viewer")]
    def __init__(self, owner_app, courses: Dict[int, Tuple[str,str]]):
        super().__init__(); self._owner = owner_app
        self.courses=courses
        self.curr_id: Optional[int]=None
        self.curr_html: Optional[str]=None
        self.curr_file: Optional[Dict[str,Any]]=None
        self.curr_preview_text: Optional[str]=None
        self.curr_browser_url: Optional[str]=None
        self._row_to_cid: List[int] = []
        self.body: Optional[RichLog] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="syl-root"):
            with Horizontal(id="syl-split"):
                self.table = DataTable(zebra_stripes=True, id="syl-list"); yield self.table
                # stable wrapper; child RichLog is ephemeral, no id to avoid DuplicateIds
                self.preview = Vertical(id="syl-preview"); yield self.preview
            yield Footer()

    def on_mount(self):
        self.table.clear(columns=True)
        self.table.add_columns("Course")
        self.table.cursor_type = "row"
        self._row_to_cid.clear()
        for cid,(code,name) in sorted(self.courses.items(), key=lambda kv: (kv[1][0], kv[0])):
            self.table.add_row(f"{code or cid} — {name or ''}")
            self._row_to_cid.append(cid)
        try: self.table.cursor_coordinate=(0,0)
        except Exception: pass
        cid = self._selected_course()
        if cid is not None:
            self._open_async(int(cid))

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop(); self.app.pop_screen()

    def _container(self) -> Vertical:
        return self.query_one("#syl-preview", Vertical)

    def _reset_preview(self):
        cont = self._container()
        try:
            for child in list(cont.children):
                child.remove()
        except Exception:
            pass
        self.body = RichLog(highlight=True, wrap=True)
        cont.mount(self.body)

    def _selected_course(self) -> Optional[int]:
        row = self.table.cursor_row
        if row is None: return None
        if 0 <= row < len(self._row_to_cid):
            return self._row_to_cid[row]
        return None

    def _render_text(self, text: str):
        self._reset_preview()
        assert self.body is not None
        self.body.write(text)

    def _pdftotext_available(self) -> bool:
        return shutil.which("pdftotext") is not None

    def _preview_pdf_from_url(self, url: str):
        def worker():
            try:
                with S.get(url, timeout=HTTP_TIMEOUT) as r:
                    r.raise_for_status()
                    data = r.content
                if not self._pdftotext_available():
                    msg = "(pdftotext not found; press 'b' to open in browser or 'w' to save.)"
                else:
                    with tempfile.NamedTemporaryFile(prefix="canvas_syl_", suffix=".pdf", delete=False) as f:
                        f.write(data); pdf_path = f.name
                    txt_path = pdf_path + ".txt"
                    try:
                        subprocess.run(["pdftotext","-layout", pdf_path, txt_path], check=False, timeout=10)
                        if os.path.exists(txt_path):
                            with open(txt_path, "r", encoding="utf-8", errors="ignore") as tf:
                                msg = tf.read().strip() or "(empty text after conversion)"
                        else:
                            msg = "(conversion failed)"
                    finally:
                        try: os.remove(pdf_path)
                        except Exception: pass
                        try: os.remove(txt_path)
                        except Exception: pass
                self.app.call_from_thread(self._render_text, msg)
            except Exception as e:
                self.app.call_from_thread(self._render_text, f"(preview failed: {e})")
        threading.Thread(target=worker, daemon=True).start()

    def _open_async(self, cid: int):
        self._render_text("[dim]Loading syllabus…[/dim]")
        def worker():
            html = None; files = []
            try: html = fetch_course_syllabus(int(cid)) or ""
            except Exception: html = ""
            if html and html.strip():
                text = re.sub(r"<[^>]+>", "", html.replace("<br>","\n").replace("<br/>","\n"))
                self.curr_id = cid; self.curr_html = html; self.curr_file = None; self.curr_preview_text = text; self.curr_browser_url = None
                self.app.call_from_thread(self._render_text, text or "(syllabus HTML empty)")
                return
            try:
                cand: Dict[int, Dict[str,Any]] = {}
                for term in ("syllab", "syllabus", "outline"):
                    for f in search_course_files(int(cid), term):
                        fid = f.get("id")
                        if fid is not None: cand[fid] = f
                files = list(cand.values())
                def is_pdf(f):
                    ct = str(f.get("content-type","")).lower()
                    name = (f.get("display_name") or f.get("filename") or "").lower()
                    return ct.endswith("pdf") or name.endswith(".pdf")
                def name_lc(f): return (f.get("display_name") or f.get("filename") or "").lower()
                files.sort(key=lambda f: (not is_pdf(f), "syllab" not in name_lc(f), -(f.get("size") or 0)))
            except Exception:
                files = []
            if not files:
                self.app.call_from_thread(self._render_text, "(No syllabus HTML and no matching files.)"); return
            f0 = files[0]
            name = f0.get("display_name") or f0.get("filename") or "syllabus.pdf"
            url = f0.get("download_url") or f0.get("url") or f0.get("html_url")
            text = f"Found file: {name} ({(f0.get('size') or 0)/1_000_000:.2f} MB)\nPress Enter to preview (PDF→text) or 'b' to open in browser; 'w' to save."
            self.curr_id = cid; self.curr_file = f0; self.curr_html=None; self.curr_preview_text=None; self.curr_browser_url = url
            self.app.call_from_thread(self._render_text, text)
        threading.Thread(target=worker, daemon=True).start()

    # New action name bound to Enter
    def action_syl_open(self):
        cid = self._selected_course()
        if cid is not None and cid != self.curr_id:
            self._open_async(int(cid)); return
        if self.curr_browser_url:
            self._render_text("[dim]Downloading + converting PDF…[/dim]")
            self._preview_pdf_from_url(self.curr_browser_url)

    # Keep for 'w' binding etc.
    def action_save(self):
        if self.curr_html and self.curr_id:
            code,_ = self.courses.get(self.curr_id,("", "Course"))
            dstdir = os.path.join(get_download_dir(), "Canvas", sanitize(code or str(self.curr_id))); os.makedirs(dstdir, exist_ok=True)
            path = os.path.join(dstdir, "Syllabus.html")
            with open(path, "w", encoding="utf-8") as f: f.write(self.curr_html)
            if OPEN_AFTER_DL and shutil.which("xdg-open"): subprocess.Popen(["xdg-open", path])
            assert self.body is not None
            self.body.write(f"\nSaved → {path}")
            return
        if self.curr_file and self.curr_id and self.curr_browser_url:
            code,_ = self.courses.get(self.curr_id,("", "Course"))
            dstdir = os.path.join(get_download_dir(), "Canvas", sanitize(code or str(self.curr_id))); os.makedirs(dstdir, exist_ok=True)
            name = self.curr_file.get("display_name") or self.curr_file.get("filename") or "syllabus.pdf"
            path = os.path.join(dstdir, sanitize(name))
            def worker():
                try:
                    with S.get(self.curr_browser_url, stream=True, timeout=HTTP_TIMEOUT) as resp:
                        resp.raise_for_status()
                        with open(path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=65536):
                                if chunk: f.write(chunk)
                    if OPEN_AFTER_DL and shutil.which("xdg-open"): subprocess.Popen(["xdg-open", path])
                    self.app.call_from_thread(lambda: (self.body and self.body.write(f"\nSaved → {path}")))
                except Exception as e:
                    self.app.call_from_thread(lambda: (self.body and self.body.write(f"\nDownload failed: {e}")))
            threading.Thread(target=worker, daemon=True).start()

    def action_browser(self):
        if self.curr_browser_url:
            try: webbrowser.open(self.curr_browser_url, new=2)
            except Exception: pass
        elif self.curr_html and self.curr_id:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as f:
                f.write(self.curr_html); p=f.name
            try: webbrowser.open(f"file://{p}", new=2)
            except Exception: pass

    def action_view_native(self):
        if not self.curr_browser_url: return
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                r = S.get(self.curr_browser_url, timeout=HTTP_TIMEOUT); r.raise_for_status()
                f.write(r.content); p = f.name
            if shutil.which("xdg-open"): subprocess.Popen(["xdg-open", p])
        except Exception:
            pass

    def on_data_table_cursor_moved(self, _event):
        cid = self._selected_course()
        if cid is not None and cid != self.curr_id:
            self._open_async(int(cid))

# --- Announcements list (single pane) ---
class AnnouncementsScreen(Screen):
    # unique action name to avoid App 'enter' binding collision
    BINDINGS = [("backspace","pop","Back"), ("escape","pop","Back"),
                ("enter","ann_open","Open"), ("o","open_in_browser","Open in browser"),
                ("w","download","Download attachments")]
    def __init__(self, owner_app, announcements: List[Dict[str,Any]]):
        super().__init__(); self._owner = owner_app; self._anns = announcements

    def compose(self) -> ComposeResult:
        with Vertical(id="ann-root"):
            self.table = DataTable(zebra_stripes=True, id="ann-table"); yield self.table
            yield Footer()

    def on_mount(self):
        self.table.clear(columns=True)
        self.table.add_columns("Announcement")
        self.table.cursor_type = "row"
        for it in self._anns:
            self.table.add_row(self._fmt_row(it))
        try: self.table.cursor_coordinate=(0,0)
        except Exception: pass
        self.table.focus()

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.stop(); self.action_ann_open()
        elif event.key == "backspace":
            event.stop(); self.app.pop_screen()

    def _fmt_row(self, it: Dict[str, Any]) -> str:
        when = it.get("due_at") or "-"
        rel  = f" ({it.get('due_rel')})" if it.get("due_rel") else ""
        code = it.get("course_code") or ""
        title = it.get("title") or "(announcement)"
        return f"{when} — {code} — {title}{rel}"

    def _sel(self) -> Optional[Dict[str,Any]]:
        row = self.table.cursor_row
        if row is None: return None
        if 0 <= row < len(self._anns): return self._anns[row]
        return None

    def action_ann_open(self):
        it = self._sel()
        if not it: return
        self.app.push_screen(AnnouncementDetailScreen(self._owner, it))

    def action_open_in_browser(self):
        it = self._sel()
        if not it: return
        try: webbrowser.open(it.get("url",""), new=2)
        except Exception: pass

    def action_download(self):
        it = self._sel()
        if not it: return
        self._owner._async_gather_attachments(it)

# --- Announcements detail (full content) ---
class AnnouncementDetailScreen(Screen):
    BINDINGS = [("backspace","pop","Back"), ("escape","pop","Back"),
                ("o","open_in_browser","Open in browser"), ("w","download","Download attachments")]
    def __init__(self, owner_app, item: Dict[str,Any]):
        super().__init__(); self._owner = owner_app; self.item = item
        self.links: List[Tuple[str,str]] = []
    def compose(self) -> ComposeResult:
        with Vertical():
            self.head = Static(id="a-head"); yield self.head
            self.body = RichLog(highlight=True, wrap=True, id="a-body"); yield self.body
            self.link_table = DataTable(zebra_stripes=True, id="a-links"); yield self.link_table
            yield Footer()
    def on_mount(self):
        it = self.item
        self.head.update(f"[b]{it['title']}[/b]\n{it['course_code']} — {it['course_name']}\n{it.get('due_at') or '-'} ({it.get('due_rel') or '-'})")
        self.body.write("[dim]Loading announcement…[/dim]")
        self.link_table.clear(columns=True); self.link_table.add_columns("Label","URL")
        threading.Thread(target=self._load, daemon=True).start()
    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop(); self.app.pop_screen()
    def _load(self):
        it = self.item
        disc = None
        try:
            if it["course_id"] and it["plannable_id"]:
                disc = fetch_discussion_or_announcement(int(it["course_id"]), int(it["plannable_id"]))
        except Exception:
            pass
        def render():
            self.body.clear()
            text = ""
            if disc:
                msg_html = disc.get("message") or ""
                text = re.sub(r"<[^>]+>", "", msg_html.replace("<br>","\n").replace("<br/>","\n")).strip()
                for a in (disc.get("attachments") or []):
                    lbl = a.get("display_name") or a.get("filename") or "file"
                    url = a.get("url") or a.get("download_url") or a.get("html_url") or ""
                    if url: self.links.append((lbl, url))
            if not text:
                text = "(No body content.)"
            self.body.write(text)
            self.links = [("Open in browser", it["url"])] + self.links
            self.link_table.clear(columns=True); self.link_table.add_columns("Label","URL")
            for lab, url in self.links: self.link_table.add_row(lab, url)
            try: self.link_table.cursor_coordinate=(0,0)
            except Exception: pass
        self.app.call_from_thread(render)
    def action_open_in_browser(self):
        try:
            webbrowser.open(self.item.get("url",""), new=2)
        except Exception:
            pass
    def action_download(self):
        files = [(lab,url,0) for (lab,url) in self.links if lab != "Open in browser"]
        if not files:
            return
        dstdir_default = os.path.join(get_download_dir(), "Canvas", sanitize(self.item.get("course_code","")), sanitize(self.item.get("title","announcement")))
        self._owner._show_confirm_path(f"{len(files)} attachment(s) detected. Confirm download directory (Enter to accept):",
                                       dstdir_default, "dl_dir",
                                       {"files": files, "default": dstdir_default, "item": self.item})

# ---------- App ----------
class Info(Static): pass
class Details(Static): pass

class Pomodoro(Static):
    def __init__(self, on_state_change=None):
        super().__init__(id="pomodoro")
        self._timer_lock = threading.Lock()
        self._end_ts: Optional[float] = None
        self._ticker_thread: Optional[threading.Thread] = None
        self._stop = False
        self._on_state_change = on_state_change
        self.update("[dim]Pomodoro: stopped[/dim]")

    def start(self, minutes: int):
        with self._timer_lock:
            self._end_ts = time.time() + max(1, int(minutes))*60
            self._stop = False
            if self._on_state_change: self._on_state_change(self._end_ts)
            if not self._ticker_thread or not self._ticker_thread.is_alive():
                self._ticker_thread = threading.Thread(target=self._run, daemon=True)
                self._ticker_thread.start()
            else:
                self._safe_update(self.render_status())

    def resume_until(self, end_ts: float):
        with self._timer_lock:
            self._end_ts = float(end_ts)
            self._stop = False
            if not self._ticker_thread or not self._ticker_thread.is_alive():
                self._ticker_thread = threading.Thread(target=self._run, daemon=True)
                self._ticker_thread.start()
            self._safe_update(self.render_status())

    def stop(self):
        with self._timer_lock:
            self._end_ts = None
            self._stop = True
            if self._on_state_change: self._on_state_change(None)
            self._safe_update("[dim]Pomodoro: stopped[/dim]")

    def _safe_update(self, text: str):
        try:
            self.app.call_from_thread(self.update, text)
        except Exception:
            try: self.update(text)
            except Exception: pass

    def render_status(self) -> str:
        if self._end_ts is None:
            return "[dim]Pomodoro: stopped[/dim]"
        remaining = max(0, int(self._end_ts - time.time()))
        m, s = divmod(remaining, 60)
        total = max(1, int(self._end_ts - (time.time() - remaining)))
        bar_len = 28
        filled = int(bar_len * (1 - remaining / total))
        bar = "█"*filled + "░"*(bar_len-filled)
        return f"Pomodoro: {m:02d}:{s:02d}  {bar}"

    def _run(self):
        while True:
            with self._timer_lock:
                if self._stop:
                    self._safe_update("[dim]Pomodoro: stopped[/dim]"); break
                text = self.render_status()
                if "Pomodoro: 00:00" in text:
                    self._safe_update("[green]Pomodoro done[/green]")
                    _notify("Pomodoro", "Time is up.")
                    self._end_ts=None
                    if self._on_state_change: self._on_state_change(None)
                    break
                self._safe_update(text)
            time.sleep(1)

class CanvasTUI(App):
    CSS = """
    Screen { layout: horizontal; }
    Horizontal { height: 1fr; }
    Vertical#left { width: 54; border: solid #555; }
    Vertical#right { height: 1fr; }
    DataTable { border: solid #555; }
    Static#info { padding: 1 2; }
    Static#details { padding: 1 2; border: solid #555; height: 12; }
    Static#pomodoro { padding: 1 2; border: solid #555; height: 6; }
    Static#progress { padding: 1 2; border: solid #555; height: 6; }

    /* Syllabi split */
    #syl-root { height: 1fr; width: 1fr; }
    #syl-split { layout: horizontal; height: 1fr; }
    #syl-list { width: 48; min-width: 32; max-width: 80; }
    #syl-preview { height: 1fr; overflow: auto; }

    /* Announcements full width */
    #ann-root { height: 1fr; width: 1fr; }
    #ann-table { width: 1fr; height: 1fr; }

    /* Detail bodies + link tables */
    #d-body, #a-body { height: 1fr; overflow: auto; }
    #d-links, #a-links { height: 8; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("o", "open", "Open in browser"),
        ("enter", "open_details", "Open details"),
        ("d", "quick_preview", "Quick details"),
        ("y", "yank_url", "Copy URL"),
        ("w", "download", "Download attachments"),
        ("c", "export_ics", "Export ICS"),
        ("C", "export_ics_and_import", "Export+calcurse -i"),
        ("ctrl+c", "export_ics_and_import", "Add all to calendar"),
        ("g", "open_course", "Open course"),
        ("/", "filter", "Filter"),
        ("x", "toggle_hide", "Hide/Unhide"),
        ("H", "toggle_show_hidden", "Show hidden"),
        ("1", "pomo30", "Pomodoro 30m"),
        ("2", "pomo60", "Pomodoro 1h"),
        ("3", "pomo120", "Pomodoro 2h"),
        ("P", "pomo_custom", "Pomodoro custom"),
        ("0", "pomo_stop", "Pomodoro stop"),
        ("S", "open_syllabi", "Syllabi"),
        ("A", "open_announcements", "Announcements"),
    ]

    def __init__(self):
        super().__init__()
        self.items: List[Dict[str, Any]] = []
        self.announcements: List[Dict[str,Any]] = []
        self.course_cache: Dict[int, Tuple[str,str]] = {}
        self.filtered: Optional[List[int]] = None
        self.show_hidden = False
        self.table: Optional[DataTable] = None
        self.info: Optional[Static] = None
        self.details: Optional[Static] = None
        self.pomo: Optional[Pomodoro] = None
        self._refresh_lock = threading.Lock()
        self._last_refresh = 0.0
        self._bg_refresh_thread: Optional[threading.Thread] = None
        self._stop_bg = False
        self._submission_cache: Dict[Tuple[int,int], Dict[str,Any]] = {}
        self._pending: Dict[int, Tuple[str, Dict[str,Any]]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                self.info = Static(id="info"); yield self.info
                self.details = Static(id="details"); yield self.details
                self.pomo = Pomodoro(on_state_change=self._persist_pomo); yield self.pomo
            with Vertical(id="right"):
                self.table = DataTable(zebra_stripes=True); yield self.table
                self.progress = Static(id="progress"); yield self.progress
        yield Footer()

    def _persist_pomo(self, end_ts: Optional[float]):
        STATE["pomo_end_ts"] = end_ts
        _save_state(STATE)

    # ---------- mount / teardown ----------
    def on_mount(self):
        self._setup_table()
        try:
            cached_items = STATE.get("cache_items") or []
            if cached_items:
                self.items = cached_items
                self._render_info(); self._render_table()
        except Exception:
            pass
        self.push_screen(LoadingScreen())
        self.call_later(self._initial_load)
        try:
            end_ts = STATE.get("pomo_end_ts")
            if isinstance(end_ts, (int,float)) and float(end_ts) > time.time():
                self.pomo.resume_until(float(end_ts))
        except Exception:
            pass
        if AUTO_REFRESH_SEC > 0:
            self._bg_refresh_thread = threading.Thread(target=self._bg_refresh_loop, daemon=True)
            self._bg_refresh_thread.start()

    def _initial_load(self):
        try:
            self.refresh_data()
        finally:
            try: self.pop_screen()
            except Exception: pass

    def on_unmount(self): self._stop_bg = True

    # ---------- table ----------
    def _setup_table(self):
        assert self.table is not None
        self.table.clear(columns=True)
        self.table.add_columns("Due","Rel","Type","Course","Title","Pts","Status")
        self.table.cursor_type = "row"; self.table.zebra_stripes = True

    # Only react to row selection from the MAIN table
    def on_data_table_row_selected(self, msg: DataTable.RowSelected) -> None:
        src = getattr(msg, "data_table", None) or getattr(msg, "control", None)
        if src is not self.table:
            return
        self.action_open_details()

    def on_key(self, event: Key) -> None:
        if event.key in ("1","2","3","0","P"):
            event.stop()
            if event.key == "1": self.action_pomo30()
            elif event.key == "2": self.action_pomo60()
            elif event.key == "3": self.action_pomo120()
            elif event.key == "0": self.action_pomo_stop()
            elif event.key == "P": self.action_pomo_custom()

    def _stats(self) -> Tuple[int,int,int,int]:
        total = len(self.items)
        now = dt.datetime.now(ZoneInfo(USER_TZ))
        today = now.strftime("%m/%d/%Y")
        def _is_overdue(it):
            if "submitted" in it["status_flags"]: return False
            return it["due_rel"].endswith("ago")
        due_today = sum(1 for it in self.items if it["due_at"].startswith(today))
        overdue = sum(1 for it in self.items if _is_overdue(it))
        submitted = sum(1 for it in self.items if "submitted" in it["status_flags"])
        return total, due_today, overdue, submitted

    def _render_info(self):
        now = dt.datetime.now(ZoneInfo(USER_TZ))
        total, due_today, overdue, submitted = self._stats()
        prog = f"{submitted}/{total}" if total else "0/0"
        s = (
            f"[b]Canvas TODO (next {DAYS_AHEAD}d; past {PAST_HOURS}h if unsubmitted)[/b]\n"
            f"{BASE_URL}\n"
            f"[dim]{now.strftime('%m/%d/%Y %H:%M %Z')}[/dim]\n"
            f"Items: {total} • Today: {due_today} • Overdue: {overdue} • Submitted: {submitted} (progress {prog})\n"
            f"Keys: ↑/↓ move • Enter open • d quick • o open • w download • y copy URL • c/C export ICS • / filter • x hide • H show hidden • A announcements • S syllabi • r refresh • q quit"
        )
        self.info.update(s)

    def _visible_items(self) -> List[Dict[str, Any]]:
        base = self.items
        if not self.show_hidden:
            base = [it for it in base if STATE["visibility"].get(it["key"], 0) != 2]
        if self.filtered is None: return base
        idxs = self.filtered
        return [base[i] for i in range(len(base)) if i in idxs]

    def _color_for_item(self, it: Dict[str,Any]) -> str:
        if "submitted" in it["status_flags"]: return "green"
        if not it["due_iso"]: return "white"
        now = dt.datetime.now(ZoneInfo(USER_TZ))
        due = local_dt(it["due_iso"]); delta_h = (due - now).total_seconds()/3600.0
        if delta_h < 0: return "red"
        if delta_h <= 8: return "orange1"
        if delta_h <= 12: return "yellow1"
        if delta_h <= 24: return "green"
        if delta_h <= 48: return "cyan"
        return "white"

    def _pts_cell(self, it: Dict[str,Any]) -> str:
        pts = it["points"]
        if "graded" in it["status_flags"] and it["course_id"] and it["plannable_id"] and pts:
            key = (int(it["course_id"]), int(it["plannable_id"]))
            sub = self._submission_cache.get(key)
            if not sub:
                try: sub = fetch_submission(*key)
                except Exception: sub = None
                if sub: self._submission_cache[key] = sub
            if sub and sub.get("score") is not None:
                sc = float(sub.get("score")); pct = (100.0*sc/float(pts)) if pts else 0.0
                return f"{sc:.0f}/{float(pts):.0f} ({pct:.0f}%)"
        return f"{pts:.0f}" if isinstance(pts, (int,float)) else "-"

    def _apply_past_filter(self, items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
        now = dt.datetime.now(ZoneInfo(USER_TZ))
        cutoff = now - dt.timedelta(hours=PAST_HOURS)
        out = []
        for it in items:
            if it["ptype"] == "announcement":
                continue
            ts_iso = it["due_iso"]
            if not ts_iso:
                rp = it.get("raw_plannable") or {}
                ts_iso = rp.get("posted_at") or rp.get("created_at") or rp.get("available_at") or ""
            if not ts_iso:
                out.append(it)
                continue
            ts = local_dt(ts_iso)
            if ts >= cutoff:
                if ts < now and "submitted" in it["status_flags"]:
                    continue
                out.append(it)
        return out

    @staticmethod
    def _apply_past_filter_static(items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
        now = dt.datetime.now(ZoneInfo(USER_TZ))
        cutoff = now - dt.timedelta(hours=PAST_HOURS)
        out = []
        for it in items:
            if it["ptype"] in ("announcement","calendar_event","planner_note"):
                continue
            rp = it.get("raw_plannable") or {}
            ts_iso = it.get("due_iso") or rp.get("posted_at") or rp.get("created_at") or rp.get("available_at") or ""
            if not ts_iso:
                out.append(it)
                continue
            ts = local_dt(ts_iso)
            lock_at = rp.get("lock_at")
            if lock_at:
                try:
                    if "missing" in it.get("status_flags", []) and local_dt(lock_at) < now:
                        continue
                except Exception:
                    pass
            if ts >= cutoff:
                if ts < now and "submitted" in it.get("status_flags", []):
                    continue
                out.append(it)
        return out

    def _render_table(self):
        assert self.table is not None
        self.table.clear()
        for it in self._visible_items():
            tcell = f"[{self._color_for_item(it)}]{it['ptype']}[/]"
            vis = STATE["visibility"].get(it["key"], 0)
            title = it["title"] if vis==0 else f"[dim]{it['title']}[/]"
            row = [it["due_at"] or "-", it["due_rel"] or "-", tcell, it["course_code"], title, self._pts_cell(it),
                   ", ".join(it["status_flags"]) if it["status_flags"] else "-"]
            self.table.add_row(*row)
        if self._visible_items():
            self.table.focus()
            try: self.table.cursor_coordinate = (0,0)
            except Exception: pass

    def _render_progress(self):
        total, _, _, submitted = self._stats()
        if not total:
            self.progress.update("[dim]Progress: 0/0[/dim]"); return
        pct = submitted / total
        slices = ["○","◔","◑","◕","●"]
        i = min(int(pct * (len(slices)-1) + 0.5), len(slices)-1)
        bar_len = 20
        filled = int(bar_len * pct)
        bar = "█"*filled + "░"*(bar_len-filled)
        self.progress.update(f"Progress: {submitted}/{total}  {slices[i]} {int(pct*100)}%\n[{bar}]")

    # ---------- refresh ----------
    def _bg_refresh_loop(self):
        while not self._stop_bg:
            time.sleep(AUTO_REFRESH_SEC)
            if self._stop_bg: break
            try: self.refresh_data(silent=True)
            except Exception: pass

    def action_refresh(self):
        now = time.time()
        if (now - self._last_refresh) < REFRESH_COOLDOWN:
            self.details.update(f"[yellow]Refresh ignored:[/yellow] cooldown {REFRESH_COOLDOWN:.1f}s"); return
        if self._refresh_lock.locked():
            self.details.update("[yellow]Refresh already in progress…[/yellow]"); return
        self.refresh_data()

    def refresh_data(self, silent: bool=False):
        if not self._refresh_lock.acquire(blocking=False): return
        if not silent:
            self.details.update("[dim]Refreshing…[/dim]")
        def worker():
            try:
                course_cache, items, announcements = _fetch_all_data_sync()
                migrate_visibility_keys_if_needed(items)
                def apply_ui():
                    self.course_cache = course_cache
                    self.items = items
                    self.announcements = announcements
                    self.filtered = None
                    self._submission_cache.clear()
                    STATE["cache_items"] = _serialize_simple(items)
                    STATE["cache_announcements"] = _serialize_simple(announcements)
                    _save_state(STATE)
                    self._render_info()
                    self._render_table()
                    if not silent:
                        self.details.update("[dim]Select an item and press Enter (full) or d (quick). Use A for announcements, S for syllabi.[/dim]")
                    self._last_refresh = time.time()
                    self._render_progress()
                self.call_from_thread(apply_ui)
            except Exception as e:
                self.call_from_thread(lambda: self.details.update(f"[red]Error:[/red] {e}"))
            finally:
                self._refresh_lock.release()
        threading.Thread(target=worker, daemon=True).start()

    def _selected_idx(self) -> Optional[int]:
        vis = self._visible_items()
        if not vis or not self.table: return None
        if self.table.cursor_row is None: return None
        return self.table.cursor_row

    def _selected_item(self) -> Optional[Dict[str,Any]]:
        vis = self._visible_items(); idx = self._selected_idx()
        if idx is None or idx >= len(vis): return None
        return vis[idx]

    # ---------- Prompt plumbing ----------
    def _show_input(self, title: str, placeholder: str, default: str, kind: str, ctx: Dict[str,Any]):
        scr = InputPrompt(title, placeholder, default); self._pending[id(scr)] = (kind, ctx); self.push_screen(scr)

    def _show_confirm_path(self, msg: str, default_path: str, kind: str, ctx: Dict[str,Any]):
        scr = ConfirmPath(msg, default_path); self._pending[id(scr)] = (kind, ctx); self.push_screen(scr)

    def on_screen_dismissed(self, event) -> None:
        entry = self._pending.pop(id(event.screen), None)
        if not entry: return
        kind, ctx = entry
        res = event.result
        if kind == "filter":
            needle = (res or "").strip().lower()
            if not needle:
                self.details.update("[dim]Filter cancelled[/dim]"); return
            base = self._visible_items()
            idxs = [i for i,it in enumerate(base) if needle in f"{it['title']} {it['course_code']} {it['ptype']}".lower()]
            self.filtered = idxs or None
            self._render_table()
            self.details.update(f"[dim]Filter:[/dim] '{needle}' → {len(self._visible_items())} items")
        elif kind == "pomo":
            try:
                mins = int(res)
                self.pomo.start(mins)
            except Exception:
                self.details.update("[yellow]Invalid minutes[/yellow]")
        elif kind == "dl_dir":
            ok, path = res if isinstance(res, tuple) else (False, "")
            if not ok:
                self.details.update("[dim]Download cancelled[/dim]"); return
            files = ctx["files"]; dstdir = path or ctx["default"]
            os.makedirs(dstdir, exist_ok=True)
            if not files:
                self.details.update("[yellow]No attachments detected[/yellow]"); return
            if len(files) >= 6:
                total_known = sum(sz for _,_,sz in files)
                human = f"{total_known/1_000_000:.1f} MB" if total_known else "unknown size"
                self._show_input(f"Download {len(files)} files (~{human})? Type YES to proceed:", "", "", "dl_many", {"files": files, "dir": dstdir})
            else:
                self._async_do_download(files, dstdir)
        elif kind == "dl_many":
            if (res or "").upper() != "YES":
                self.details.update("[dim]Download cancelled[/dim]"); return
            self._async_do_download(ctx["files"], ctx["dir"])

    # ---------- async helpers ----------
    def _async_download_from_links(self, item: Dict[str,Any], links: List[Tuple[str,str]]):
        files = [(lab, url, 0) for (lab, url) in links if lab != "Open in browser"]
        dstdir_default = os.path.join(get_download_dir(), "Canvas", sanitize(item["course_code"]), sanitize(item["title"]))
        msg = f"{len(files)} attachment(s) detected. Confirm download directory (Enter to accept):"
        self._show_confirm_path(msg, dstdir_default, "dl_dir", {"files": files, "default": dstdir_default, "item": item})

    def _async_gather_attachments(self, it: Dict[str,Any]):
        self.details.update("[dim]Scanning attachments…[/dim]")
        def worker():
            files: List[Tuple[str,str,int]] = []
            try:
                if it["ptype"] == "assignment" and it["course_id"] and it["plannable_id"]:
                    ad = fetch_assignment_details(int(it["course_id"]), int(it["plannable_id"]))
                    for a in ad.get("attachments",[]) or []:
                        name = a.get("display_name") or a.get("filename") or "file"
                        url = a.get("url") or a.get("download_url") or a.get("href")
                        size = int(a.get("size") or 0)
                        if url: files.append((name, url, size))
            except Exception:
                pass
            if not files:
                try:
                    r = S.get(it["url"], timeout=HTTP_TIMEOUT)
                    if r.ok:
                        for m in re.finditer(r'href="([^"]+)"', r.text):
                            href = m.group(1)
                            if "/files/" in href and "download" in href:
                                files.append((os.path.basename(urlparse(href).path) or "file", absolute_url(href), 0))
                except Exception:
                    pass
            dstdir_default = os.path.join(get_download_dir(), "Canvas", sanitize(it["course_code"]), sanitize(it["title"]))
            self.app.call_from_thread(self._show_confirm_path,
                                      f"{len(files)} attachment(s) detected. Confirm download directory (Enter to accept):",
                                      dstdir_default, "dl_dir",
                                      {"files": files, "default": dstdir_default, "item": it})
        threading.Thread(target=worker, daemon=True).start()

    def _async_do_download(self, files: List[Tuple[str,str,int]], dstdir: str):
        self.details.update("[dim]Downloading…[/dim]")
        def worker():
            okc, fail, total = 0, 0, 0
            for name, url, _size in files:
                fname = os.path.join(dstdir, sanitize(name))
                try:
                    with S.get(url, stream=True, timeout=HTTP_TIMEOUT) as resp:
                        resp.raise_for_status()
                        with open(fname, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=65536):
                                if chunk: f.write(chunk); total += len(chunk)
                    okc += 1
                    if OPEN_AFTER_DL and shutil.which("xdg-open"): subprocess.Popen(["xdg-open", fname])
                except Exception:
                    fail += 1
            self.app.call_from_thread(self.details.update, f"[green]Downloaded {okc}[/green], [red]{fail} failed[/red] → {dstdir}  (total {total/1_000_000:.2f} MB)")
        threading.Thread(target=worker, daemon=True).start()

    # ---------- actions ----------
    def action_open(self):
        it = self._selected_item()
        if not it: return
        try: webbrowser.open(it["url"], new=2)
        except Exception: pass

    def action_quick_preview(self):
        it = self._selected_item()
        if not it: return
        pts = "-" if it["points"] is None else f"{it['points']:.0f}"
        s = (
            f"[b]{it['title']}[/b]\n"
            f"{it['course_code']} — {it['course_name']}\n"
            f"Type: {it['ptype']} • Due: {it['due_at'] or '-'} ({it['due_rel'] or '-'}) • Points: {pts}\n"
            f"Status: {', '.join(it['status_flags']) if it['status_flags'] else '-'}\n"
            f"URL: {it['url']}"
        )
        self.details.update(s)

    def action_open_details(self):
        it = self._selected_item()
        if not it: return
        self.push_screen(DetailsScreen(self, it))

    def action_yank_url(self):
        it = self._selected_item()
        if not it: return
        url = it["url"]; copied = False
        for cmd in (("xclip","-selection","clipboard"),("wl-copy",)):
            if shutil.which(cmd[0]):
                try:
                    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    p.communicate(url.encode("utf-8"), timeout=2)
                    if p.returncode == 0: copied=True; break
                except Exception: pass
        self.details.update("[green]Copied URL[/green]" if copied else f"[yellow]Copy failed[/yellow]: {url}")

    def action_download(self):
        it = self._selected_item()
        if not it: return
        self._async_gather_attachments(it)

    def _ics_escape(self, s: str) -> str:
        return s.replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")

    def _ics_event_for_item(self, it: Dict[str,Any]) -> Optional[str]:
        if not it["due_iso"]: return None
        due = local_dt(it["due_iso"]); start = due - dt.timedelta(minutes=DEFAULT_BLOCK_MIN)
        def ics_dt(ts: dt.datetime) -> str: return ts.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uid = f"canvas-{it.get('course_id','')}-{it.get('plannable_id','')}-{abs(hash(it['title']))}@{socket.gethostname()}"
        summary = f"{it['course_code']} • {it['title']} [{it['ptype']}]"
        desc = f"URL: {it['url']}"; loc = it["course_name"] or it["course_code"]
        return "\n".join([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{ics_dt(dt.datetime.now(ZoneInfo(USER_TZ)))}",
            f"DTSTART:{ics_dt(start)}",
            f"DTEND:{ics_dt(due)}",
            f"SUMMARY:{self._ics_escape(summary)}",
            f"DESCRIPTION:{self._ics_escape(desc)}",
            f"LOCATION:{self._ics_escape(loc)}",
            "END:VEVENT"
        ])

    def _export_all_ics(self) -> str:
        os.makedirs(EXPORT_DIR, exist_ok=True)
        events = [self._ics_event_for_item(it) for it in self.items]
        ics = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//canvas-tui//EN\n" + "\n".join([e for e in events if e]) + "\nEND:VCALENDAR\n"
        with open(EXPORT_ICS, "w", encoding="utf-8") as f: f.write(ics)
        return EXPORT_ICS

    def action_export_ics(self):
        try:
            path = self._export_all_ics()
            self.details.update(f"[green]ICS exported[/green]: {path}")
        except Exception as e:
            self.details.update(f"[red]ICS export failed:[/red] {e}")

    def action_export_ics_and_import(self):
        try:
            path = self._export_all_ics()
            if shutil.which("calcurse"):
                p = subprocess.run(["calcurse","-i", path], capture_output=True, text=True)
                if p.returncode == 0:
                    self.details.update(f"[green]ICS imported to calcurse[/green]: {path}")
                else:
                    self.details.update(f"[yellow]calcurse import error[/yellow]: {p.stderr.strip() or p.stdout.strip()}")
            else:
                self.details.update(f"[yellow]calcurse not found[/yellow]. ICS at {path}")
        except Exception as e:
            self.details.update(f"[red]ICS export/import failed:[/red] {e}")

    def action_open_course(self):
        it = self._selected_item()
        if not it: return
        m = re.search(r"/courses/(\d+)", it["url"])
        if m:
            url = urljoin(BASE_URL, f"/courses/{m.group(1)}")
            try: webbrowser.open(url, new=2)
            except Exception: pass
        else:
            self.details.update("[yellow]No course link found[/yellow]")

    def action_filter(self):
        if self.filtered is not None:
            self.filtered = None; self._render_table(); self.details.update("[dim]Filter cleared[/dim]"); return
        self._show_input("Filter (title/course/type):", "", "", "filter", {})

    def action_toggle_hide(self):
        it = self._selected_item()
        if not it: return
        vis = STATE["visibility"].get(it["key"], 0)
        vis = 1 if vis==0 else 2 if vis==1 else 0
        STATE["visibility"][it["key"]] = vis
        _save_state(STATE)
        self._render_table()

    def action_toggle_show_hidden(self):
        self.show_hidden = not self.show_hidden
        self._render_table()
        self.details.update("[dim]Showing hidden[/dim]" if self.show_hidden else "[dim]Hidden suppressed[/dim]")

    # Pomodoro
    def action_pomo30(self): self.pomo.start(30)
    def action_pomo60(self): self.pomo.start(60)
    def action_pomo120(self): self.pomo.start(120)
    def action_pomo_custom(self): self._show_input("Minutes:", "", "45", "pomo", {})
    def action_pomo_stop(self): self.pomo.stop()

    # Views
    def action_open_syllabi(self):
        if not self.course_cache:
            self.details.update("[yellow]No courses cached yet[/yellow]"); return
        self.push_screen(SyllabiScreen(self, self.course_cache))

    def action_open_announcements(self):
        if not self.announcements:
            self.details.update("[dim]No announcements in window[/dim]"); return
        self.push_screen(AnnouncementsScreen(self, self.announcements))

if __name__ == "__main__":
    CanvasTUI().run()

