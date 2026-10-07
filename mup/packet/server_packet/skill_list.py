from mup.packet.base import Base


class SkillList(Base):
    def __init__(self, skills):
        data = bytearray([0xC1, 0, 0xF3, 0x11, len(skills)])

        for index, skill in enumerate(skills):
            data += bytearray([index, skill, 0])  # list index, skill number, skill level

        super().__init__(data)
        self.length = len(self)
