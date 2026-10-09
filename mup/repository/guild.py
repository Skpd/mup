from typing import List, Tuple

MASTER = 0x80  # guild_members.status of the master, the usual value


class GuildRepository:
    """Guilds and their members (guilds, guild_members). The game keeps them in memory and writes each change."""

    def __init__(self, db):
        self.db = db

    def load(self) -> List[Tuple[dict, List[Tuple[int, str]]]]:
        """Every guild (id, name, master_id, mark, score) with its members (character id, name), the master first,
        then by joining."""
        found = []
        for g in self.db.execute('SELECT id, name, master_id, mark, score FROM guilds ORDER BY id'):
            members = self.db.execute(
                'SELECT m.character_id, c.name FROM guild_members m JOIN characters c ON c.id = m.character_id '
                'WHERE m.guild_id = ? ORDER BY m.status = ? DESC, m.rowid', (g['id'], MASTER)).fetchall()
            found.append((dict(g), [(r['character_id'], r['name']) for r in members]))
        return found

    def name_taken(self, name):
        return self.db.execute('SELECT 1 FROM guilds WHERE name = ?', (name,)).fetchone() is not None

    def create(self, name, master_id, mark):
        """A new guild with its master as the first member. Returns its id."""
        with self.db:
            cur = self.db.execute('INSERT INTO guilds (name, master_id, mark) VALUES (?, ?, ?)',
                                  (name, master_id, bytes(mark)))
            self.db.execute('INSERT INTO guild_members (guild_id, character_id, status) VALUES (?, ?, ?)',
                            (cur.lastrowid, master_id, MASTER))
        return cur.lastrowid

    def add_member(self, guild_id, character_id):
        with self.db:
            self.db.execute('INSERT INTO guild_members (guild_id, character_id) VALUES (?, ?)',
                            (guild_id, character_id))

    def remove_member(self, character_id):
        with self.db:
            self.db.execute('DELETE FROM guild_members WHERE character_id = ?', (character_id,))

    def delete(self, guild_id):
        """The guild and its members."""
        with self.db:
            self.db.execute('DELETE FROM guilds WHERE id = ?', (guild_id,))
