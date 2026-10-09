"""The game server's packet handlers by head and sub (None: any sub), one per packet in mup/server/handler."""
from mup.server.handler.action import action_handler
from mup.server.handler.add_point import add_point_handler
from mup.server.handler.attack import attack_handler
from mup.server.handler.char_list import char_list_handler
from mup.server.handler.chat import chat_handler, whisper_handler
from mup.server.handler.close import close_handler
from mup.server.handler.create_character import create_character_handler
from mup.server.handler.delete_character import delete_character_handler
from mup.server.handler.devil_square import devil_square_enter_handler
from mup.server.handler.game_start import game_start_handler
from mup.server.handler.guild import (guild_request_handler, guild_answer_handler, guild_list_handler,
                                      guild_leave_handler, guild_master_answer_handler, guild_create_handler,
                                      guild_cancel_handler)
from mup.server.handler.key_settings import key_settings_handler
from mup.server.handler.item import pick_up_handler, drop_item_handler, move_item_handler, use_item_handler
from mup.server.handler.login import login_handler
from mup.server.handler.logout import logout_handler
from mup.server.handler.magic import magic_attack_handler, aoe_magic_handler, area_hits_handler
from mup.server.handler.map_ready import map_ready_handler
from mup.server.handler.move import move_handler
from mup.server.handler.move_gate import move_gate_handler
from mup.server.handler.npc import (talk_handler, close_window_handler, buy_handler, sell_handler, repair_handler,
                                    warehouse_money_handler, warehouse_close_handler, mix_handler, chaos_close_handler)
from mup.server.handler.party import party_request_handler, party_answer_handler, party_leave_handler
from mup.server.handler.ping import ping_handler
from mup.server.handler.quest import quest_states_handler, quest_proceed_handler
from mup.server.handler.trade import (trade_request_handler, trade_answer_handler, trade_zen_handler,
                                      trade_ok_handler, trade_cancel_handler)


def register(gs):
    gs.add_handler(0x18, None, action_handler)
    gs.add_handler(0x15, None, attack_handler)
    gs.add_handler(0x19, None, magic_attack_handler)
    gs.add_handler(0x1E, None, aoe_magic_handler)
    gs.add_handler(0x1D, None, area_hits_handler)
    gs.add_handler(0x10, None, move_handler)
    gs.add_handler(0x1C, None, move_gate_handler)
    gs.add_handler(0x22, None, pick_up_handler)
    gs.add_handler(0x23, None, drop_item_handler)
    gs.add_handler(0x24, None, move_item_handler)
    gs.add_handler(0x26, None, use_item_handler)
    gs.add_handler(0x30, None, talk_handler)
    gs.add_handler(0x31, None, close_window_handler)
    gs.add_handler(0x32, None, buy_handler)
    gs.add_handler(0x33, None, sell_handler)
    gs.add_handler(0x34, None, repair_handler)
    gs.add_handler(0x81, None, warehouse_money_handler)
    gs.add_handler(0x82, None, warehouse_close_handler)
    gs.add_handler(0x86, None, mix_handler)
    gs.add_handler(0x87, None, chaos_close_handler)
    gs.add_handler(0x00, None, chat_handler)
    gs.add_handler(0x02, None, whisper_handler)
    gs.add_handler(0x36, None, trade_request_handler)
    gs.add_handler(0x37, None, trade_answer_handler)
    gs.add_handler(0x3A, None, trade_zen_handler)
    gs.add_handler(0x3C, None, trade_ok_handler)
    gs.add_handler(0x3D, None, trade_cancel_handler)
    gs.add_handler(0x40, None, party_request_handler)
    gs.add_handler(0x41, None, party_answer_handler)
    gs.add_handler(0x43, None, party_leave_handler)
    gs.add_handler(0x50, None, guild_request_handler)
    gs.add_handler(0x51, None, guild_answer_handler)
    gs.add_handler(0x52, None, guild_list_handler)
    gs.add_handler(0x53, None, guild_leave_handler)
    gs.add_handler(0x54, None, guild_master_answer_handler)
    gs.add_handler(0x55, None, guild_create_handler)
    gs.add_handler(0x57, None, guild_cancel_handler)
    gs.add_handler(0x90, None, devil_square_enter_handler)
    gs.add_handler(0xA0, None, quest_states_handler)
    gs.add_handler(0xA2, None, quest_proceed_handler)
    gs.add_handler(0x0E, 0x00, ping_handler)
    gs.add_handler(0xF3, 0x00, char_list_handler)
    gs.add_handler(0xF3, 0x01, create_character_handler)
    gs.add_handler(0xF3, 0x02, delete_character_handler)
    gs.add_handler(0xF3, 0x03, game_start_handler)
    gs.add_handler(0xF3, 0x12, map_ready_handler)
    gs.add_handler(0xF3, 0x30, key_settings_handler)
    gs.add_handler(0xF3, 0x06, add_point_handler)
    gs.add_handler(0xF1, 0x01, login_handler)
    gs.add_handler(0xF1, 0x02, logout_handler)
    gs.add_handler(0xF1, 0x03, close_handler)
