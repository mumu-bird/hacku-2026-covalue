import json
from contextlib import contextmanager

from sqlalchemy import create_engine, event

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, initials TEXT NOT NULL, headline TEXT NOT NULL, reviewer INTEGER NOT NULL DEFAULT 0, blocked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL CHECK(kind IN ('REQUEST','OFFER')), title TEXT NOT NULL, category TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN', version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), category TEXT NOT NULL, kind TEXT NOT NULL, peer_id TEXT REFERENCES users(id), agreement_id TEXT, obligation_id TEXT, data TEXT NOT NULL, status TEXT NOT NULL, quality REAL, created TEXT NOT NULL, reviewer_id TEXT REFERENCES users(id));
CREATE UNIQUE INDEX IF NOT EXISTS unique_obligation_evidence ON evidence(obligation_id) WHERE obligation_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id), requester_id TEXT NOT NULL REFERENCES users(id), provider_id TEXT NOT NULL REFERENCES users(id), mode TEXT NOT NULL, path TEXT NOT NULL, scope_version INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preferences(proposal_id TEXT NOT NULL REFERENCES proposals(id), user_id TEXT NOT NULL REFERENCES users(id), scope_version INTEGER NOT NULL, kind TEXT NOT NULL, value INTEGER NOT NULL CHECK(value>=0), PRIMARY KEY(proposal_id,user_id));
CREATE TABLE IF NOT EXISTS perspectives(proposal_id TEXT NOT NULL REFERENCES proposals(id), user_id TEXT NOT NULL REFERENCES users(id), scope_version INTEGER NOT NULL, received_value INTEGER NOT NULL CHECK(received_value>=0), reason TEXT NOT NULL, shared INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL, PRIMARY KEY(proposal_id,user_id));
CREATE TABLE IF NOT EXISTS agreements(id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id), listing_id TEXT NOT NULL REFERENCES listings(id), requester_id TEXT NOT NULL REFERENCES users(id), provider_id TEXT NOT NULL REFERENCES users(id), mode TEXT NOT NULL, status TEXT NOT NULL, terms_version INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consents(target TEXT NOT NULL, target_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), version INTEGER NOT NULL, created TEXT NOT NULL, PRIMARY KEY(target,target_id,user_id,version));
CREATE TABLE IF NOT EXISTS stages(id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL REFERENCES agreements(id), round_no INTEGER NOT NULL, status TEXT NOT NULL, UNIQUE(agreement_id,round_no));
CREATE TABLE IF NOT EXISTS obligations(id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL REFERENCES agreements(id), stage_id TEXT NOT NULL REFERENCES stages(id), provider_id TEXT NOT NULL REFERENCES users(id), recipient_id TEXT NOT NULL REFERENCES users(id), seq INTEGER NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS time_entries(id TEXT PRIMARY KEY, obligation_id TEXT NOT NULL REFERENCES obligations(id), provider_id TEXT NOT NULL REFERENCES users(id), component TEXT NOT NULL, minutes INTEGER NOT NULL CHECK(minutes>=0), status TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(obligation_id,component));
CREATE TABLE IF NOT EXISTS payment_intents(id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL REFERENCES agreements(id), stage_id TEXT NOT NULL REFERENCES stages(id), payer_id TEXT NOT NULL REFERENCES users(id), payee_id TEXT NOT NULL REFERENCES users(id), amount INTEGER NOT NULL CHECK(amount>=0), reserved INTEGER NOT NULL DEFAULT 0, released INTEGER NOT NULL DEFAULT 0, refunded INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'NEW', CHECK(reserved>=released+refunded), UNIQUE(stage_id));
CREATE TABLE IF NOT EXISTS accounts(user_id TEXT PRIMARY KEY REFERENCES users(id), available INTEGER NOT NULL CHECK(available>=0), reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0));
CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES payment_intents(id), action TEXT NOT NULL, source TEXT NOT NULL, destination TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>=0), created TEXT NOT NULL, business_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL REFERENCES agreements(id), user_id TEXT NOT NULL REFERENCES users(id), start TEXT NOT NULL, end TEXT NOT NULL, UNIQUE(agreement_id,user_id));
CREATE TABLE IF NOT EXISTS disputes(id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL REFERENCES agreements(id), author_id TEXT NOT NULL REFERENCES users(id), obligation_id TEXT REFERENCES obligations(id), status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS closeouts(id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL REFERENCES agreements(id), version INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES users(id), entity TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(user_id TEXT NOT NULL REFERENCES users(id), key TEXT NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL, result TEXT NOT NULL, status INTEGER NOT NULL, PRIMARY KEY(user_id,key));
"""


class DB:
    def __init__(self, path):
        self.engine = create_engine(
            "sqlite:///" + str(path),
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(self.engine, "connect")
        def settings(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")

        with self.engine.connect() as c:
            c.exec_driver_sql("PRAGMA journal_mode=WAL")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    c.exec_driver_sql(statement)
            c.commit()

    @contextmanager
    def tx(self):
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield Store(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def read(self):
        with self.engine.connect() as conn:
            yield Store(conn)


class Store:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        return self.conn.exec_driver_sql(sql, args)

    def all(self, sql, args=()):
        return [dict(r) for r in self.execute(sql, args).mappings()]

    def one(self, sql, args=()):
        r = self.execute(sql, args).mappings().first()
        return dict(r) if r else None

    def insert(self, table, **values):
        cols = ",".join(values)
        self.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({','.join('?' for _ in values)})",
            tuple(values.values()),
        )


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def unpack(row):
    if row and "data" in row:
        return {**row, "data": json.loads(row["data"])}
    return row
