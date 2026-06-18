# בעיות שנתקלתי בהן

## 1. ingest container בלולאת restart
**הבעיה:** `main.py` היה ריק — container עולה, לא מוצא קוד, יוצא מיד. Docker מנסה שוב ושוב.
**הפתרון:** הוספת `while True: time.sleep(60)` כplaceholder עד שהקוד היה מוכן.

---

## 2. ModuleNotFoundError: No module named 'db'
**הבעיה:** Python לא מצא את `db.py` כי ה-`WORKDIR` היה `/app` ולא `/app/ingest`.
**הפתרון:** הוספת `WORKDIR /app/ingest` ב-`Dockerfile` לפני ה-`CMD`.

---

## 3. ingest מחכה 300 שניות לdata-init
**הבעיה:** הוספנו `depends_on: gh-archive-vendor` אבל ה-`gh-archive-vendor` תלוי ב-`data-init` שמוריד 144 קבצים (20-40 דקות).
**הפתרון:** הגדרת `MAX_FILES_TO_DOWNLOAD=6` ב-`.env` לצרכי פיתוח.

---

## 4. vendor מחזיר 404 למרות שהקבצים קיימים
**הבעיה:** URL שגוי — `2024-1-15-0.json.gz` במקום `2024-01-15-0.json.gz`. חסר zero-padding על חודש ויום.
**הפתרון:** שינוי ב-`poller.py` מ-`{hour.month}` ל-`{hour.month:02d}` ו-`{hour.day:02d}`.
