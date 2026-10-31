# Productive Engineer – บอทโพสต์อัตโนมัติ (Facebook Page + TikTok)

บอทนี้รันบน GitHub Actions ทุก 15 นาที อ่านโพสต์จากโฟลเดอร์ `queue/` แล้วโพสต์ลงเพจ Facebook และ TikTok (แบบภาพ) ตามเวลาที่กำหนด ตั้งค่าทั้งหมดทำบน iPad ผ่าน Safari ได้

## วิธีใช้งานประจำวัน

แต่ละโพสต์คือหนึ่งโฟลเดอร์ใน `queue/` ตั้งชื่อเป็นวันเวลาที่จะโพสต์ (เวลาไทย)

```
queue/
  2026-11-01_0900/
    01.png          ← ภาพ (ใส่ได้หลายภาพ: 02.png, 03.png ...)
    caption.txt     ← แคปชัน (บรรทัดแรกใช้เป็นชื่อโพสต์ TikTok)
```

- Facebook: บอทตั้งเวลาโพสต์ในเพจล่วงหน้าให้เมื่อเหลือไม่เกิน 23 ชั่วโมง (โพสต์ตรงเวลา)
- TikTok: ไม่มีระบบตั้งเวลา บอทโพสต์ตอนถึงเวลา (อาจช้า 5–20 นาที)
- ภาพ PNG ถูกแปลงเป็น JPG ให้อัตโนมัติ
- ผลลัพธ์และข้อผิดพลาดดูใน `state.json` หรือแท็บ Actions ถ้าล้มเหลวบอทลองใหม่ 3 ครั้ง อยากลองอีกให้ลบรายการโพสต์นั้นใน `state.json`

## ตั้งค่า Facebook (ทำได้เลย ไม่ต้องใช้โดเมน)

1. **Meta app:** developers.facebook.com → My Apps → แอปของคุณ ให้แน่ใจว่าบัญชีคุณเป็นแอดมินของเพจ Productive Engineer
2. **ขอ token:** เปิด developers.facebook.com/tools/explorer
   - Meta App: เลือกแอปของคุณ / User or Page: **User Token**
   - Permissions: เพิ่ม `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
   - กด **Generate Access Token** อนุญาตเพจ Productive Engineer แล้วคัดลอก token
3. **ทำให้ไม่หมดอายุ:** เปิด developers.facebook.com/tools/debug/accesstoken วาง token → **Debug** → เลื่อนลงกด **Extend Access Token** → คัดลอก token ใหม่ที่ได้
4. **เอา Page token:** กลับไปที่ Graph API Explorer วาง token ใหม่ในช่อง Access Token พิมพ์ `me/accounts` ในช่องคำค้น กด **Submit** จะเห็นเพจของคุณ คัดลอก `id` และ `access_token` ของเพจ Productive Engineer
5. **ใส่ใน GitHub:** repo → Settings → Secrets and variables → Actions → **New repository secret**
   - `FB_PAGE_ID` = id จากข้อ 4
   - `FB_PAGE_TOKEN` = access_token จากข้อ 4
6. ทดสอบ: แท็บ Actions → autopost → **Run workflow**

## ตั้งค่า TikTok (หลังได้โดเมน)

1. **เว็บโฮสต์ภาพ:** Settings → Pages → Source: **GitHub Actions** แล้วใส่ Custom domain เช่น `media.productiveeng.com` ตั้ง DNS ที่ผู้ให้บริการโดเมน: CNAME `media` → `thanapatchai88.github.io` รอจนติ๊ก **Enforce HTTPS** ได้
2. **Variables:** Settings → Secrets and variables → Actions → แท็บ Variables
   - `SITE_URL` = `https://media.productiveeng.com`
   - `TT_PRIVACY` = `SELF_ONLY`
3. Actions → autopost → Run workflow หนึ่งครั้ง แล้วเปิด `https://media.productiveeng.com/callback.html` ต้องเห็นหน้า "TikTok login code"
4. **TikTok Developer app:** เพิ่ม **Login Kit** และ **Content Posting API** (เปิด Direct Post) สโคป `user.info.basic`, `video.publish`
   - Login Kit → Redirect URI: `https://media.productiveeng.com/callback.html`
   - Content Posting API → URL properties → ยืนยัน URL prefix `https://media.productiveeng.com/` (ส่งไฟล์ยืนยันมาให้ Claude ใส่ใน `docs/` ได้)
5. **Secrets:** `TT_CLIENT_KEY`, `TT_CLIENT_SECRET` (จากหน้าแอป) และ `GH_PAT`:
   github.com/settings/personal-access-tokens → Generate new token → Repository access: เฉพาะ repo นี้ → Permissions: **Secrets: Read and write**
6. **ล็อกอิน TikTok:** Actions → tiktok-login → Run workflow (เว้นช่อง code ว่าง) → เปิดผลการรัน กดลิงก์ล็อกอิน → อนุญาต → คัดลอกโค้ด → Run workflow อีกครั้งโดยวางโค้ด ระบบบันทึก token ให้เอง
7. **Audit:** ก่อนแอปผ่าน audit โพสต์จะเห็นแค่เจ้าของบัญชี และบัญชีต้องเป็นส่วนตัว ส่งแอปเข้า audit ใน developer portal ผ่านแล้วเปลี่ยน `TT_PRIVACY` เป็น `PUBLIC_TO_EVERYONE`

เว้นค่าของแพลตฟอร์มไหนไว้ บอทจะข้ามแพลตฟอร์มนั้น

## หมายเหตุ
- repo เป็น public คนอื่นเห็นภาพและแคปชันในคิวก่อนโพสต์ได้ ส่วน token อยู่ใน secrets ปลอดภัย
- GitHub ปิด workflow ตั้งเวลาอัตโนมัติถ้า repo ไม่มีความเคลื่อนไหว 60 วัน เพิ่มโพสต์ประจำก็ไม่มีปัญหา
