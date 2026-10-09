"""Create a separate local database/account; never change an existing installation."""
from pathlib import Path
import secrets,pymysql,os
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
local=ROOT/'.env.local'
if local.exists():
    print('Local database configuration already exists; not overwritten.')
    raise SystemExit(0)
conn=pymysql.connect(unix_socket=str(ROOT/'.runtime/mysql.sock'),user='root')
app_password=secrets.token_urlsafe(36)
root_password=secrets.token_urlsafe(36)
with conn.cursor() as c:
    c.execute('CREATE DATABASE IF NOT EXISTS ai_memories_local CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    c.execute("CREATE USER 'ai_memories'@'127.0.0.1' IDENTIFIED BY %s",(app_password,))
    c.execute("GRANT ALL ON ai_memories_local.* TO 'ai_memories'@'127.0.0.1'")
    c.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s",(root_password,))
conn.close()
local.write_text(f'DATABASE_URL=mysql+pymysql://ai_memories:{app_password}@127.0.0.1:3307/ai_memories_local?charset=utf8mb4\n')
local.chmod(0o600)
admin=ROOT/'.runtime/mysql-admin.cnf'
admin.write_text(f'[client]\nuser=root\npassword={root_password}\nsocket={ROOT / ".runtime/mysql.sock"}\n')
admin.chmod(0o600)
print('Created isolated MySQL database and local credentials (values not printed).')
