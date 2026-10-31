"""
Productive Engineer auto-poster
--------------------------------
Reads posts from queue/<YYYY-MM-DD_HHMM>/ (Bangkok time) and publishes them to
a Facebook Page and TikTok (photo post). Designed to run every 15 minutes on
GitHub Actions; it is safe to run repeatedly — progress is kept in state.json.

Each post folder contains:
    01.png, 02.jpg ...   one or more images (png/jpg/jpeg/webp)
    caption.txt          the caption (first line is used as the TikTok title)
"""
import json
import os
import pathlib
import sys
import time
import datetime as dt
from zoneinfo import ZoneInfo

import requests
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent
QUEUE = ROOT / "queue"
MEDIA = ROOT / "docs" / "media"
STATE_FILE = ROOT / "state.json"
TZ = ZoneInfo("Asia/Bangkok")

GRAPH = "https://graph.facebook.com/v21.0"
TT = "https://open.tiktokapis.com/v2"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}

FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN", "")
TT_CLIENT_KEY = os.getenv("TT_CLIENT_KEY", "")
TT_CLIENT_SECRET = os.getenv("TT_CLIENT_SECRET", "")
TT_REFRESH_TOKEN = os.getenv("TT_REFRESH_TOKEN", "")
# Your verified site, e.g. https://media.example.com (GitHub Pages serves docs/ there)
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")
MEDIA_BASE_URL = f"{SITE_URL}/media" if SITE_URL else ""
# PUBLIC_TO_EVERYONE once your TikTok app passes audit; until then only SELF_ONLY works
TT_PRIVACY = os.getenv("TT_PRIVACY", "SELF_ONLY")
DRY_RUN = os.getenv("DRY_RUN", "") == "1"

FB_ENABLED = bool(FB_PAGE_ID and FB_PAGE_TOKEN)
TT_ENABLED = bool(TT_CLIENT_KEY and TT_CLIENT_SECRET and TT_REFRESH_TOKEN and MEDIA_BASE_URL)

FB_SCHEDULE_MIN = dt.timedelta(minutes=11)   # Meta needs >= 10 min ahead
FB_SCHEDULE_MAX = dt.timedelta(hours=23)     # temporary photos live ~24 h
TT_EARLY = dt.timedelta(minutes=5)           # may post up to 5 min early
MAX_LATE = dt.timedelta(hours=6)             # skip posts that are this overdue
MAX_ATTEMPTS = 3


def log(msg):
    print(f"[{dt.datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- state ----
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- queue ----
class Post:
    def __init__(self, folder: pathlib.Path):
        self.id = folder.name
        self.folder = folder
        self.time = dt.datetime.strptime(folder.name[:15], "%Y-%m-%d_%H%M").replace(tzinfo=TZ)
        self.images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMG_EXT)
        cap = folder / "caption.txt"
        self.caption = cap.read_text(encoding="utf-8").strip() if cap.exists() else ""

    def media_files(self):
        return [MEDIA / self.id / f"{i + 1:02d}.jpg" for i in range(len(self.images))]

    def media_urls(self):
        return [f"{MEDIA_BASE_URL}/{self.id}/{p.name}" for p in self.media_files()]


def load_posts():
    posts = []
    if not QUEUE.exists():
        return posts
    for d in sorted(QUEUE.iterdir()):
        if not d.is_dir():
            continue
        try:
            p = Post(d)
        except ValueError:
            log(f"skip {d.name}: folder name must look like 2026-11-01_0900")
            continue
        if not p.images or not p.caption:
            log(f"skip {p.id}: needs at least one image and caption.txt")
            continue
        posts.append(p)
    return posts


def prepare_media(post):
    """Convert images to JPEG (TikTok rejects PNG) inside docs/media for hosting."""
    changed = False
    for src, dst in zip(post.images, post.media_files()):
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(src).convert("RGB")
        if img.width > 1080:
            img = img.resize((1080, round(img.height * 1080 / img.width)), Image.LANCZOS)
        img.save(dst, "JPEG", quality=90, optimize=True)
        changed = True
        log(f"prepared {dst.relative_to(ROOT)}")
    return changed


# -------------------------------------------------------------- facebook ---
def fb_check(r):
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"Facebook error: {data.get('error', data)}")
    return data


def fb_publish(post, schedule_at=None):
    photo_ids = []
    for path in post.media_files():
        with open(path, "rb") as f:
            r = requests.post(
                f"{GRAPH}/{FB_PAGE_ID}/photos",
                data={"published": "false", "temporary": "true", "access_token": FB_PAGE_TOKEN},
                files={"source": f},
                timeout=120,
            )
        photo_ids.append(fb_check(r)["id"])

    data = {"message": post.caption, "access_token": FB_PAGE_TOKEN}
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    if schedule_at:
        data.update(
            published="false",
            scheduled_publish_time=str(int(schedule_at.timestamp())),
            unpublished_content_type="SCHEDULED",
        )
    r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/feed", data=data, timeout=60)
    return fb_check(r)["id"]


# ---------------------------------------------------------------- tiktok ---
_tt_token = None


def tt_token():
    global _tt_token
    if _tt_token:
        return _tt_token
    r = requests.post(
        f"{TT}/oauth/token/",
        data={
            "client_key": TT_CLIENT_KEY,
            "client_secret": TT_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": TT_REFRESH_TOKEN,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data.get('error_description') or data}")
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != TT_REFRESH_TOKEN:
        # The workflow stores this as the new TT_REFRESH_TOKEN secret, then deletes the file.
        (ROOT / ".tt_new_refresh").write_text(new_refresh)
    _tt_token = data["access_token"]
    return _tt_token


def tt_call(path, body):
    r = requests.post(
        f"{TT}{path}",
        json=body,
        headers={"Authorization": f"Bearer {tt_token()}", "Content-Type": "application/json; charset=UTF-8"},
        timeout=60,
    )
    data = r.json()
    err = data.get("error", {})
    if err.get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok error {err.get('code')}: {err.get('message')}")
    return data.get("data", {})


def tt_title(caption):
    first = caption.splitlines()[0].strip()
    # limit is 90 UTF-16 units; emoji count double, so stay well under
    while len(first.encode("utf-16-le")) // 2 > 88:
        first = first[:-1]
    return first


def tt_publish(post):
    info = tt_call("/post/publish/creator_info/query/", {})
    options = info.get("privacy_level_options", [])
    privacy = TT_PRIVACY if TT_PRIVACY in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])
    if privacy != TT_PRIVACY:
        log(f"TikTok: {TT_PRIVACY} not allowed for this account/app, using {privacy}")
    body = {
        "post_info": {
            "title": tt_title(post.caption),
            "description": post.caption[:3990],
            "privacy_level": privacy,
            "disable_comment": False,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": post.media_urls(),
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    publish_id = tt_call("/post/publish/content/init/", body)["publish_id"]

    status = "PROCESSING"
    for _ in range(12):  # poll up to ~2 minutes
        time.sleep(10)
        st = tt_call("/post/publish/status/fetch/", {"publish_id": publish_id})
        status = st.get("status", status)
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            if status == "FAILED":
                raise RuntimeError(f"TikTok publish failed: {st.get('fail_reason')}")
            break
    return publish_id, status


def urls_live(post):
    for url in post.media_urls():
        try:
            if requests.head(url, timeout=15, allow_redirects=True).status_code != 200:
                return False
        except requests.RequestException:
            return False
    return True


# ------------------------------------------------------------------ main ---
def attempt(state, post, platform, fn):
    rec = state.setdefault(post.id, {})
    tries = rec.get(f"{platform}_attempts", 0)
    if tries >= MAX_ATTEMPTS:
        return
    try:
        if DRY_RUN:
            log(f"[dry run] would post {post.id} to {platform}")
            return
        result = fn()
        rec[platform] = result
        rec[f"{platform}_at"] = dt.datetime.now(TZ).isoformat(timespec="seconds")
        rec.pop(f"{platform}_error", None)
        log(f"{platform}: {post.id} -> {result}")
    except Exception as e:  # keep going with other posts
        rec[f"{platform}_attempts"] = tries + 1
        rec[f"{platform}_error"] = str(e)[:500]
        log(f"{platform}: {post.id} FAILED ({tries + 1}/{MAX_ATTEMPTS}): {e}")


def main():
    state = load_state()
    posts = load_posts()
    now = dt.datetime.now(TZ)
    log(f"{len(posts)} post(s) in queue | FB {'on' if FB_ENABLED else 'off'} | TikTok {'on' if TT_ENABLED else 'off'}")

    media_changed = False
    for post in posts:
        media_changed |= prepare_media(post)

    for post in posts:
        rec = state.get(post.id, {})
        late = now - post.time
        if late > MAX_LATE and not rec:
            log(f"skip {post.id}: more than {MAX_LATE} overdue")
            continue

        if FB_ENABLED and "fb" not in rec:
            ahead = post.time - now
            if ahead <= FB_SCHEDULE_MIN:
                attempt(state, post, "fb", lambda: fb_publish(post))
            elif ahead <= FB_SCHEDULE_MAX:
                attempt(state, post, "fb", lambda: fb_publish(post, schedule_at=post.time))

        if TT_ENABLED and "tt" not in rec and post.time - now <= TT_EARLY:
            if urls_live(post):
                attempt(state, post, "tt", lambda: "{} ({})".format(*tt_publish(post)))
            else:
                log(f"tt: {post.id} waiting for images to go live on {MEDIA_BASE_URL}")

    save_state(state)
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"media_changed={'true' if media_changed else 'false'}\n")


if __name__ == "__main__":
    sys.exit(main())
