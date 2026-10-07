from itertools import count
from mup.error import NotFoundError
from mup.model.account import Account
from mup.model.player import Player


class MemoryAccountMapper:
    """Accounts kept in process memory, lost on restart."""

    def __init__(self):
        self.accounts = {}
        self.ids = count(1)

    def load(self, name):
        if name not in self.accounts:
            raise NotFoundError

        return self.accounts[name]

    def store(self, account: Account):
        if account.id is None:
            account.id = next(self.ids)
        self.accounts[account.name] = account


class MemoryPlayerMapper:
    """Characters kept in process memory, lost on restart."""

    def __init__(self):
        self.players = {}

    def get_by_account(self, account: Account):
        return sorted(
            [p for p in self.players.values() if p.account.id == account.id],
            key=lambda p: p.index
        )

    def load(self, name):
        if name not in self.players:
            raise NotFoundError

        return self.players[name]

    def store(self, player: Player):
        self.players[player.name] = player

    def delete(self, player: Player):
        self.players.pop(player.name, None)
