# הכנה לדיפנס — Crater

מסמך זה מרכז: (1) פיץ' פתיחה, (2) הסבר הארכיטקטורה והבחירות, (3) שאלות צפויות + תשובות מוכנות, (4) **נקודות תורפה** שחשוב להכיר לפני שישאלו, (5) צ'קליסט הרצה.

---

## 1. פיץ' פתיחה (30 שניות)

> "Crater הוא pipeline שמושך את ה-firehose של אירועי GitHub (push, PR, star, fork...) מ-vendor שמדמה את GH Archive, מנקה ומנרמל אותם לתוך מודל נתונים מסודר, ומגיש מעליו 5 שאילתות בסגנון recruiter. בחרנו אחסון **polyglot**: PostgreSQL ל-4 השאילתות האנליטיות (סנן/קבץ/ספור), ו-Neo4j לשאילתה החמישית שהיא graph traversal. ה-pipeline שורד restart בעזרת high-water mark, ושורד את כל מצבי ה-chaos."

---

## 2. הארכיטקטורה — מה כל רכיב עושה

```
gh-archive-vendor (mock)  →  ingest service (Python)  →  PostgreSQL  →  Neo4j
   (קובץ gzip לשעה)            poller→parser→normalizer→db        (sync ידני)
```

**שירות ה-ingest מחולק ל-4 קבצים — single responsibility:**

| קובץ | אחריות |
|------|--------|
| `poller.py` | בונה URL לפי שעה, מושך מה-vendor, מטפל ב-200/404/503/network עם backoff שונה לכל אחד |
| `normalizer.py` | פותח gzip, מפרסר JSON, ומחלץ מכל סוג event רק את השדות הרלוונטיים |
| `db.py` | כל הגישה ל-Postgres — יצירת טבלאות, שמירת event, high-water mark |
| `main.py` | הלולאה הראשית שמחברת את הכל |
| `neo4j_sync.py` | סנכרון ה-contributions מ-Postgres ל-Neo4j (רץ ידנית לפני Q5) |

**למה לפצל ככה?** כל קובץ עושה דבר אחד. אפשר לבדוק כל שלב בנפרד, ואם משנים את מקור הנתונים (vendor) רק `poller.py` משתנה; אם משנים DB רק `db.py` משתנה. זו הפרדת concerns קלאסית.

---

## 3. שאלות צפויות + תשובות

### א. בחירת אחסון (Storage)

**ש: למה PostgreSQL ל-Q1–Q4?**
ת: כל ארבע השאילתות הן "סנן, קבץ, ספור, JOIN" — בדיוק החוזקה של רלציוני. עם indexes מותאמים ו-GROUP BY/window functions זה מהיר וקריא. בנוסף הנתונים מגיעים כ-JSON פולימורפי, ו-Postgres נותן לי לחלץ את השדות החשובים לעמודות מסודרות וגם לשמור raw ב-JSONB כשצריך.

**ש: למה Neo4j ל-Q5?**
ת: Q5 היא "מי מחובר למי במרחק 1 ו-2" — graph traversal טהור. ב-Postgres הייתי צריך recursive CTE עם JOIN על JOIN שמתייקר ככל שהגרף גדל. Neo4j מאחסן קשרים נטיבית ועושה traversal בצורה טבעית עם Cypher.

**ש: אז יכולת לעשות הכל ב-Postgres?**
ת: כן, לגמרי — Q5 אפשרי עם recursive CTE. בחרתי polyglot **במודע** כדי להדגים graph database ו-sync בין שתי מערכות, וכי Cypher מבטא את כוונת השאילתה הרבה יותר ברור. זו החלטת trade-off, לא הכרח.

**ש: למה לא DuckDB / MongoDB / Redis?**
ת:
- DuckDB — columnar מצוין ל-aggregations, אבל אין graph ואין persistence טובה ב-container שצריך לשרוד restart.
- MongoDB — טוב ל-JSON גולמי, אבל שאילתות אנליטיות מורכבות (Q2, Q3) מסורבלות בלי SQL.
- Redis — in-memory, ~34M שורות יקר מדי ב-RAM; מתאים ל-caching לא ל-storage, ואין צורך כאן.

---

### ב. עיצוב הסכמה (Schema)

**ש: למה טבלה נפרדת לכל סוג event ולא טבלה אחת עם JSONB?**
ת: לכל סוג event יש payload שונה לגמרי. טבלה אחת עם JSON גולמי הייתה מכריחה כל שאילתה לחפש בתוך ה-JSON — איטי ומסורבל. במקום זה אני מחלץ מראש רק את השדות הרלוונטיים לעמודות typed עם indexes. סוגים שלא מכיר נשמרים ב-`raw_events` עם JSONB — כך לא מאבדים מידע (דרישת ה-BRIEF: לא לזרוק unknown types).

**ש: למה טבלת `push_commits` נפרדת מ-`push_events`?**
ת: כל push מכיל מספר commits (יחס one-to-many). הפרדה למודל מנורמל; ה-FK הוא `push_event_id`.

**ש: מה זה ה-materialized view `contributions` ולמה?**
ת: Q3 ו-Q5 צריכים "מי תרם לאיזה repo". המידע מפוזר בשתי טבלאות (`pr_author` ב-PR events, `author_name` ב-push_commits). ה-view מאחד אותם פעם אחת. בחרתי **materialized** ולא view רגיל כי על מיליוני שורות חישוב מחדש בכל שאילתה איטי; materialized שומר על דיסק = מהיר כמו טבלה. לא טבלה רגילה כי לא צריך לעדכן תוך כדי ingest — מספיק `REFRESH` פעם אחת לפני הדיפנס.

**ש: איך בחרת אילו indexes?**
ת: כל index ממופה לשאילתה שמשתמשת בו — למשל `idx_pr_author` ל-Q1/Q3, `idx_watch_created_at` ל-window הזמן של Q4. (יש טבלה מלאה ב-`docs/schema.md`.)

**הגדרת "contributor" לפי סוג event — נקודה שה-BRIEF מדגיש:**
- ב-PullRequestEvent ה-`actor` הוא מי ש**סגר/מיזג**, לא מי שפתח. את הכותב האמיתי שולפים מ-`payload.pull_request.user.login` → נשמר ב-`pr_author`.
- ב-PushEvent ה-`actor` הוא ה-pusher, אבל כותב ה-commit האמיתי הוא `author` בתוך כל commit. שומרים את שניהם בנפרד — בדיוק מה ש-Q2 משווה.

---

### ג. אמינות ה-pipeline + chaos

**ש: איך ה-pipeline שורד restart?**
ת: high-water mark — אחרי שכל שורות השעה נשמרו, מעדכן `ingest_state.last_fetched_hour`. ב-restart קוראים את הערך וממשיכים. (ראה גם נקודת תורפה #1 על off-by-one).

**ש: אין listing endpoint — איך אתה יודע איזה קובץ למשוך?**
ת: בונה את ה-URL לבד מה-high-water mark. פורמט: `YYYY-MM-DD-H.json.gz` — שים לב ש**שעת הקובץ לא מרופדת באפסים** (`...-3` ולא `...-03`), בעוד חודש ויום כן מרופדים. זה תואם את convention האמיתי של GH Archive.

**ש: איך אתה מטפל בכל מצב chaos?**
| Chaos | טיפול |
|-------|-------|
| Outage (503) | sleep 30 שניות, return None, הלולאה מנסה שוב |
| Late file (404) | sleep 5 שניות, return None, מנסה שוב |
| Network error | sleep 10 שניות, return None |
| Schema drift (שדה חדש) | משתמש ב-`.get()` עם defaults; שדות לא מוכרים לא שוברים כלום |
| Slow file | `requests.get` פשוט מחכה עד שהקובץ מסתיים |
| Truncated file | **ראה נקודת תורפה #2 — זה הסיכון הגדול ביותר** |

**ש: מה קורה עם event פגום?**
ת: `try/except` סביב `save_event` עושה rollback ומדלג בלי לקרוס. שורות JSON שבורות מסוננות ב-`parse_event` שמחזיר None.

---

### ד. שאלה-אחר-שאלה (Q1–Q5)

**Q1 — top 3 שפות per developer (10+ merged PRs):** `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` לקבל top 3 לכל אחד, ואז סינון `>= 10`.

**Q2 — top pushers מול top commit authors ל-50 repos הפעילים:** שני sub-queries עם ROW_NUMBER, JOIN על repo, `STRING_AGG` להציג זה לצד זה. מסנן forced pushes כי הם לא תרומה אמיתית.

**Q3 — top 10 זוגות שעבדו על 3+ repos משותפים:** SELF JOIN; התנאי `a.actor < b.actor` מונע כפילויות וזוג-עם-עצמו.

**Q4 — funnel של star → fork → PR:** repos עם 500+ stars, וכמה מהם קיבלו fork / PR.

**Q5 — רשת שיתוף פעולה (Neo4j):** מ-seed actor, `CONTRIBUTED_TO` hop אחד = distance 1, שני hops = distance 2, עם `UNION`. זה בדיוק מה ש-graph DB נועד לו.

---

### ה. Neo4j / sync

**ש: איך הנתונים מגיעים ל-Neo4j?**
ת: `neo4j_sync.py` מרענן את ה-materialized view, שולף את כל זוגות (actor, repo), ויוצר nodes (`Developer`, `Repo`) וקשרי `CONTRIBUTED_TO` ב-batches של 1000 (כדי לא להעמיס CPU). יוצר indexes על שמות לפני ה-MERGE כדי להאיץ.

**ש: למה sync ידני ולא בזמן אמת?**
ת: Q5 רצה רק בדיפנס, אז אין טעם לשלם overhead של dual-write בכל event. ה-Postgres הוא source of truth; Neo4j הוא projection נגזר.

---

## 4. ✅ תיקונים שבוצעו — ומה להגיד עליהם אם ישאלו

אלה היו 7 הפערים בין ה-BRIEF למימוש הראשוני. **כולם תוקנו.** אם הבוחן נוגע באחד מהם — תוכל להראות שטיפלת בו ולהסביר איך.

**#1 — restart בלי כפילויות (off-by-one).** ✅
ה-high-water mark נשמר אחרי שעיבוד שעה הסתיים. תוקן ב-`main.py`: ב-restart מתחילים מ-`last_hour + 1 hour`, כך ששעה שכבר נשמרה לא נמשכת שוב. ה-commit הוא per-שעה, אז שעה שנקטעה באמצע פשוט תיעבד מחדש נקי — בלי לאבד ובלי לכפול.

**#2 — Truncated file לא מפיל את הלולאה.** ✅
`parse_file` ב-`normalizer.py` משתמש ב-`zlib.decompressobj` במקום `gzip.decompress`, ותופס `EOFError`/`zlib.error` — שומר את כל השורות השלמות עד נקודת החיתוך. בנוסף עטפנו את הקריאה ב-try/except ב-`main.py`. נבדק: קובץ חתוך מחזיר את השורות התקינות בלי קריסה. זה אחד ממצבי ה-chaos שהבוחן יפעיל.

**#3 — Q1 לפי `pr_author` ולא `actor`.** ✅
השפות הן של מי שפתח את ה-PR. השאילתה מקבצת לפי `pr_author`, והסף של 10 PRs ממוזגים הוא על סך כל ה-PRs של המפתח.

**#4 — Q3 עם הגדרת contributor נכונה + tie-break.** ✅
Q3 רץ על ה-materialized view `contributions` (= PR author או commit author, לא ה-actor הגולמי), עם tie-break לפי `combined_contributions`. ה-view עודכן לכלול עמודת ספירה.

**#5 — Q4 עם חלונות הזמן.** ✅
Q4 הוא funnel per-repo אמיתי: אחוז ה-stargazers שעשו fork תוך יומיים, ואחוז ה-forkers שפתחו PR תוך 5 ימים — מצורף לפי אותו actor+repo עם `INTERVAL` על `created_at`. נבדק על הנתונים.

**#6 — Q5 מחזיר את ה-repos המחברים.** ✅
ה-Cypher מחזיר `connecting_repos` (collect של ה-repos), ומונע ספירה כפולה של מי שכבר במרחק 1 (`NOT (seed)-...-(d2)`).

**#7 — SQL injection ב-`set_last_fetched_hour`.** ✅
הוחלף מ-f-string ל-parameterized query (`cursor.execute(sql, (hour, hour))`).

> אם הבוחן יפעיל `make vendor-chaos` — המערכת שורדת את כל 5 המצבים (slow/late/truncated/drift/outage). ה-truncated (#2) היה הסיכון הגדול וטופל.

---

## 5. צ'קליסט לפני ההצגה

- [ ] `docker compose down -v` ואז `docker compose up -d --build` — התחלה נקייה (**חובה `--build`** אחרת הקוד הישן ירוץ!)
- [ ] `docker compose ps` — לוודא הכל healthy
- [ ] להמתין שה-replay יסתיים (~5 דקות wall-clock) לפני שמריצים שאילתות
- [ ] להריץ `REFRESH MATERIALIZED VIEW contributions;` לפני Q3/Q5
- [ ] להריץ `docker exec crater-ingest python neo4j_sync.py` לפני Q5
- [ ] לוודא ש-pgAdmin (`localhost:15432`) ו-Neo4j Browser (`localhost:17474`) נגישים
- [ ] לבחור seed actor אמיתי שקיים בנתונים ל-Q5 (לבדוק מראש שיש לו שכנים)
- [ ] לתרגל `docker compose restart ingest` באמצע — להראות שזה שורד (ממשיך מהשעה הבאה, בלי כפילויות)
- [ ] לתרגל `make vendor-chaos` — לוודא שלא קורס (במיוחד truncated)

---

## 6. שאלות "מלכודת" שכדאי לחזות

- *"מה קורה אם ה-ingest קורס באמצע עיבוד שעה?"* → ה-commit הוא per-hour, אז שעה חלקית לא נשמרת (rollback). ב-restart ה-high-water mark מצביע על השעה האחרונה שהושלמה, וממשיכים מהשעה שאחריה — בלי לאבד ובלי לכפול.
- *"כמה נתונים יש לך בסך הכל?"* → דע את המספר בערך (מיליוני שורות, ~200k events לקובץ × מספר שעות בחלון של 6 ימים).
- *"למה לא נרמלת actors/repos לטבלאות נפרדות עם FK?"* → trade-off: שמות כ-VARCHAR פשוטים יותר ל-pipeline; נרמול היה חוסך מקום אבל מוסיף JOINs. עבור היקף הפרויקט בחרתי פשטות.
- *"איך תתמודד עם 10× נתונים?"* → partitioning לפי זמן, COPY במקום INSERT בודד, batch inserts, ואולי columnar store לאנליטיקה.
- *"למה INSERT אחד בכל פעם ולא batch/COPY?"* → פשטות; בקנה מידה גדול הייתי עובר ל-`execute_values`/COPY (נקודת שיפור כנה).
