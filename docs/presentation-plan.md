# תוכנית הצגה — Crater

---

## שלב 0 — איפוס מלא (לפני ההצגה)

```bash
# מחיקת כל הcontainers והנתונים
docker compose down -v

# הפעלה מחדש מאפס
docker compose up -d --build
```

**מה להגיד:** "אני מתחיל מאפס — אין נתונים, אין היסטוריה. הכל ייבנה live."

---

## שלב 1 — הפעלת המערכת

```bash
docker compose up -d --build
make run
```

**מה להגיד:** "אני מפעיל את כל השירותים — Postgres, Neo4j, ה-vendor mock שמדמה את GitHub Archive, ושירות ה-ingest שכתבתי."

---

## שלב 2 — בדיקה שהכל עלה

```bash
docker compose ps
```

**מה להגיד:** "אפשר לראות שכל השירותים Healthy. ה-ingest מחכה ל-Postgres ול-Neo4j לפני שהוא עולה — זה dependency management."

---

## שלב 3 — בדיקה שנתונים נכנסים ל-Postgres

```bash
docker compose logs --tail=10 ingest
```

**מה להגיד:** "ה-ingest מוריד קבצים שעה אחרי שעה מה-vendor. כל קובץ הוא ~200k events. הוא שומר לפי סוג event לטבלה נפרדת."

```bash
docker exec -it crater-postgres psql -U postgres -d crater -c "
SELECT 'push_events' as table, COUNT(*) FROM push_events
UNION ALL
SELECT 'pull_request_events', COUNT(*) FROM pull_request_events
UNION ALL
SELECT 'watch_events', COUNT(*) FROM watch_events
UNION ALL
SELECT 'fork_events', COUNT(*) FROM fork_events
UNION ALL
SELECT 'raw_events', COUNT(*) FROM raw_events;
"
```

**מה להגיד:** "אפשר לראות שיש מיליוני records. כל event type יושב בטבלה משלו עם indexes מותאמים לשאילתות."

---

## שלב 4 — high-water mark

```bash
docker exec -it crater-postgres psql -U postgres -d crater -c "SELECT * FROM ingest_state;"
```

**מה להגיד:** "ה-pipeline שורד restart — הוא שומר עד לאיזה קובץ הגיע. אם ה-container נופל ועולה שוב, הוא ממשיך מהשעה הבאה — לא מעבד מחדש שעה שכבר נשמרה, כך שאין כפילויות. ה-commit הוא per-שעה, אז שעה שנקטעה באמצע פשוט תיעבד מחדש נקי."


---

## שלב 5 — הרצת שאילתות ב-pgAdmin

פתח pgAdmin:
- Host: `localhost` | Port: `15432` | User: `postgres` | Password: `password` | DB: `crater`

### Q1 — Top 3 שפות לכל developer (עם 10+ merged PRs)
```sql
SELECT a.pr_author, a.language, a.merged_prs
FROM (
    SELECT pr_author, language, count(*) AS merged_prs,
           ROW_NUMBER() OVER (PARTITION BY pr_author ORDER BY count(*) DESC) as rownumber
    FROM public.pull_request_events
    WHERE merged = true AND action = 'closed'
    GROUP BY pr_author, language
) a
WHERE a.rownumber <= 3
  AND a.pr_author IN (
      SELECT pr_author FROM public.pull_request_events
      WHERE merged = true AND action = 'closed'
      GROUP BY pr_author HAVING count(*) >= 10
  );
```
**מה להגיד:** "Q1 מראה את ה-expertise של כל developer — באיזה שפות הוא מיזג הכי הרבה PRs. חשוב: סופרים לפי `pr_author` (מי שפתח את ה-PR), לא לפי `actor` (מי שסגר/מיזג). הסף של 10 הוא על סך כל ה-PRs הממוזגים של המפתח. ROW_NUMBER() OVER PARTITION נותן top 3 לכל אחד."

---

### Q2 — Top 5 pushers vs top 5 commit authors לפי repo
```sql
SELECT aa.repo, aa.top_pushers, bb.top_commit_authors
FROM
(
    SELECT a.repo, STRING_AGG(a.actor, ' , ') as top_pushers
    FROM (
        SELECT repo, actor, count(actor),
               ROW_NUMBER() OVER (PARTITION BY repo ORDER BY count(actor) DESC) as rownumber
        FROM public.push_events
        WHERE repo IN (
            SELECT repo FROM pull_request_events
            GROUP BY repo ORDER BY COUNT(*) DESC LIMIT 50
        )
        GROUP BY repo, actor
    ) a
    WHERE a.rownumber <= 5
    GROUP BY a.repo
) aa
JOIN
(
    SELECT b.repo, STRING_AGG(b.author_name || ' + ' || b.author_email, ' , ') as top_commit_authors
    FROM (
        SELECT pe.repo, pc.author_name, pc.author_email,
               ROW_NUMBER() OVER (PARTITION BY pe.repo ORDER BY count(pc.author_name) DESC) as rownumber
        FROM public.push_commits pc
        JOIN public.push_events pe ON pc.push_event_id = pe.push_event_id
        WHERE pe.forced != true
          AND pe.repo IN (
              SELECT repo FROM pull_request_events
              GROUP BY repo ORDER BY COUNT(*) DESC LIMIT 50
          )
        GROUP BY pe.repo, pc.author_name, pc.author_email
    ) b
    WHERE b.rownumber <= 5
    GROUP BY b.repo
) bb ON aa.repo = bb.repo;
```
**מה להגיד:** "Q2 משווה מי דוחף קוד מול מי כותב קוד — לא תמיד אותו אדם. מסנן forced pushes כי הם לא תרומה אמיתית."

---

### Q3 — Top 10 זוגות developers שעבדו על 3+ repos משותפים
```sql
-- לפני הרצה: REFRESH MATERIALIZED VIEW contributions;
SELECT a.actor AS actor_1, b.actor AS actor_2,
       COUNT(*) AS shared_repos,
       SUM(a.contributions + b.contributions) AS combined_contributions
FROM contributions a
JOIN contributions b ON a.repo = b.repo AND a.actor < b.actor
GROUP BY a.actor, b.actor
HAVING COUNT(*) >= 3
ORDER BY shared_repos DESC, combined_contributions DESC
LIMIT 10;
```
**מה להגיד:** "Q3 מוצא זוגות developers שעובדים יחד. SELF JOIN על ה-materialized view `contributions` — שמגדיר תורם נכון: מי שפתח PR או כתב commit (לא ה-pusher/closer הגולמי). התנאי `a.actor < b.actor` מונע כפילויות וזוג-עם-עצמו. שובר שוויון לפי סך התרומות המשותפות."

---

### Q4 — Star → Fork → PR funnel (עם חלונות זמן)
```sql
WITH popular AS (
    SELECT repo FROM watch_events GROUP BY repo HAVING COUNT(*) >= 500
),
stars AS (
    SELECT actor, repo, MIN(created_at) AS starred_at
    FROM watch_events WHERE repo IN (SELECT repo FROM popular)
    GROUP BY actor, repo
),
forks AS (
    SELECT actor, repo, MIN(created_at) AS forked_at
    FROM fork_events WHERE repo IN (SELECT repo FROM popular)
    GROUP BY actor, repo
),
prs AS (
    SELECT pr_author AS actor, repo, MIN(created_at) AS opened_at
    FROM pull_request_events
    WHERE action = 'opened' AND repo IN (SELECT repo FROM popular)
    GROUP BY pr_author, repo
),
star_fork AS (
    SELECT s.repo, COUNT(*) AS stargazers,
           COUNT(*) FILTER (
               WHERE f.forked_at >= s.starred_at
                 AND f.forked_at <= s.starred_at + INTERVAL '2 days'
           ) AS converted_to_fork
    FROM stars s
    LEFT JOIN forks f ON f.actor = s.actor AND f.repo = s.repo
    GROUP BY s.repo
),
fork_pr AS (
    SELECT fo.repo, COUNT(*) AS forkers,
           COUNT(*) FILTER (
               WHERE p.opened_at >= fo.forked_at
                 AND p.opened_at <= fo.forked_at + INTERVAL '5 days'
           ) AS converted_to_pr
    FROM forks fo
    LEFT JOIN prs p ON p.actor = fo.actor AND p.repo = fo.repo
    GROUP BY fo.repo
)
SELECT pop.repo,
       (SELECT COUNT(*) FROM watch_events w WHERE w.repo = pop.repo) AS stars,
       ROUND(100.0 * sf.converted_to_fork / NULLIF(sf.stargazers, 0), 2) AS star_to_fork_pct,
       ROUND(100.0 * fp.converted_to_pr   / NULLIF(fp.forkers, 0), 2)   AS fork_to_pr_pct
FROM popular pop
LEFT JOIN star_fork sf ON sf.repo = pop.repo
LEFT JOIN fork_pr   fp ON fp.repo = pop.repo
ORDER BY stars DESC;
```
**מה להגיד:** "Q4 הוא funnel אמיתי per-repo עם חלונות זמן: איזה אחוז מה-stargazers עשו fork תוך **יומיים** מהכוכב, ואיזה אחוז מה-forkers פתחו PR תוך **5 ימים** מה-fork. אני מצרף star↔fork ו-fork↔PR לפי אותו actor ואותו repo, ובודק שההפרש ב-`created_at` (זמן-סימולציה) בתוך החלון. `FILTER` סופר רק את מי שהמיר בזמן."

---

## שלב 6 — סנכרון ל-Neo4j

```bash
docker exec crater-ingest python neo4j_sync.py
```

**מה להגיד:** "לפני Q5 אני מסנכרן את נתוני ה-contributions מ-Postgres ל-Neo4j. Neo4j מותאם לשאילתות graph traversal — למצוא מי מחובר למי דרך repos משותפים."

---

## שלב 7 — Q5 ב-Neo4j Browser

פתח: `http://localhost:17474/browser`
- Connection URL: `neo4j://localhost:17487`
- User: `neo4j` | Password: `password`

```cypher
// Distance 1 — שכנים ישירים + ה-repos המשותפים
MATCH (seed:Developer {name: "mkarmark"})-[:CONTRIBUTED_TO]->(r:Repo)<-[:CONTRIBUTED_TO]-(d1:Developer)
WHERE d1 <> seed
RETURN d1.name AS developer, 1 AS distance, collect(DISTINCT r.name) AS connecting_repos

UNION

// Distance 2 — דרך מתווך אחד + ה-repos של ה-hop השני (לא כולל מי שכבר במרחק 1)
MATCH (seed:Developer {name: "mkarmark"})-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d1:Developer)-[:CONTRIBUTED_TO]->(r2:Repo)<-[:CONTRIBUTED_TO]-(d2:Developer)
WHERE d2 <> seed
  AND NOT (seed)-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d2)
RETURN d2.name AS developer, 2 AS distance, collect(DISTINCT r2.name) AS connecting_repos
```

**מה להגיד:** "Q5 מראה את רשת שיתוף הפעולה סביב developer ספציפי, כולל ה-repos שמחברים (דרישת ה-BRIEF). Distance 1 = מי שעבד איתו ישירות על אותו repo; Distance 2 = מי שעבד עם אלה (וה-`NOT` מוודא שמי שכבר במרחק 1 לא נספר גם כמרחק 2). זה בדיוק מה ש-graph database נועד לו — ב-SQL זה היה דורש recursive CTE מסובך."

---

## נקודות מפתח לדיפנס

**למה PostgreSQL?**
טבלה לכל סוג event — שאילתות מהירות עם indexes מותאמים. JSONB ל-raw_events לסוגים לא מוכרים.

**למה Neo4j?**
שאילתות graph traversal (מי מחובר למי) — Neo4j עושה את זה באופן טבעי עם Cypher. ניתן לעשות גם עם recursive CTE ב-Postgres, בחרנו Neo4j ללמידה ולהדגמת sync בין שתי מערכות.

**מה ה-pipeline עושה?**
high-water mark pattern — שורד restart. כל event שגוי נדלג (try/except) בלי לקרוס. **קובץ gzip חתוך (truncated) לא מפיל את המערכת** — שומרים את החלק שהתפענח. סוגי events לא מוכרים נשמרים ב-raw_events.

