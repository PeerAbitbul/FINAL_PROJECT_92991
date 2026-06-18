import os
import psycopg2
from neo4j import GraphDatabase


def get_connection():
    url = os.environ.get('POSTGRES_URL')
    connection = psycopg2.connect(url)
    return connection


def get_contributions():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("REFRESH MATERIALIZED VIEW contributions;")
        conn.commit()
        cursor.execute("""
            SELECT actor, repo FROM contributions
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching contributions: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def create_developers(tx, batch):
    tx.run("UNWIND $batch AS c MERGE (:Developer {name: c.actor})", batch=batch)

def create_repos(tx, batch):
    tx.run("UNWIND $batch AS c MERGE (:Repo {name: c.repo})", batch=batch)

def create_relationships(tx, batch):
    tx.run("""
        UNWIND $batch AS c
        MATCH (d:Developer {name: c.actor})
        MATCH (r:Repo {name: c.repo})
        MERGE (d)-[:CONTRIBUTED_TO]->(r)
    """, batch=batch)


def create_indexes(driver):
    with driver.session() as session:
        session.run("CREATE INDEX IF NOT EXISTS FOR (d:Developer) ON (d.name)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (r:Repo) ON (r.name)")


def sync_to_neo4j(contributions):
    driver = GraphDatabase.driver(
        os.environ.get('NEO4J_URL'),
        auth=("neo4j", os.environ.get('NEO4J_PASSWORD'))
    )
    create_indexes(driver)
    all_rows = [{"actor": actor, "repo": repo} for actor, repo in contributions]
    chunk_size = 1000
    total = len(all_rows)
    with driver.session() as session:
        for i in range(0, total, chunk_size):
            chunk = all_rows[i:i + chunk_size]
            session.execute_write(create_developers, chunk)
            session.execute_write(create_repos, chunk)
            session.execute_write(create_relationships, chunk)
            print(f"Synced {min(i + chunk_size, total)}/{total}", flush=True)
    driver.close()


if __name__ == "__main__":
    print("Fetching contributions from Postgres...", flush=True)
    contributions = get_contributions()
    print(f"Got {len(contributions)} contributions, syncing to Neo4j...", flush=True)
    sync_to_neo4j(contributions)
    print("Done.", flush=True)
