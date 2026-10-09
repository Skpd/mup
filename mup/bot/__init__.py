"""
Bots: characters the server plays through the same rules as clients (docs/bots.md). A bot is a connection in process
(session.py) whose packets go through the game's handlers, its brain (brain.py, activity.py) picks what to do from
what a client would know, the motor (motor.py) does it at the client's pace, the career (career.py) picks where to
hunt and how to spend its points. The manager (manager.py) logs them in and drives them from the game tick.
"""
from mup.model.player import CharacterClass

# class names of bin/account.py and bin/sim.py
CLASSES = {'dw': CharacterClass.DARK_WIZARD, 'dk': CharacterClass.DARK_KNIGHT, 'elf': CharacterClass.ELF,
           'mg': CharacterClass.MAGIC_GLADIATOR}
