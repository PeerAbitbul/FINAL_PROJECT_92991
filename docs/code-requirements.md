# דרישות לכל קובץ קוד

---

## `src/Dockerfile`
בניית image לשירות ה-ingest.

- base image של Python 3.12
- העתקת תיקיית `ingest/` לתוך ה-container
- התקנת dependencies: `psycopg2-binary`, `neo4j`, `requests`
- נקודת כניסה: `python ingest/main.py`

---

## `compose.yml`
הפעלת כל השירותים יחד.

- `data-init` — מוריד את קבצי GH Archive לvolume (קיים מהscaffold)
- `gh-archive-vendor` — מגיש את הקבצים עם simulated clock (קיים מהscaffold)
- `postgres` — בסיס נתונים ראשי, גרסה 16, עם volume לשמירת נתונים בין restarts
- `neo4j` — graph database, גרסה 5, עם volume לשמירת נתונים בין restarts
- `ingest` — השירות שלנו, מחכה ל-healthcheck של postgres ו-neo4j לפני שעולה
- כל שירות עם `restart: unless-stopped` כדי לשרוד restart אוטומטי

---

## `src/ingest/db.py`
אחראי על כל מה שקשור לבסיס הנתונים.

- התחברות ל-Postgres דרך `POSTGRES_URL` מה-environment
- יצירת כל הטבלאות אם לא קיימות (`create_tables`)
- יצירת indexes
- יצירת materialized view של `contributions`
- קריאה ועדכון של high-water mark (`get_last_fetched_hour`, `set_last_fetched_hour`)

---

## `src/ingest/poller.py`
אחראי על משיכת קבצים מה-vendor.

- בניית URL מה-high-water mark לפי פורמט `YYYY-M-D-H.json.gz` (ללא zero-padding על השעה)
- שליחת GET request ל-vendor
- טיפול בתשובות:
  - `200` — הצלחה, להעביר את הקובץ ל-normalizer
  - `404` — השעה עוד לא עברה, לחכות ולנסות שוב
  - `503` — vendor בoutage, לחכות ולנסות שוב
- retry עם exponential backoff על 404 ו-503
- זיהוי truncated gzip — אם הקובץ נחתך באמצע לנסות שוב
- קריאת `VENDOR_URL` מה-environment

---

## `src/ingest/normalizer.py`
אחראי על חילוץ שדות מה-JSON לפי סוג אירוע.

- קבלת שורת JSON אחת (event)
- זיהוי `type` של האירוע
- חילוץ שדות רלוונטיים לפי סוג:
  - `PushEvent` → actor, repo, forced, commits (author_name, author_email)
  - `PullRequestEvent` → pr_author מה-payload (לא actor), repo, language, action, merged
  - `WatchEvent` → actor, repo, created_at
  - `ForkEvent` → actor, repo, created_at
  - סוג לא מוכר → שמירה כ-raw_event עם payload מלא
- החזרת dict מסודר לשמירה ב-db

---

## `src/ingest/main.py`
נקודת הכניסה — מפעיל את הלולאה הראשית.

- קריאה ל-`create_tables()` בהפעלה ראשונה
- קריאת high-water mark — מאיזה קובץ להמשיך
- אם אין high-water mark — להתחיל מ-`REPLAY_WINDOW_START` שב-environment
- לולאה אינסופית:
  1. חשב את השעה הבאה
  2. קרא ל-poller להוריד
  3. קרא ל-normalizer לנרמל
  4. שמור ל-db
  5. עדכן high-water mark
  6. עבור לשעה הבאה
