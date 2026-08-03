import re, pymysql
cfg = {}
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" in line:
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
host = cfg.get("DB_HOST", "127.0.0.1")
port = int(cfg.get("DB_PORT", 3306))
user = cfg.get("DB_USER", "root")
pwd = cfg.get("DB_PASSWORD", "")
db = cfg.get("DB_NAME", "")
conn = pymysql.connect(host=host, port=port, user=user, password=pwd, database=db, autocommit=True)
cur = conn.cursor()
cur.execute("SHOW COLUMNS FROM kb_documents LIKE 'user_id'")
if cur.fetchone():
    print("user_id column already exists -> skip")
else:
    cur.execute("ALTER TABLE kb_documents ADD COLUMN user_id BIGINT NULL, ADD INDEX idx_kb_user (user_id)")
    print("ALTER done: added user_id column + index")
cur.execute("SHOW COLUMNS FROM kb_documents LIKE 'user_id'")
print("verify:", cur.fetchone())
conn.close()
