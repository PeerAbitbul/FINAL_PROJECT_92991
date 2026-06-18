# PostgreSQL Schema Design

## למה טבלה לכל סוג אירוע?

כל סוג אירוע ב-GH Archive יש לו `payload` שונה לגמרי.
אם נשמור הכל בטבלה אחת עם JSON גולמי, כל שאילתה תצטרך לחפש בתוך ה-JSON — איטי ומסורבל.
במקום זה, אנחנו שולפים מה-JSON רק את השדות שרלוונטיים לנו ושומרים אותם בעמודות נפרדות.
סוגים שלא מכירים נשמרים ב-`raw_events` כדי לא לאבד מידע.

---

## הטבלאות

### `push_events`
מייצגת כל פעם שמישהו עשה push לrepository.

| עמודה | סיבה |
|-------|------|
| `id` | מזהה ייחודי של האירוע |
| `actor` | מי עשה את ה-push (לא בהכרח מי כתב את הקוד) |
| `repo` | שם הrepository |
| `created_at` | מתי קרה |
| `forced` | האם זה היה force push — אם כן, הcommits לא בהכרח שיקוף אמיתי של מי כתב מה (חשוב ל-Q2) |

### `push_commits`
טבלה נפרדת כי כל push יכול להכיל הרבה commits.

| עמודה | סיבה |
|-------|------|
| `push_id` | קישור ל-`push_events` |
| `author_name` | שם כותב ה-commit |
| `author_email` | אימייל כותב ה-commit — Q2 מגדיר commit author כזוג ייחודי של name+email |

---

### `pull_request_events`
מייצגת פתיחה, סגירה, או מיזוג של pull request.

| עמודה | סיבה |
|-------|------|
| `id` | מזהה ייחודי של האירוע |
| `actor` | מי ביצע את הפעולה (לא בהכרח מי פתח את ה-PR) |
| `pr_author` | מי פתח את ה-PR — שלוף מ-`payload.pull_request.user.login`, לא מ-`actor` (חשוב ל-Q1, Q3) |
| `repo` | שם הrepository |
| `language` | שפת התכנות — שלוף מ-`payload.pull_request.base.repo.language` (חשוב ל-Q1) |
| `action` | `opened` / `closed` — לדעת אם זו פתיחה או סגירה |
| `merged` | האם ה-PR אוחד — שלוף מ-`payload.pull_request.merged` (חשוב ל-Q1) |
| `created_at` | מתי קרה |

---

### `watch_events`
מייצגת כל פעם שמישהו נתן כוכב לrepository (GitHub קורא לזה WatchEvent).

| עמודה | סיבה |
|-------|------|
| `id` | מזהה ייחודי של האירוע |
| `actor` | מי נתן את הכוכב |
| `repo` | לאיזה repository |
| `created_at` | מתי — חשוב ל-Q4 (חלון הזמן star→fork→PR) |

---

### `fork_events`
מייצגת כל פעם שמישהו עשה fork לrepository.

| עמודה | סיבה |
|-------|------|
| `id` | מזהה ייחודי של האירוע |
| `actor` | מי עשה את ה-fork |
| `repo` | לאיזה repository |
| `created_at` | מתי — חשוב ל-Q4 (חלון הזמן star→fork→PR) |

---

### `ingest_state`
שורה אחת בלבד — שומרת עד לאיזה קובץ ה-poller הגיע. כך אם השירות מתאפס הוא יודע מאיפה להמשיך ולא מתחיל מחדש.

| עמודה | סיבה |
|-------|------|
| `last_fetched_hour` | הקובץ האחרון שהורד בהצלחה, למשל: `2024-01-15-3` |

---

### `raw_events`
כל אירוע מסוג שלא מכירים נשמר כאן כ-JSON גולמי. כך לא מאבדים מידע אם GitHub יוסיף סוגים חדשים בעתיד.

| עמודה | סיבה |
|-------|------|
| `id` | מזהה ייחודי של האירוע |
| `type` | סוג האירוע הלא מוכר |
| `actor` | מי ביצע |
| `repo` | על איזה repository |
| `created_at` | מתי קרה |
| `payload` | כל ה-JSON גולמי (JSONB) |

---

## Materialized View — `contributions`

### למה?
Q3 וQ5 צריכים לדעת "מי תרם לאיזה repo". המידע הזה מפוזר בשתי טבלאות — `pull_request_events` (pr_author) ו-`push_commits` (author_name). במקום לחשב את זה מחדש בכל שאילתה, שומרים אותו פעם אחת.

### למה Materialized View ולא View רגיל?
View רגיל מחשב מחדש בכל שאילתה — על 34M שורות זה איטי.
Materialized View שומר את התוצאה על הדיסק — מהיר כמו טבלה.

### למה לא טבלה רגילה?
כי לא צריך לעדכן אותה בזמן ingest — רק לפני שמריצים את השאילתות בdefense.

### הגדרה:
```sql
CREATE MATERIALIZED VIEW contributions AS
  SELECT pr_author AS actor, repo FROM pull_request_events
  UNION
  SELECT pc.author_name AS actor, pe.repo
  FROM push_commits pc
  JOIN push_events pe ON pc.push_id = pe.id;
```

### מתי מרעננים?
**לא** תוך כדי ingest. רק פעם אחת לפני defense:
```sql
REFRESH MATERIALIZED VIEW contributions;
```

---

## Indexes

### `pull_request_events`
| Index | סיבה |
|-------|------|
| `pr_author` | Q1 וQ3 מחפשים לפי מי פתח את ה-PR |
| `repo` | Q2 מחפש top 50 repos לפי PR activity |
| `merged`, `action` | Q1 מסנן רק PRs שאוחדו |
| `created_at` | Q4 מסנן לפי חלון זמן |

### `push_events`
| Index | סיבה |
|-------|------|
| `repo` | Q2 מחפש לפי repo |
| `actor` | Q2 מחפש top pushers |

### `push_commits`
| Index | סיבה |
|-------|------|
| `push_id` | JOIN עם `push_events` |
| `author_name`, `author_email` | Q2 מחפש לפי commit author |

### `watch_events`
| Index | סיבה |
|-------|------|
| `repo` | Q4 מחפש repos עם 500+ כוכבים |
| `actor`, `repo` | Q4 בודק אם אותו actor חזר לfork |
| `created_at` | Q4 מסנן לפי חלון זמן |

### `fork_events`
| Index | סיבה |
|-------|------|
| `actor`, `repo` | Q4 בודק אם מי שנתן כוכב גם עשה fork |
| `created_at` | Q4 מסנן לפי חלון זמן |

---

## לאיזה שאילתה כל טבלה?

| שאילתה | טבלאות |
|--------|--------|
| Q1 — שפות per actor | `pull_request_events` |
| Q2 — commit authors vs pushers | `push_events` + `push_commits` |
| Q3 — developer pairs | `contributions` (materialized view) |
| Q4 — star→fork→PR funnel | `watch_events` + `fork_events` + `pull_request_events` |
| Q5 — collaboration network | Neo4j (מוזן מ-`contributions`) |
