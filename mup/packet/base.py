class Base(bytearray):
    def is_double(self):
        return self[0] in {0xC2, 0xC4}

    @property
    def head(self):
        return self[3] if self.is_double() else self[2]

    @head.setter
    def head(self, value):
        p = 3 if self.is_double() else 2
        self[p] = value

    @property
    def sub(self):
        return self[4] if self.is_double() else self[3]

    @sub.setter
    def sub(self, value):
        p = 4 if self.is_double() else 3
        self[p] = value

    @property
    def length(self):
        if self.is_double():
            return self[1] << 8 | self[2]
        else:
            return self[1]

    @length.setter
    def length(self, length):
        if self.is_double():
            self[1] = length >> 8 & 0xFF
            self[2] = length & 0xFF
        else:
            self[1] = length & 0xFF

    @property
    def key(self):
        if self.is_double():
            return self[3], self[4]
        else:
            return self[2], self[3]
