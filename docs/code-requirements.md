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

### פונקציות:
- **`get_connection()`** — פותח connection ל-Postgres דרך `POSTGRES_URL` מה-environment. מוחזר ל-caller כדי שה-connection יישאר פתוח לאורך כל עיבוד השעה (ביצועים).
- **`execute_sql(sql)`** — מריץ SQL statement חד-פעמי (לשימוש ב-DDL בלבד — יצירת טבלאות, indexes).
- **`create_tables()`** — יוצר את כל הטבלאות, indexes, וה-materialized view אם לא קיימים. רץ פעם אחת בהפעלה.
- **`save_event(event, conn)`** — שומר event אחד לטבלה המתאימה לפי `event['type']`. מקבל connection מבחוץ כדי לא לפתוח connection חדש לכל event.
- **`get_last_fetched_hour()`** — קורא את ה-high-water mark מטבלת `ingest_state`. מחזיר `None` אם זו הפעלה ראשונה.
- **`set_last_fetched_hour(hour)`** — מעדכן את ה-high-water mark בטבלת `ingest_state` עם UPSERT.

---

## `src/ingest/poller.py`
אחראי על משיכת קבצים מה-vendor.

### פונקציות:
- **`build_url(hour)`** — בונה את ה-URL לפי שעה נתונה. פורמט: `YYYY-MM-DD-H.json.gz` עם zero-padding על חודש ויום.
- **`fetch_file(hour)`** — שולח GET request ל-vendor ומטפל בתשובות:
  - `200` — מחזיר את ה-response
  - `404` — השעה עוד לא עברה, ישן 5 שניות ומחזיר `None`
  - `503` — vendor בoutage, ישן 30 שניות ומחזיר `None`
  - שגיאת network — ישן 10 שניות ומחזיר `None`

---

## `src/ingest/normalizer.py`
אחראי על חילוץ שדות מה-JSON לפי סוג אירוע.

### פונקציות:
- **`parse_file(response)`** — מקבל HTTP response, מפענח את ה-gzip ומחזיר רשימת שורות. משתמש ב-`zlib.decompressobj` כדי שגם **gzip חתוך (truncated chaos)** לא יקרוס — שומר את כל השורות השלמות עד נקודת החיתוך, והשורה החצי-שבורה האחרונה נזרקת ב-`parse_event`.
- **`parse_event(line)`** — מפרסר שורת JSON אחת ל-dict. מחזיר `None` אם השורה שבורה.
- **`normalize(event)`** — ממיר event גולמי לפורמט אחיד לפי סוג:
  - `PushEvent` → actor, repo, forced, commits (author_name, author_email)
  - `PullRequestEvent` → pr_author מה-payload (לא actor), repo, language, action, merged
  - `WatchEvent` → actor, repo, created_at
  - `ForkEvent` → actor, repo, created_at
  - סוג לא מוכר → raw_event עם payload מלא ב-JSONB

---

## `src/ingest/main.py`
נקודת הכניסה — מפעיל את הלולאה הראשית.

### זרימה:
1. `create_tables()` — יצירת כל הטבלאות בהפעלה ראשונה
2. `get_last_fetched_hour()` — קריאת high-water mark. אם קיים, מתחילים מהשעה ש*אחרי* האחרונה שהושלמה (כדי לא לעבד פעמיים שעה שכבר נשמרה). אם `None` — מתחילים מתחילת החלון.
3. לולאה אינסופית לכל שעה:
   - `fetch_file(hour)` — הורדת קובץ מה-vendor
   - `parse_file(response)` — פתיחת gzip וחלוקה לשורות
   - לכל שורה: `parse_event` → `normalize` → `save_event`
   - event שגוי — `try/except` שתופס ומדלג בלי לקרוס
   - `set_last_fetched_hour(hour)` — עדכון high-water mark רק אחרי שכל השורות עובדו

---

## `src/ingest/neo4j_sync.py`
סנכרון נתוני contributions מ-PostgreSQL ל-Neo4j. רץ ידנית לפני הדיפנס.

### פונקציות:
- **`get_connection()`** — פותח connection ל-Postgres.
- **`get_contributions()`** — מרענן את ה-materialized view ושולף את כל זוגות `(actor, repo)`.
- **`create_indexes(driver)`** — יוצר indexes על Developer.name ו-Repo.name ב-Neo4j לפני הכנסת נתונים (מאיץ את ה-MERGE).
- **`create_developers(tx, batch)`** — יוצר Developer nodes ב-Neo4j בbatch.
- **`create_repos(tx, batch)`** — יוצר Repo nodes ב-Neo4j בbatch.
- **`create_relationships(tx, batch)`** — יוצר קשרי `CONTRIBUTED_TO` בין Developers ל-Repos.
- **`sync_to_neo4j(contributions)`** — מריץ את כל השלבים בchunks של 1000 שורות כדי לא לשבור את ה-CPU.
