from mup.error import NotFoundError
from mup.mapper.base import BaseMapper
from mup.model.account import Account


class AccountMapper(BaseMapper):
    def __init__(self):
        super().__init__()
        self.c = self.db.get_collection('accounts')

    def load(self, name):
        r = self.c.find_one({'name': name})

        if r is None:
            raise NotFoundError

        p = Account()
        for k, v in r:
            if k == '_id':
                k = 'id'
            setattr(p, k, v)

        return p

    def store(self, account: Account):
        fields = vars(account)
        if 'id' in fields:
            v = fields.pop('id')
            fields['_id'] = v
        self.c.update({'name': account.name}, fields, upsert=True)
