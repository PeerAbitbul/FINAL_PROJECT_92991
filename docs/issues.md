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

---

## 5. קובץ gzip חתוך (truncated chaos) הפיל את ה-ingest
**הבעיה:** `parse_file` ב-`normalizer.py` השתמש ב-`gzip.decompress()`, שזורק `EOFError` על stream חתוך. זה אחד ממצבי ה-chaos של ה-vendor — וגרם לקריסת הלולאה כולה.
**הפתרון:** מעבר ל-`zlib.decompressobj(zlib.MAX_WBITS | 16)` שמחזיר את כל מה שהתפענח עד נקודת החיתוך; תפיסת `zlib.error`/`EOFError` ושמירת השורות השלמות. השורה החצי-שבורה נדחית ב-`parse_event`.

---

## 6. restart הכניס נתונים כפולים (off-by-one)
**הבעיה:** ה-high-water mark נשמר אחרי עיבוד שעה, אבל ב-restart הקוד התחיל מאותה שעה שכבר נשמרה — ומשך אותה שוב, מה שיצר כפילויות (אין unique constraint).
**הפתרון:** ב-`main.py`, ב-restart מתחילים מ-`last_hour + timedelta(hours=1)` — השעה הבאה. ה-commit הוא per-שעה, אז שעה שנקטעה באמצע מתעבדת מחדש נקי בלי כפילות.

---

## 7. Q1 ספר לפי `actor` במקום `pr_author`
**הבעיה:** ה-BRIEF מגדיר שהשפות הן של מי שפתח את ה-PR. השאילתה קיבצה לפי `actor` (מי שסגר/מיזג), והסף של 10 PRs נבדק לכל שפה בנפרד במקום על סך הכל.
**הפתרון:** קיבוץ לפי `pr_author`; הסף `HAVING count(*) >= 10` על סך כל ה-PRs הממוזגים של המפתח.

---

## 8. Q3 השתמש ב-actor גולמי ובלי tie-break
**הבעיה:** Q3 איחד `pull_request_events.actor` + `push_events.actor`, אבל "תורם" = PR author או commit author. בנוסף חסר שובר-שוויון לפי סך תרומות (דרישת ה-BRIEF).
**הפתרון:** Q3 רץ על ה-materialized view `contributions`. ה-view עודכן לכלול עמודת `contributions` (ספירה), והשאילתה ממיינת `ORDER BY shared_repos DESC, combined_contributions DESC`.

---

## 9. Q4 לא יישם את חלונות הזמן
**הבעיה:** ה-BRIEF דורש אחוז stargazers שעשו fork תוך יומיים, ואחוז forkers שפתחו PR תוך 5 ימים — per actor. השאילתה רק ספרה כמה repos קיבלו fork/PR בכלל, בלי קישור per-actor ובלי חלון זמן.
**הפתרון:** שאילתה חדשה עם CTEs (`stars`/`forks`/`prs`) שמצרפת לפי `(actor, repo)` ומסננת לפי `INTERVAL '2 days'` ו-`INTERVAL '5 days'` על `created_at` (זמן-סימולציה).

---

## 10. Q5 לא החזיר את ה-repos המחברים
**הבעיה:** ה-BRIEF דורש להחזיר גם את ה-repos שמחברים בין המפתחים. ה-Cypher החזיר רק שם + distance, וגם ספר מפתחים במרחק 1 שוב כמרחק 2.
**הפתרון:** הוספת `collect(DISTINCT r.name) AS connecting_repos`, ותנאי `NOT (seed)-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d2)` שמוציא את מי שכבר במרחק 1.

---

## 11. SQL injection ב-`set_last_fetched_hour`
**הבעיה:** הפונקציה בנתה את ה-SQL עם f-string (`'{hour}'`) במקום parameterized query.
**הפתרון:** מעבר ל-`cursor.execute(..., (hour, hour))` עם placeholders `%s` — psycopg2 מבריח את הערך.

---

## 12. הקוד "צרוב" ל-image — `docker compose up` רץ קוד ישן
**הבעיה:** שירות ה-ingest הוא `build: ./src` בלי volume mount, אז עריכת קוד בדיסק לא משפיעה על ה-container עד rebuild. `docker compose up -d` בלבד הריץ את הקוד הישן.
**הפתרון:** שימוש ב-`docker compose up -d --build` (או `make run`) — עודכן ב-`presentation-plan.md`.
