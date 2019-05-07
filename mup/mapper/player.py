from mup.error import NotFoundError
from mup.mapper.base import BaseMapper
from mup.model.account import Account
from mup.model.player import Player


class PlayerMapper(BaseMapper):
    def __init__(self):
        super().__init__()
        self.c = self.db.get_collection('players')

    def get_by_account(self, account: Account):
        r = self.c.find({'account_id': account.id})
        res = [self.map(rr) for rr in r]
        return res

    def load(self, name):
        r = self.c.find_one({'name': name})

        if r is None:
            raise NotFoundError

        p = self.map(r)

        return p

    def map(self, r):
        p = Player()
        for k, v in r:
            if k == '_id':
                k = 'id'
            setattr(p, k, v)
        return p

    def store(self, player: Player):
        fields = vars(player)
        if 'id' in fields:
            v = fields.pop('id')
            fields['_id'] = v
        self.c.update({'name': player.name}, fields, upsert=True)
