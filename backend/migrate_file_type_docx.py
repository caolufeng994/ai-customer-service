"""
迁移脚本：kb_documents.file_type 枚举增加 'docx'。

背景：新增 Word(.docx) 文档解析能力后，上传的 docx 需要写入 file_type 列，
而该列原为 ENUM('txt','md','pdf')，存量库直接插入会报错。

幂等：已包含 'docx' 时跳过。仅扩展枚举取值，不改动任何存量数据。

运行：python migrate_file_type_docx.py
"""
import pymysql

TARGET_DEF = "enum('txt','md','pdf','docx')"


def load_env(path: str = ".env") -> dict:
    cfg = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def main() -> None:
    cfg = load_env()
    conn = pymysql.connect(
        host=cfg.get("DB_HOST", "127.0.0.1"),
        port=int(cfg.get("DB_PORT", 3306)),
        user=cfg.get("DB_USER", "root"),
        password=cfg.get("DB_PASSWORD", ""),
        database=cfg.get("DB_NAME", ""),
        autocommit=True,
    )
    try:
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM kb_documents LIKE 'file_type'")
        row = cur.fetchone()
        if not row:
            print("column file_type not found -> abort")
            return

        current = row[1].lower().replace(" ", "")
        print("current:", current)
        if "docx" in current:
            print("'docx' already allowed -> skip")
        else:
            cur.execute(
                "ALTER TABLE kb_documents "
                "MODIFY COLUMN file_type ENUM('txt','md','pdf','docx') NOT NULL"
            )
            print("ALTER done: file_type now allows docx")

        cur.execute("SHOW COLUMNS FROM kb_documents LIKE 'file_type'")
        print("verify:", cur.fetchone()[1])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
