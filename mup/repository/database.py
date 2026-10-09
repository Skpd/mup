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
    # roadmap M4: exp is the total the client keeps (it was the exp within the level), hotkeys of F3 30
    """
    UPDATE characters SET exp = exp + 10 * (level + 8) * (level - 1) * (level - 1)
        + CASE WHEN level > 256 THEN 1000 * (level - 247) * (level - 256) * (level - 256) ELSE 0 END;
    ALTER TABLE characters ADD COLUMN key_settings BLOB;
    """,
    # roadmap M5: items in the chaos machine are kept with their character (owner 'chaos', slot 0..31), the CHECK
    # can't be altered in SQLite, the table is rebuilt
    """
    CREATE TABLE items_new (
        id INTEGER PRIMARY KEY,
        serial INTEGER NOT NULL UNIQUE,
        owner TEXT NOT NULL CHECK (owner IN ('inventory', 'warehouse', 'chaos')),
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
    INSERT INTO items_new SELECT * FROM items;
    DROP TABLE items;
    ALTER TABLE items_new RENAME TO items;
    CREATE INDEX items_character ON items (character_id);
    CREATE INDEX items_account ON items (account_id);
    """,
    # roadmap M6: items put in a trade are kept with their character (owner 'trade', slot 0..31) until it ends, the
    # table is rebuilt for the CHECK. Every trade is logged with what each side gave (trades, trade_items)
    """
    CREATE TABLE items_new (
        id INTEGER PRIMARY KEY,
        serial INTEGER NOT NULL UNIQUE,
        owner TEXT NOT NULL CHECK (owner IN ('inventory', 'warehouse', 'chaos', 'trade')),
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
    INSERT INTO items_new SELECT * FROM items;
    DROP TABLE items;
    ALTER TABLE items_new RENAME TO items;
    CREATE INDEX items_character ON items (character_id);
    CREATE INDEX items_account ON items (account_id);
    CREATE TABLE trades (
        id INTEGER PRIMARY KEY,
        time INTEGER NOT NULL,
        a_character_id INTEGER REFERENCES characters (id) ON DELETE SET NULL,
        b_character_id INTEGER REFERENCES characters (id) ON DELETE SET NULL,
        a_name TEXT NOT NULL,
        b_name TEXT NOT NULL,
        a_zen INTEGER NOT NULL,
        b_zen INTEGER NOT NULL
    );
    CREATE TABLE trade_items (
        id INTEGER PRIMARY KEY,
        trade_id INTEGER NOT NULL REFERENCES trades (id) ON DELETE CASCADE,
        side TEXT NOT NULL CHECK (side IN ('a', 'b')),
        serial INTEGER NOT NULL,
        type INTEGER NOT NULL,
        level INTEGER NOT NULL,
        durability INTEGER NOT NULL,
        skill INTEGER NOT NULL,
        luck INTEGER NOT NULL,
        option INTEGER NOT NULL,
        excellent INTEGER NOT NULL
    );
    CREATE INDEX trade_items_trade ON trade_items (trade_id);
    CREATE INDEX trade_items_type ON trade_items (type);
    """,
    # roadmap M7: seconds in game since the pk count last changed, it goes back to 0 with them (mup.server.pk)
    """
    ALTER TABLE characters ADD COLUMN pk_time REAL NOT NULL DEFAULT 0;
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
