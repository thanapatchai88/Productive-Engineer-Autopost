"""
TikTok login for the bot, run from GitHub Actions (works from an iPad).

Run 1 (no code): writes the TikTok login link to the run summary.
Run 2 (with code from callback.html): exchanges it for a refresh token and
writes it to .tt_new_refresh, which the workflow saves as TT_REFRESH_TOKEN.
"""
import os
import secrets
import urllib.parse

import requests

client_key = os.environ["TT_CLIENT_KEY"]
client_secret = os.environ["TT_CLIENT_SECRET"]
site = os.environ["SITE_URL"].rstrip("/")
code = urllib.parse.unquote(os.getenv("CODE", "").strip())
redirect_uri = f"{site}/callback.html"
summary = open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/stdout"), "a")

if not code:
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": client_key,
        "scope": "user.info.basic,video.publish",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": secrets.token_urlsafe(8),
    })
    summary.write(
        "## ขั้นที่ 1: ล็อกอิน TikTok\n\n"
        f"[กดที่นี่เพื่อล็อกอินด้วยบัญชี productive_engineer]({url})\n\n"
        "อนุญาตแล้วจะเห็นโค้ด ให้คัดลอกโค้ด แล้วกลับมา Run workflow นี้อีกครั้งโดยวางโค้ดในช่อง code\n"
    )
    raise SystemExit(0)

r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=30,
).json()

if "refresh_token" not in r:
    summary.write(f"## ไม่สำเร็จ\n\n{r.get('error_description') or r.get('error') or 'unknown error'}\n\nลองขั้นที่ 1 ใหม่ (โค้ดใช้ได้ครั้งเดียวและหมดอายุเร็ว)\n")
    raise SystemExit(1)

print(f"::add-mask::{r['refresh_token']}")
with open(".tt_new_refresh", "w") as f:
    f.write(r["refresh_token"])
summary.write(f"## เชื่อม TikTok สำเร็จ ✅\n\nสิทธิ์ที่ได้: {r.get('scope')}\n\nบันทึก token ลง secrets เรียบร้อย\n")
