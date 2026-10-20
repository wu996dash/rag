"""账号与会话（MySQL 存储，D16）：users/tokens/conversations 三表。
连接参数来自 .env（MYSQL_HOST/PORT/USER/PASSWORD/DB），启动 init_db() 自动建库建表。"""
import hashlib, json, re, secrets, time
import pymysql
from . import config
NAME_RE = re.compile(r"^[\w\u4e00-\u9fff.-]{2,24}$")
def _conn(db=True):
    return pymysql.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                           user=config.MYSQL_USER, password=config.MYSQL_PASSWORD,
                           database=(config.MYSQL_DB if db else None),
                           charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)
def _hash(pw, salt):
    return hashlib.sha256((salt + pw + "viki-rag-pepper").encode("utf-8")).hexdigest()
def init_db():
    with _conn(db=False) as c:
        with c.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS `" + config.MYSQL_DB + "` CHARACTER SET utf8mb4")
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS users(
                username VARCHAR(32) PRIMARY KEY, salt VARCHAR(16) NOT NULL,
                pw_hash CHAR(64) NOT NULL, role VARCHAR(8) NOT NULL DEFAULT 'user',
                created VARCHAR(20)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            cur.execute("""CREATE TABLE IF NOT EXISTS tokens(
                token CHAR(32) PRIMARY KEY, username VARCHAR(32) NOT NULL,
                created VARCHAR(20), INDEX(username)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            cur.execute("""CREATE TABLE IF NOT EXISTS conversations(
                id VARCHAR(24) PRIMARY KEY, username VARCHAR(32) NOT NULL,
                title VARCHAR(120), messages JSON, saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX user_ts(username, saved_at)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
def create_default_admin():
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username='admin'")
            if cur.fetchone():
                return False
            salt = secrets.token_hex(8)
            cur.execute("INSERT INTO users(username,salt,pw_hash,role,created) VALUES(%s,%s,%s,'admin',%s)",
                        ("admin", salt, _hash("admin@2026", salt), time.strftime("%Y-%m-%d %H:%M")))
    return True
def register(username, password):
    if not username or not NAME_RE.match(username):
        return {"error": "用户名需为 2-24 位字母/数字/汉字"}
    if not password or len(password) < 6:
        return {"error": "密码至少 6 位"}
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                return {"error": "用户已存在"}
            salt = secrets.token_hex(8)
            cur.execute("INSERT INTO users(username,salt,pw_hash,role,created) VALUES(%s,%s,%s,'user',%s)",
                        (username, salt, _hash(password, salt), time.strftime("%Y-%m-%d %H:%M")))
    return {"ok": True, "username": username, "role": "user"}
def login(username, password):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username or "",))
            u = cur.fetchone()
            if not u or _hash(password or "", u["salt"]) != u["pw_hash"]:
                return {"error": "用户名或密码错误"}
            tok = secrets.token_hex(16)
            cur.execute("INSERT INTO tokens(token,username,created) VALUES(%s,%s,%s)",
                        (tok, username, time.strftime("%Y-%m-%d %H:%M")))
            return {"token": tok, "username": username, "role": u["role"]}
def user_of(token):
    if not token:
        return None
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT u.username,u.role FROM tokens t JOIN users u ON u.username=t.username WHERE t.token=%s", (token,))
            r = cur.fetchone()
            return {"username": r["username"], "role": r["role"]} if r else None
# ---------- 会话记忆：每人最近 5 条（MySQL） ----------
MAX_CONV = 5
def list_sessions(username):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT id,title,messages,saved_at FROM conversations WHERE username=%s ORDER BY saved_at DESC LIMIT %s", (username, MAX_CONV))
            out = []
            for r in cur.fetchall():
                msgs = r["messages"]
                if isinstance(msgs, str):
                    msgs = json.loads(msgs)
                out.append({"id": r["id"], "title": r["title"], "messages": msgs, "saved_at": str(r["saved_at"])})
            return out
def save_session(username, conv):
    cid = str(conv.get("id") or secrets.token_hex(6))[:24]
    title = str(conv.get("title") or (conv.get("messages") or [{}])[0].get("q", "对话"))[:60]
    msgs = json.dumps(conv.get("messages", [])[:40], ensure_ascii=False)
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("REPLACE INTO conversations(id,username,title,messages) VALUES(%s,%s,%s,%s)", (cid, username, title, msgs))
            cur.execute("""DELETE FROM conversations WHERE username=%s AND id NOT IN (
                SELECT id FROM (SELECT id FROM conversations WHERE username=%s ORDER BY saved_at DESC LIMIT %s) x)""",
                (username, username, MAX_CONV))
            cur.execute("SELECT COUNT(*) n FROM conversations WHERE username=%s", (username,))
            return cur.fetchone()["n"]