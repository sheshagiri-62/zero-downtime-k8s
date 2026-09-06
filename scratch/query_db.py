import os
import pg8000.native

# Need to run from policy-engine directory or pass DATABASE_URL
db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
# parse url manually: postgresql://user:pass@host:port/db
# postgresql://postgres:postgres@localhost:5432/postgres
user = "postgres"
password = "postgres"
host = "localhost"
port = 5432
database = "appdb"

con = pg8000.native.Connection(user=user, password=password, host=host, port=port, database=database)

print("Recent Rollbacks:")
rows = con.run("SELECT id, decision_timestamp, action_taken, from_version, to_version, safety_score, snapshot, recovery_verified, time_to_recover_seconds FROM decision_log WHERE action_taken='rollback' ORDER BY decision_timestamp DESC LIMIT 5")
for r in rows:
    print(r)

print("\nRecent Promotes (Step 0 to 100%):")
rows = con.run("SELECT id, decision_timestamp, action_taken, from_version, to_version, safety_score, snapshot FROM decision_log WHERE action_taken='promote' ORDER BY decision_timestamp DESC LIMIT 10")
for r in rows:
    print(r)



con.close()
