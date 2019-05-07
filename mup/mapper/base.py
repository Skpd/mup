from pymongo import MongoClient


class BaseMapper:
    def __init__(self):
        self.db = MongoClient(['mongodb://localhost/mu']).get_database('mu')
