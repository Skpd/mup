from datetime import datetime


class Monster:
    type_id: int
    max_life: int
    move_strategy = None
    respawn_interval: int
    spawn_area: tuple

    cid: int
    state: int
    map_id: int
    x: int
    y: int
    life: int
    is_dead: bool
    died_at: int

    @property
    def dead(self):
        return self.is_dead

    @dead.setter
    def dead(self, value):
        if value:
            self.is_dead = True
            self.died_at = int(datetime.utcnow().timestamp())
        else:
            self.is_dead = False

    def __init__(self, cid, type_id):
        self.state = 0
        self.x = 0
        self.y = 0
        self.cid = cid
        self.type_id = type_id
        self.is_dead = False
        self.respawn_interval = 5

        self.life = 100
        self.max_life = 120
