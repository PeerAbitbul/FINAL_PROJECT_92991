# בחירת Storage — הצדקה

## מה בחרנו

**PostgreSQL** לשאילתות Q1-Q4 — כל האנליטיקה.
**Neo4j** לשאילתה Q5 — graph traversal.

---

## למה PostgreSQL לQ1-Q4

כל ארבע השאילתות הן מסוג "סנן, קבץ, ספור" — בדיוק מה שרלציונלי עושה הכי טוב.

| שאילתה | למה Postgres מתאים |
|--------|-------------------|
| Q1 — שפות per actor | GROUP BY פשוט על עמודות מסודרות |
| Q2 — commit authors vs pushers | JOIN בין שתי טבלאות, TOP N |
| Q3 — developer pairs | self JOIN על `contributions` materialized view |
| Q4 — star→fork→PR funnel | סינון לפי זמן ואותו actor, SQL רגיל |

בנוסף — הנתונים מגיעים כ-JSON פולימורפי. PostgreSQL מאפשר לשלוף את השדות הרלוונטיים מה-JSON ולשמור אותם בעמודות מסודרות, מה שהופך את השאילתות למהירות וברורות.

---

## למה Neo4j לQ5

Q5 שואלת "מי מכיר את מי במרחק 1 ו-2" — זו שאילתת graph traversal.

PostgreSQL יכול לענות על זה עם recursive CTE, אבל ככל שהגרף גדל ה-JOIN על JOIN נהיה יקר.

Neo4j בנוי בדיוק לשאלות כאלה — הוא מאחסן קשרים בצורה שמאפשרת טיול בגרף במהירות.

**חשוב:** Q5 אפשרי לגמרי ב-PostgreSQL עם recursive CTE — בחרנו Neo4j כדי ללמוד לעבוד עם graph database ולהדגים sync בין שני databases.

---

## אלטרנטיבות שדחינו

**PostgreSQL בלבד**
אפשרי — recursive CTE מספיק לQ5. דחינו כדי ללמוד Neo4j.

**DuckDB**
columnar — מצוין לaggregations כמו Q1. אבל אין graph support, ואין persistence טובה בcontainer. לא מתאים לפרויקט שצריך לשרוד restart.

**MongoDB**
document store — טוב לאחסון JSON גולמי, אבל שאילתות אנליטיות מורכבות כמו Q2 וQ3 הרבה יותר מסורבלות מ-SQL.

**Redis**
in-memory — כל הנתונים חיים ב-RAM. 34M שורות זה יקר מדי בזיכרון. לא מתאים לאחסון, מתאים לcaching ותזמון — לא צריך כאן.

**PostgreSQL + Neo4j + Redis (polyglot מלא)**
הוספת Redis לא מוסיפה ערך — ה-ingest הוא sequential, אין צורך בתיאום מקביל.

---

## סיכום

| שאילתה | Database | סיבה |
|--------|----------|------|
| Q1, Q2, Q3, Q4 | PostgreSQL | סנן, קבץ, ספור — רלציונלי |
| Q5 | Neo4j | graph traversal |
