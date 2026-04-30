from sqlalchemy import text

SQL = "ALTER TABLE citizen_conversations ADD COLUMN IF NOT EXISTS last_bot_message TEXT;"


def run(conn) -> None:
    conn.execute(text(SQL))
