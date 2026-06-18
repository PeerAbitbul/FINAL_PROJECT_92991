-- Q1: Top 3 languages per actor (actors with >= 10 merged PRs)
SELECT a.actor, a.language, a.merged_prs
FROM (
    SELECT actor,
           language,
           count(merged) AS merged_prs,
           ROW_NUMBER() OVER (
               PARTITION BY actor
               ORDER BY count(merged) DESC
           ) as rownumber
    FROM public.pull_request_events
    WHERE merged = true AND action = 'closed'
    GROUP BY actor, language
) a
WHERE a.rownumber <= 3 AND merged_prs >= 10;

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

-- Q3: Top 10 developer pairs sharing >= 3 repos
WITH combined_events AS (
    SELECT repo, actor FROM public.pull_request_events
    UNION
    SELECT repo, actor FROM public.push_events
)
SELECT a.actor AS actor_1, b.actor AS actor_2, COUNT(*) AS shared_repos
FROM combined_events a
JOIN combined_events b ON a.repo = b.repo
WHERE a.actor < b.actor
GROUP BY a.actor, b.actor
HAVING COUNT(*) >= 3
ORDER BY shared_repos DESC
LIMIT 10;

-- Q4: Star -> Fork -> PR funnel (repos with 500+ WatchEvents)
SELECT
    (SELECT COUNT(*)
     FROM (
         SELECT repo FROM watch_events
         GROUP BY repo
         HAVING count(repo) > 500
     ) t) AS stars_500_plus,

    (SELECT COUNT(DISTINCT repo)
     FROM fork_events
     WHERE repo IN (
         SELECT repo FROM watch_events
         GROUP BY repo
         HAVING count(repo) > 500
     )) AS got_fork,

    (SELECT COUNT(DISTINCT repo)
     FROM pull_request_events
     WHERE repo IN (
         SELECT repo FROM watch_events
         GROUP BY repo
         HAVING count(repo) > 500
     )) AS got_pr;

     
-- Q5: Collaboration network from seed actor (Neo4j Cypher)
-- Neo4j Browser: http://localhost:17474/browser
-- Connection URL: neo4j://localhost:17487  |  User: neo4j  |  Password: password
-- Seed actor: mkarmark (255 repos, active human developer in dataset)

// Distance 1 — developers who contributed to the same repo as seed
MATCH (seed:Developer {name: "mkarmark"})
MATCH (seed)-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d1:Developer)
WHERE d1 <> seed
RETURN DISTINCT d1.name AS developer, 1 AS distance

UNION

// Distance 2 — developers who collaborated with distance-1 developers
MATCH (seed:Developer {name: "mkarmark"})
MATCH (seed)-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d1:Developer)
MATCH (d1)-[:CONTRIBUTED_TO]->(:Repo)<-[:CONTRIBUTED_TO]-(d2:Developer)
WHERE d2 <> seed
RETURN DISTINCT d2.name AS developer, 2 AS distance
