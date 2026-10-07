import itertools
from abc import abstractmethod
from pprint import pprint
from random import randint
from time import time
from typing import Dict, List


class PositionableMixin:
    __slots__ = ('x', 'y')

    def __init__(self, x, y):
        self.x = x
        self.y = y


class Player(PositionableMixin):
    __slots__ = ('name',)

    def __init__(self, name, x, y):
        super().__init__(x, y)
        self.name = name


class IMapView:
    @abstractmethod
    def find_at(self, x, y):
        ...

    @abstractmethod
    def find_near(self, x, y, distance):
        ...

    @abstractmethod
    def add(self, ent: PositionableMixin):
        ...

    @abstractmethod
    def remove(self, ent: PositionableMixin):
        ...


class NaiveMapView(IMapView):
    map: List[List[List[PositionableMixin]]]
    max_x = 255
    max_y = 255

    def __init__(self):
        self.map = []
        for x in range(self.max_x + 1):
            self.map.append([])
            for y in range(self.max_y + 1):
                self.map[x].append([])

    def find_at(self, x, y):
        return self.map[x][y]

    def find_near(self, x, y, distance):
        xl = max(0, min(x-distance, self.max_x))
        yl = max(0, min(y-distance, self.max_y))
        xh = max(0, min(x+distance, self.max_x)) + 1
        yh = max(0, min(y+distance, self.max_y)) + 1

        # ugly af - unpack
        # [[[p1x1y1, p2x1y1], [p1x1y2, p2x1y2]], [[p1x2y1, p2x2y1], [p1x2y2, p2x2y2]]]
        # to
        # [p1x1y1, p2x1y1, p1x1y2, p2x1y2, p1x2y1, p2x2y1, p1x2y2, p2x2y2]
        return list(
            itertools.chain.from_iterable(
                itertools.chain.from_iterable(
                    [x[yl:yh] for x in self.map[xl:xh]]
                )
            )
        )

    def add(self, ent: PositionableMixin):
        self.map[ent.x][ent.y].append(ent)

    def remove(self, ent: PositionableMixin):
        self.map[ent.x][ent.y].remove(ent)


if __name__ == '__main__':
    players = [Player(f'Player{i}', randint(0, 255), randint(0, 255)) for i in range(100000)]
    map_one = NaiveMapView()

    print(len(players), 'players')

    for p in players:
        map_one.add(p)

    print([f'{x.name} at {x.x}:{x.y}' for x in map_one.find_at(10, 10)])
    print([f'{x.name} at {x.x}:{x.y}' for x in map_one.find_at(150, 150)])

    print([f'{x.name} near 5 from 15:15 -  {x.x}:{x.y}' for x in map_one.find_near(15, 15, 5)])

    t = -time()
    r = map_one.find_near(150, 150, 50)
    t += time()
    pprint([f'{x.name} near 50 from 150:150 -  {x.x}:{x.y}' for x in r])
    print(t, len(r))
