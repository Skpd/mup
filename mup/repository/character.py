from mup.error import NotFoundError
from mup.model.player import Player, CharacterClass

# characters column -> Player attribute, for the columns stored as they are
COLUMNS = {
    'account_id': 'account_id', 'slot': 'index', 'name': 'name', 'level': 'level', 'exp': 'exp',
    'level_up_points': 'free_points', 'str': 'strength', 'agi': 'agility', 'vit': 'vitality', 'ene': 'energy',
    'life': 'life', 'mana': 'mana', 'zen': 'zen', 'map': 'map_id', 'x': 'x', 'y': 'y', 'dir': 'direction',
    'pk_level': 'pk', 'pk_count': 'pk_count', 'ctl_code': 'role_code', 'quest_state': 'quest_state',
}
SAVED = [c for c in COLUMNS if c not in ('account_id', 'slot', 'name')]  # what changes in game


class CharacterRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _player(row):
        p = Player(id=row['id'], class_type=CharacterClass(row['class']),
                   **{attr: row[column] for column, attr in COLUMNS.items()})
        p.quest_state = bytes(p.quest_state)
        return p

    def by_account(self, account_id):
        """Characters of an account in slot order, without skills."""
        rows = self.db.execute('SELECT * FROM characters WHERE account_id = ? ORDER BY slot', (account_id,))
        return [self._player(row) for row in rows]

    def load(self, name):
        """Character by name, case insensitive, with its skills. Raises NotFoundError."""
        row = self.db.execute('SELECT * FROM characters WHERE name = ?', (name,)).fetchone()
        if row is None:
            raise NotFoundError(name)
        p = self._player(row)
        p.skills = [r['number'] for r in self.db.execute(
            'SELECT number FROM skills WHERE character_id = ? ORDER BY slot', (p.id,))]
        return p

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

    def save(self, p: Player):
        """Writes what changes in game: stats, position, skills."""
        with self.db:
            self.db.execute('UPDATE characters SET {}, class = ? WHERE id = ?'.format(
                ', '.join(c + ' = ?' for c in SAVED)),
                [getattr(p, COLUMNS[c]) for c in SAVED] + [p.class_type.value, p.id])
            self._save_skills(p)

    def _save_skills(self, p):
        self.db.execute('DELETE FROM skills WHERE character_id = ?', (p.id,))
        self.db.executemany('INSERT INTO skills (character_id, slot, number) VALUES (?, ?, ?)',
                            [(p.id, slot, number) for slot, number in enumerate(p.skills)])

    def delete(self, p: Player):
        """The character with its skills and items."""
        with self.db:
            self.db.execute('DELETE FROM characters WHERE id = ?', (p.id,))
