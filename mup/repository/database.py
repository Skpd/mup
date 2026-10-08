"""
SQLite storage: one file, opened by the game server. The schema is a list of migrations, PRAGMA user_version counts
the ones applied. Add a migration to change the schema, never edit one that has shipped.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)

MIGRATIONS = [
    """
    CREATE TABLE accounts (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        personal_code TEXT NOT NULL DEFAULT '',
        ctl_code INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE characters (
        id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES accounts (id),
        slot INTEGER NOT NULL,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        class INTEGER NOT NULL,
        level INTEGER NOT NULL,
        exp INTEGER NOT NULL,
        level_up_points INTEGER NOT NULL,
        str INTEGER NOT NULL,
        agi INTEGER NOT NULL,
        vit INTEGER NOT NULL,
        ene INTEGER NOT NULL,
        life INTEGER NOT NULL,
        mana INTEGER NOT NULL,
        zen INTEGER NOT NULL,
        map INTEGER NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        dir INTEGER NOT NULL,
        pk_level INTEGER NOT NULL,
        pk_count INTEGER NOT NULL,
        ctl_code INTEGER NOT NULL,
        quest_state BLOB NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (account_id, slot)
    );
    -- item fields come with roadmap M3
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        serial INTEGER NOT NULL UNIQUE,
        owner TEXT NOT NULL CHECK (owner IN ('inventory', 'warehouse')),
        character_id INTEGER REFERENCES characters (id) ON DELETE CASCADE,
        account_id INTEGER REFERENCES accounts (id),
        slot INTEGER NOT NULL
    );
    CREATE TABLE skills (
        character_id INTEGER NOT NULL REFERENCES characters (id) ON DELETE CASCADE,
        slot INTEGER NOT NULL,
        number INTEGER NOT NULL,
        PRIMARY KEY (character_id, slot)
    );
    CREATE TABLE warehouses (
        account_id INTEGER PRIMARY KEY REFERENCES accounts (id),
        zen INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE guilds (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        master_id INTEGER REFERENCES characters (id),
        mark BLOB,
        score INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE guild_members (
        guild_id INTEGER NOT NULL REFERENCES guilds (id) ON DELETE CASCADE,
        character_id INTEGER NOT NULL UNIQUE REFERENCES characters (id) ON DELETE CASCADE,
        status INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, character_id)
    );
    """,
    # roadmap M3: the item fields, the table had no rows yet. Item bytes in docs/protocol-097.md
    """
    DROP TABLE items;
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        serial INTEGER NOT NULL UNIQUE,
        owner TEXT NOT NULL CHECK (owner IN ('inventory', 'warehouse')),
        character_id INTEGER REFERENCES characters (id) ON DELETE CASCADE,
        account_id INTEGER REFERENCES accounts (id),
        slot INTEGER NOT NULL,
        type INTEGER NOT NULL,
        level INTEGER NOT NULL DEFAULT 0,
        durability INTEGER NOT NULL DEFAULT 0,
        skill INTEGER NOT NULL DEFAULT 0,
        luck INTEGER NOT NULL DEFAULT 0,
        option INTEGER NOT NULL DEFAULT 0,
        excellent INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX items_character ON items (character_id);
    """,
]


def connect(path):
    """Opens the database file, creating it and applying the migrations it misses."""
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA journal_mode = WAL')

    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > len(MIGRATIONS):
        db.close()
        raise RuntimeError('{}: schema version {} is newer than this server ({})'.format(
            path, version, len(MIGRATIONS)))
    for n in range(version, len(MIGRATIONS)):
        logger.info('%s: migrating the schema to version %s', path, n + 1)
        # executescript commits on its own, the version goes in the same transaction as the migration
        db.executescript('BEGIN;\n{}\nPRAGMA user_version = {};\nCOMMIT;'.format(MIGRATIONS[n], n + 1))
    return db
