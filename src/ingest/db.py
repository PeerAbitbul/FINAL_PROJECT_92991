import os
import psycopg2


def get_connection():
    url = os.environ.get('POSTGRES_URL')
    connection = psycopg2.connect(url)
    return connection


def execute_sql(sql):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()


def create_tables():
    execute_sql("""
        CREATE TABLE IF NOT EXISTS push_events (
            push_event_id SERIAL PRIMARY KEY,
            actor VARCHAR(255),
            repo VARCHAR(255),
            created_at TIMESTAMP,
            forced BOOLEAN
        )
    """)

    execute_sql("""
        CREATE TABLE IF NOT EXISTS push_commits (
            push_commit_id SERIAL PRIMARY KEY,
            push_event_id INTEGER REFERENCES push_events(push_event_id),
            author_name VARCHAR(255),
            author_email VARCHAR(255)
        )
    """)

    execute_sql("""
        CREATE TABLE IF NOT EXISTS pull_request_events (
            pull_request_event_id SERIAL PRIMARY KEY,
            actor VARCHAR(255),
            pr_author VARCHAR(255),
            repo VARCHAR(255),
            language VARCHAR(100),
            action VARCHAR(50),
            merged BOOLEAN,
            created_at TIMESTAMP
        )
    """)

    execute_sql("""
        CREATE TABLE IF NOT EXISTS watch_events (
            watch_event_id SERIAL PRIMARY KEY,
            actor VARCHAR(255),
            repo VARCHAR(255),
            created_at TIMESTAMP
        )
    """)

    execute_sql("""
        CREATE TABLE IF NOT EXISTS fork_events (
            fork_event_id SERIAL PRIMARY KEY,
            actor VARCHAR(255),
            repo VARCHAR(255),
            created_at TIMESTAMP
        )
    """)

    execute_sql("""
        CREATE TABLE IF NOT EXISTS raw_events (
            raw_event_id SERIAL PRIMARY KEY,
            type VARCHAR(100),
            actor VARCHAR(255),
            repo VARCHAR(255),
            created_at TIMESTAMP,
            payload JSONB
        )
    """)

    execute_sql("""
        CREATE TABLE IF NOT EXISTS ingest_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            last_fetched_hour VARCHAR(20)
        )
    """)

    execute_sql("CREATE INDEX IF NOT EXISTS idx_pr_author ON pull_request_events(pr_author)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_pr_repo ON pull_request_events(repo)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_pr_merged_action ON pull_request_events(merged, action)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_pr_created_at ON pull_request_events(created_at)")

    execute_sql("CREATE INDEX IF NOT EXISTS idx_push_repo ON push_events(repo)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_push_actor ON push_events(actor)")

    execute_sql("CREATE INDEX IF NOT EXISTS idx_commits_push_id ON push_commits(push_event_id)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_commits_author ON push_commits(author_name, author_email)")

    execute_sql("CREATE INDEX IF NOT EXISTS idx_watch_repo ON watch_events(repo)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_watch_actor_repo ON watch_events(actor, repo)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_watch_created_at ON watch_events(created_at)")

    execute_sql("CREATE INDEX IF NOT EXISTS idx_fork_actor_repo ON fork_events(actor, repo)")
    execute_sql("CREATE INDEX IF NOT EXISTS idx_fork_created_at ON fork_events(created_at)")

   
    execute_sql("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS contributions AS
            SELECT pr_author AS actor, repo FROM pull_request_events
            UNION
            SELECT pc.author_name AS actor, pe.repo
            FROM push_commits pc
            JOIN push_events pe ON pc.push_event_id = pe.push_event_id
    """)

    print("All tables, indexes, and views created successfully.")


def save_event(event, conn):
    cursor = conn.cursor()

    if event['type'] == 'push':
        cursor.execute("""
            INSERT INTO push_events (actor, repo, created_at, forced)
            VALUES (%s, %s, %s, %s)
            RETURNING push_event_id
        """, (event['actor'], event['repo'], event['created_at'], event['forced']))
        push_event_id = cursor.fetchone()[0]

        for commit in event['commits']:
            cursor.execute("""
                INSERT INTO push_commits (push_event_id, author_name, author_email)
                VALUES (%s, %s, %s)
            """, (push_event_id, commit['author_name'], commit['author_email']))

    elif event['type'] == 'pull_request':
        cursor.execute("""
            INSERT INTO pull_request_events (actor, pr_author, repo, language, action, merged, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (event['actor'], event['pr_author'], event['repo'], event['language'],
              event['action'], event['merged'], event['created_at']))

    elif event['type'] == 'watch':
        cursor.execute("""
            INSERT INTO watch_events (actor, repo, created_at)
            VALUES (%s, %s, %s)
        """, (event['actor'], event['repo'], event['created_at']))

    elif event['type'] == 'fork':
        cursor.execute("""
            INSERT INTO fork_events (actor, repo, created_at)
            VALUES (%s, %s, %s)
        """, (event['actor'], event['repo'], event['created_at']))

    elif event['type'] == 'raw':
        import json
        payload_str = json.dumps(event['payload']).replace('\\u0000', '')
        cursor.execute("""
            INSERT INTO raw_events (type, actor, repo, created_at, payload)
            VALUES (%s, %s, %s, %s, %s)
        """, (event['event_type'], event['actor'], event['repo'],
              event['created_at'], payload_str))

    conn.commit()
    cursor.close()


def get_last_fetched_hour():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_fetched_hour FROM ingest_state WHERE id = 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


def set_last_fetched_hour(hour):
    execute_sql(f"""
        INSERT INTO ingest_state (id, last_fetched_hour)
        VALUES (1, '{hour}')
        ON CONFLICT (id) DO UPDATE SET last_fetched_hour = '{hour}'
    """)
