# פקודות שימושיות

## הפעלה וכיבוי

```bash
# הפעלת כל השירותים
docker compose up -d --build

# כיבוי (שומר נתונים)
docker compose down

# כיבוי + מחיקת כל הנתונים (התחלה מחדש)
docker compose down -v

# בנייה מחדש של service ספציפי
docker compose up -d --build ingest
```

---

## ניטור

```bash
# logs של ingest
docker compose logs -f ingest

# logs של data-init
docker compose logs -f data-init

# סטטוס כל השירותים
docker compose ps

# בדיקת vendor
curl -s http://localhost:18400/healthz | python3 -m json.tool

# איפה השעון הסימולטיבי עכשיו
curl -s http://localhost:18400/simulated_now | python3 -m json.tool

# בדיקה אם קובץ מסוים זמין
curl -I http://localhost:18400/2024-01-15-0.json.gz
```

---

## בדיקת נתונים ב-Postgres

```bash
# כמה נתונים נכנסו לכל טבלה
docker exec -it crater-postgres psql -U postgres -d crater -c "
SELECT 'push_events' as table, COUNT(*) FROM push_events
UNION ALL
SELECT 'push_commits', COUNT(*) FROM push_commits
UNION ALL
SELECT 'pull_request_events', COUNT(*) FROM pull_request_events
UNION ALL
SELECT 'watch_events', COUNT(*) FROM watch_events
UNION ALL
SELECT 'fork_events', COUNT(*) FROM fork_events
UNION ALL
SELECT 'raw_events', COUNT(*) FROM raw_events;
"

# כניסה ל-psql
docker exec -it crater-postgres psql -U postgres -d crater

# high-water mark — עד לאיזה קובץ הגענו
docker exec -it crater-postgres psql -U postgres -d crater -c "SELECT * FROM ingest_state;"
```

---

## לפני ההגשה — סדר הפעולות

```bash
# 1. הפעל את כל השירותים
docker compose up -d

# 2. המתן שה-ingest יעלה (כ-10 שניות) ובדוק שהוא רץ
docker compose logs --tail=5 ingest

# 3. סנכרן נתונים ל-Neo4j (לוקח כ-5 דקות)
docker exec crater-ingest python neo4j_sync.py

# 4. פתח pgAdmin לשאילתות Q1-Q4
#    Host: localhost | Port: 15432 | User: postgres | Password: password | DB: crater

# 5. פתח Neo4j Browser לשאילתה Q5
#    http://localhost:17474/browser
#    Connection URL: neo4j://localhost:17487
#    User: neo4j | Password: password

# 6. הרץ את כל השאילתות מ-docs/queries.sql
```

---

## Chaos modes

```bash
# הפעלת chaos
make vendor-chaos

# כיבוי chaos
make vendor-calm
```
