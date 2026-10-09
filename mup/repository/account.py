from mup.common.password import hash_password, NO_PASSWORD
from mup.error import NotFoundError
from mup.model.account import Account


class AccountRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _account(row):
        return Account(id=row['id'], name=row['name'], password_hash=row['password_hash'],
                       personal_code=row['personal_code'], ctl_code=row['ctl_code'], active=bool(row['active']))

    def load(self, name):
        """Account by name, case insensitive. Raises NotFoundError."""
        row = self.db.execute('SELECT * FROM accounts WHERE name = ?', (name,)).fetchone()
        if row is None:
            raise NotFoundError(name)
        return self._account(row)

    def all(self):
        return [self._account(row) for row in self.db.execute('SELECT * FROM accounts ORDER BY id')]

    def create(self, name, password, personal_code=''):
        """password None: nobody logs in to it (simulations, bots), and no hashing time spent."""
        stored = NO_PASSWORD if password is None else hash_password(password)
        with self.db:
            cur = self.db.execute('INSERT INTO accounts (name, password_hash, personal_code) VALUES (?, ?, ?)',
                                  (name, stored, personal_code))
        return self.load_id(cur.lastrowid)

    def load_id(self, account_id):
        row = self.db.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
        if row is None:
            raise NotFoundError(account_id)
        return self._account(row)

    def delete(self, account: Account):
        """The account with its vault, its characters must be deleted first."""
        with self.db:
            self.db.execute("DELETE FROM items WHERE account_id = ? AND owner = 'warehouse'", (account.id,))
            self.db.execute('DELETE FROM warehouses WHERE account_id = ?', (account.id,))
            self.db.execute('DELETE FROM accounts WHERE id = ?', (account.id,))

    def save(self, account: Account):
        with self.db:
            self.db.execute(
                'UPDATE accounts SET password_hash = ?, personal_code = ?, ctl_code = ?, active = ? WHERE id = ?',
                (account.password_hash, account.personal_code, account.ctl_code, int(account.active), account.id))
