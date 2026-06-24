-- Q1: Top 3 languages per PR author (authors with >= 10 merged PRs)
-- ה"מפתח" הוא מי שפתח את ה-PR (pr_author), לא ה-actor שסגר/מיזג אותו.
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


-- Q2: Top 5 commit authors vs top 5 pushers for top 50 repos by PR activity
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
            GROUP BY repo
            ORDER BY COUNT(*) DESC
            LIMIT 50
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
              GROUP BY repo
              ORDER BY COUNT(*) DESC
              LIMIT 50
          )
        GROUP BY pe.repo, pc.author_name, pc.author_email
    ) b
    WHERE b.rownumber <= 5
    GROUP BY b.repo
) bb ON aa.repo = bb.repo;

-- Q3: Top 10 developer pairs sharing >= 3 distinct repos
-- "contributed" = PR author OR commit author — נלקח מ-contributions (materialized view).
-- מיון לפי מספר repos משותפים; שובר שוויון לפי סך התרומות המשותפות עליהם.
-- (לפני הרצה: REFRESH MATERIALIZED VIEW contributions;)
SELECT a.actor AS actor_1,
       b.actor AS actor_2,
       COUNT(*) AS shared_repos,
       SUM(a.contributions + b.contributions) AS combined_contributions
FROM contributions a
JOIN contributions b ON a.repo = b.repo AND a.actor < b.actor
GROUP BY a.actor, b.actor
HAVING COUNT(*) >= 3
ORDER BY shared_repos DESC, combined_contributions DESC
LIMIT 10;


-- Q4: Star -> Fork -> PR conversion funnel, per repo with >= 500 stars.
-- star_to_fork_pct = אחוז ה-stargazers שעשו fork תוך 2 ימי-סימולציה מהכוכב.
-- fork_to_pr_pct   = אחוז ה-forkers שפתחו PR תוך 5 ימי-סימולציה מה-fork.
-- ה-INTERVAL פועל על created_at שהוא זמן-הסימולציה של האירוע.
WITH popular AS (
    SELECT repo
    FROM watch_events
    GROUP BY repo
    HAVING COUNT(*) >= 500
),
stars AS (
    SELECT actor, repo, MIN(created_at) AS starred_at
    FROM watch_events
    WHERE repo IN (SELECT repo FROM popular)
    GROUP BY actor, repo
),
forks AS (
    SELECT actor, repo, MIN(created_at) AS forked_at
    FROM fork_events
    WHERE repo IN (SELECT repo FROM popular)
    GROUP BY actor, repo
),
prs AS (
    SELECT pr_author AS actor, repo, MIN(created_at) AS opened_at
    FROM pull_request_events
    WHERE action = 'opened' AND repo IN (SELECT repo FROM popular)
    GROUP BY pr_author, repo
),
star_fork AS (
    SELECT s.repo,
           COUNT(*) AS stargazers,
           COUNT(*) FILTER (
               WHERE f.forked_at IS NOT NULL
                 AND f.forked_at >= s.starred_at
                 AND f.forked_at <= s.starred_at + INTERVAL '2 days'
           ) AS converted_to_fork
    FROM stars s
    LEFT JOIN forks f ON f.actor = s.actor AND f.repo = s.repo
    GROUP BY s.repo
),
fork_pr AS (
    SELECT fo.repo,
           COUNT(*) AS forkers,
           COUNT(*) FILTER (
               WHERE p.opened_at IS NOT NULL
                 AND p.opened_at >= fo.forked_at
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


     
-- Q5: Collaboration network from seed actor (Neo4j Cypher)
-- Neo4j Browser: http://localhost:17474/browser
-- Connection URL: neo4j://localhost:17487  |  User: neo4j  |  Password: password
-- Seed actor: mkarmark (255 repos, active human developer in dataset)


// Distance 1 — developers who share a repo with the seed (+ the connecting repos)
MATCH (seed:Developer {name: "mkarmark"})-[:CONTRIBUTED_TO]->(r:Repo)<-[:CONTRIBUTED_TO]-(d1:Developer)
WHERE d1 <> seed
RETURN d1.name AS developer, 1 AS distance, collect(DISTINCT r.name) AS connecting_repos

UNION

// Distance 2 — developers reachable via one intermediate (+ the second-hop repos).
// ה-NOT מוציא את מי שכבר במרחק 1, כך שכל מפתח מופיע פעם אחת עם המרחק המינימלי.
MATCH (seed:Developer {name: "mkarmark"})-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d1:Developer)-[:CONTRIBUTED_TO]->(r2:Repo)<-[:CONTRIBUTED_TO]-(d2:Developer)
WHERE d2 <> seed
  AND NOT (seed)-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d2)
RETURN d2.name AS developer, 2 AS distance, collect(DISTINCT r2.name) AS connecting_repos

