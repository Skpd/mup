import logging
from mup.error import NotFoundError
from mup.model.item import Item
from mup.model.player import Player, CharacterClass
from mup.model.warehouse import Warehouse

logger = logging.getLogger(__name__)

# characters column -> Player attribute, for the columns stored as they are
COLUMNS = {
    'account_id': 'account_id', 'slot': 'index', 'name': 'name', 'level': 'level', 'exp': 'exp',
    'level_up_points': 'free_points', 'str': 'strength', 'agi': 'agility', 'vit': 'vitality', 'ene': 'energy',
    'life': 'life', 'mana': 'mana', 'zen': 'zen', 'map': 'map_id', 'x': 'x', 'y': 'y', 'dir': 'direction',
    'pk_level': 'pk', 'pk_count': 'pk_count', 'ctl_code': 'role_code', 'quest_state': 'quest_state',
    'key_settings': 'key_settings',
}
SAVED = [c for c in COLUMNS if c not in ('account_id', 'slot', 'name')]  # what changes in game
ITEM_COLUMNS = ('level', 'durability', 'skill', 'luck', 'option', 'excellent')  # stored as the Item attributes


class CharacterRepository:
    def __init__(self, db, item_info):
        """item_info: item type -> ItemInfo"""
        self.db = db
        self.item_info = item_info

    def _player(self, row):
        p = Player(id=row['id'], class_type=CharacterClass(row['class']),
                   **{attr: row[column] for column, attr in COLUMNS.items()})
        p.quest_state = bytes(p.quest_state)
        p.inventory = self._items(p.name, "character_id = ? AND owner = 'inventory'", p.id)
        p.chaos_box = self._items(p.name, "character_id = ? AND owner = 'chaos'", p.id)
        return p

    def _items(self, whose, where, key):
        """Slot -> Item of the rows matching where (key is its parameter), whose names them in the log."""
        items = {}
        for row in self.db.execute('SELECT * FROM items WHERE ' + where, (key,)):
            info = self.item_info.get(row['type'])
            if info is None:
                logger.warning('%s: item %s of unknown type %s left out', whose, row['serial'], row['type'])
                continue
            items[row['slot']] = Item(info, serial=row['serial'], **{c: row[c] for c in ITEM_COLUMNS})
        return items

    def load_warehouse(self, account_id):
        """The account's vault, empty when it has none yet."""
        row = self.db.execute('SELECT zen FROM warehouses WHERE account_id = ?', (account_id,)).fetchone()
        items = self._items('warehouse of account {}'.format(account_id), "account_id = ? AND owner = 'warehouse'",
                            account_id)
        return Warehouse(account_id, zen=row['zen'] if row else 0, items=items)

    def by_account(self, account_id):
        """Characters of an account in slot order, with their items, without skills."""
        rows = self.db.execute('SELECT * FROM characters WHERE account_id = ? ORDER BY slot', (account_id,))
        return [self._player(row) for row in rows]

    def load(self, name):
        """Character by name, case insensitive, with its skills and items. Raises NotFoundError."""
        row = self.db.execute('SELECT * FROM characters WHERE name = ?', (name,)).fetchone()
        if row is None:
            raise NotFoundError(name)
        p = self._player(row)
        p.skills = []
        for r in self.db.execute('SELECT slot, number FROM skills WHERE character_id = ? ORDER BY slot', (p.id,)):
            p.skills += [None] * (r['slot'] - len(p.skills)) + [r['number']]  # a free slot stays free
        return p

    def last_item_serial(self):
        """The highest item serial stored, 0 without items."""
        return self.db.execute('SELECT MAX(serial) FROM items').fetchone()[0] or 0

    def exists(self, name):
        return self.db.execute('SELECT 1 FROM characters WHERE name = ?', (name,)).fetchone() is not None

    def create(self, p: Player):
        columns = list(COLUMNS) + ['class']
        values = [getattr(p, attr) for attr in COLUMNS.values()] + [p.class_type.value]
        with self.db:
            cur = self.db.execute('INSERT INTO characters ({}) VALUES ({})'.format(
                ', '.join(columns), ', '.join('?' * len(columns))), values)
            p.id = cur.lastrowid
            self._save_skills(p)
            self._save_items(p)

    def save(self, p: Player, warehouse: Warehouse = None):
        """Writes what changes in game: stats, position, skills, items, and the account's vault when it was opened.
        One transaction, so an item that moved between them is stored once."""
        with self.db:
            self.db.execute('UPDATE characters SET {}, class = ? WHERE id = ?'.format(
                ', '.join(c + ' = ?' for c in SAVED)),
                [getattr(p, COLUMNS[c]) for c in SAVED] + [p.class_type.value, p.id])
            self._save_skills(p)
            self._save_items(p, warehouse)

    def save_key_settings(self, p: Player):
        with self.db:
            self.db.execute('UPDATE characters SET key_settings = ? WHERE id = ?', (p.key_settings, p.id))

    def _save_skills(self, p):
        self.db.execute('DELETE FROM skills WHERE character_id = ?', (p.id,))
        self.db.executemany('INSERT INTO skills (character_id, slot, number) VALUES (?, ?, ?)',
                            [(p.id, slot, number) for slot, number in enumerate(p.skills) if number is not None])

    def _save_items(self, p, warehouse=None):
        # an item that changed hands may still be stored with its last owner: REPLACE takes it over by its serial
        self.db.execute("DELETE FROM items WHERE character_id = ? AND owner IN ('inventory', 'chaos')", (p.id,))
        rows = [('inventory', p.id, None, slot, item) for slot, item in p.inventory.items()]
        rows += [('chaos', p.id, None, slot, item) for slot, item in p.chaos_box.items()]
        if warehouse is not None:
            self.db.execute("DELETE FROM items WHERE account_id = ? AND owner = 'warehouse'", (warehouse.account_id,))
            rows += [('warehouse', None, warehouse.account_id, slot, item) for slot, item in warehouse.items.items()]
            self.db.execute('INSERT OR REPLACE INTO warehouses (account_id, zen) VALUES (?, ?)',
                            (warehouse.account_id, warehouse.zen))
        columns = ('serial', 'owner', 'character_id', 'account_id', 'slot', 'type') + ITEM_COLUMNS
        self.db.executemany('INSERT OR REPLACE INTO items ({}) VALUES ({})'.format(
            ', '.join(columns), ', '.join('?' * len(columns))),
            [(item.serial, owner, character, account, slot, item.type)
             + tuple(int(getattr(item, c)) for c in ITEM_COLUMNS)
             for owner, character, account, slot, item in rows])

    def delete(self, p: Player):
        """The character with its skills and items."""
        with self.db:
            self.db.execute('DELETE FROM characters WHERE id = ?', (p.id,))
