import json
from mup.error import NotFoundError
from mup.model.bot import Bot, Personality

SELECT = ('SELECT b.*, c.name, c.account_id FROM bots b JOIN characters c ON c.id = b.character_id')


class BotRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _bot(row):
        return Bot(character_id=row['character_id'], name=row['name'], account_id=row['account_id'], seed=row['seed'],
                   personality=Personality.of(json.loads(row['personality'])), career=json.loads(row['career']),
                   schedule=row['schedule'])

    def create(self, character_id, seed, personality: Personality):
        with self.db:
            self.db.execute('INSERT INTO bots (character_id, seed, personality) VALUES (?, ?, ?)',
                            (character_id, seed, json.dumps(personality.as_dict())))
        return self._bot(self.db.execute(SELECT + ' WHERE b.character_id = ?', (character_id,)).fetchone())

    def all(self):
        """Every bot, in the order they were made."""
        return [self._bot(row) for row in self.db.execute(SELECT + ' ORDER BY b.character_id')]

    def load(self, name):
        """Bot by its character's name, case insensitive. Raises NotFoundError."""
        row = self.db.execute(SELECT + ' WHERE c.name = ?', (name,)).fetchone()
        if row is None:
            raise NotFoundError(name)
        return self._bot(row)

    def save(self, bot: Bot):
        """The career state, what changes while it plays."""
        with self.db:
            self.db.execute('UPDATE bots SET career = ? WHERE character_id = ?',
                            (json.dumps(bot.career, sort_keys=True), bot.character_id))
