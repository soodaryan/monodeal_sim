from __future__ import annotations

import random
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any

from monodeal import Action, GameProto, PlayerProto, Variations
from monodeal.actions import (
    DealBreakerAction,
    DepositAction,
    ForcedDealAction,
    PlayPropertyAction,
    RentAction,
    SkipAction,
    SlyDealAction,
    generate_actions,
)
from monodeal.deck import (
    DECK,
    Card,
    HotelCard,
    HouseCard,
    JustSayNoCard,
    PropertyCard,
    WildPropertyCard,
)
from monodeal.game import Player
from monodeal.propertyset import PropertySet


@dataclass(frozen=True)
class RoomPlayer:
    player_id: str
    name: str
    seat: int


def _card_label(card: Card) -> str:
    return card.name


def _property_set_payload(ps: PropertySet) -> dict[str, Any]:
    cards = [card.name for card in ps]
    return {
        "colour": ps.get_colour().name,
        "is_complete": ps.is_complete(),
        "rent_value": ps.rent_value(),
        "cards": cards,
    }


def _action_label(action: Action) -> str:
    if isinstance(action, PlayPropertyAction):
        return f"Play {action.card.name} as {action.colour.name}"
    if isinstance(action, DepositAction):
        return f"Bank {action.card.name}"
    if isinstance(action, RentAction):
        scope = "all opponents" if action.target is None else f"{action.target.name}"
        mult = 1
        if action.double_rent is not None:
            mult *= 2
        if action.quad_rent is not None:
            mult *= 2
        mult_label = f" x{mult}" if mult > 1 else ""
        return f"Charge rent on {action.propertyset.get_colour().name}{mult_label} to {scope}"
    if isinstance(action, DealBreakerAction):
        return f"Deal Breaker: take {action.propertyset.get_colour().name} set from {action.target.name}"
    if isinstance(action, SlyDealAction):
        return f"Sly Deal: take {action.target_card.name} from {action.target.name}"
    if isinstance(action, ForcedDealAction):
        return (
            f"Forced Deal: swap your {action.your_card.name} with "
            f"{action.target.name}'s {action.target_card.name}"
        )
    if isinstance(action, SkipAction):
        return "Skip action"
    return action.__class__.__name__


class InteractiveGame(GameProto):
    def __init__(
        self,
        player_defs: list[RoomPlayer],
        rng: random.Random | None = None,
        variations: Variations = Variations(0),
    ):
        self.players: list[Player] = [
            Player(p.name) for p in sorted(player_defs, key=lambda x: x.seat)
        ]
        self.player_map: dict[str, Player] = {
            pdef.player_id: player
            for pdef, player in zip(
                sorted(player_defs, key=lambda x: x.seat), self.players
            )
        }
        self.player_ids_by_name: dict[str, str] = {
            p.name: pid for pid, p in self.player_map.items()
        }
        self.turn_index = 0
        self.actions_left = 3
        self.draw: deque[Card] = deque()
        self.discarded: deque[Card] = deque()
        self.random = rng if rng is not None else random.Random()
        self.variations = variations
        self.winner: str | None = None
        self.started = False
        self.action_cache: list[Action] = []

    def start(self) -> None:
        self.discarded.extend(DECK)
        self.random.shuffle(self.discarded)
        self.draw.extend(self.discarded)
        self.discarded.clear()
        for _ in range(5):
            for p in self.players:
                self.deal_to(p)
        self.started = True
        self._start_turn()

    def _start_turn(self) -> None:
        player = self.current_player()
        draw_count = 5 if len(player.get_hand()) == 0 else 2
        for _ in range(draw_count):
            self.deal_to(player)
        self.actions_left = 3
        self.action_cache = []

    def current_player(self) -> Player:
        return self.players[self.turn_index]

    def current_player_id(self) -> str:
        return self.player_ids_by_name[self.current_player().name]

    def get_opposition(self, player: PlayerProto) -> list[Player]:
        return [p for p in self.players if p != player]

    def deal_to(self, p: PlayerProto) -> None:
        if len(self.draw) == 0:
            self.draw.extend(self.discarded)
            self.discarded.clear()
            self.random.shuffle(self.draw)
        if len(self.draw) == 0:
            return
        p.deal_card(self.draw.popleft())

    def discard(self, card: Card) -> None:
        self.discarded.append(card)

    def check_stop_action(self, p: PlayerProto, a: Action) -> bool:
        stop_cards = [card for card in p.get_hand() if isinstance(card, JustSayNoCard)]
        if not stop_cards:
            return False
        card = stop_cards[0]
        if p.should_stop_action(a):
            p.get_hand().remove(card)
            self.discard(card)
            return True
        return False

    def player_owes_money(
        self, from_player: PlayerProto, to_player: PlayerProto, amount: int
    ) -> None:
        cards = from_player.choose_how_to_pay(amount)
        for c in cards:
            from_player.remove(c)

        for c in cards:
            if isinstance(c, PropertyCard):
                to_player.add_property(c.colour, c)
            elif isinstance(c, WildPropertyCard):
                colour = to_player.pick_colour_for_recieved_wildcard(c)
                to_player.add_property(colour, c)
            elif isinstance(c, HouseCard) or isinstance(c, HotelCard):
                optional_colour = to_player.pick_colour_for_recieved_building(c)
                if optional_colour is not None:
                    to_player.add_property(optional_colour, c)
                else:
                    to_player.add_money(c)
            else:
                to_player.add_money(c)

    def available_actions(self, player_id: str) -> list[dict[str, Any]]:
        if self.winner is not None or not self.started:
            return []
        if player_id != self.current_player_id():
            return []
        player = self.player_map[player_id]
        actions = generate_actions(self, player, self.actions_left)
        actions.append(SkipAction(player))
        self.action_cache = actions
        return [
            {
                "index": i,
                "label": _action_label(a),
                "cost": a.action_count(),
                "type": a.__class__.__name__,
            }
            for i, a in enumerate(actions)
        ]

    def apply_action(self, player_id: str, action_index: int) -> None:
        if self.winner is not None:
            raise ValueError("Game is finished")
        if player_id != self.current_player_id():
            raise ValueError("Not your turn")
        if not self.action_cache:
            self.available_actions(player_id)
        if action_index < 0 or action_index >= len(self.action_cache):
            raise ValueError("Invalid action index")
        action = self.action_cache[action_index]
        if action.action_count() > self.actions_left:
            raise ValueError("Not enough actions left")
        self.actions_left -= action.action_count()
        action.apply(self)
        self.action_cache = []
        current = self.current_player()
        if current.has_won():
            self.winner = player_id
            return
        if self.actions_left <= 0:
            self.end_turn(player_id)

    def end_turn(self, player_id: str) -> None:
        if player_id != self.current_player_id():
            raise ValueError("Not your turn")
        current = self.current_player()
        while len(current.get_hand()) > 7:
            card = current.get_discard()
            self.discard(card)
        self.turn_index = (self.turn_index + 1) % len(self.players)
        self._start_turn()

    def state_for(self, viewer_id: str | None) -> dict[str, Any]:
        players_payload = []
        for pid, p in self.player_map.items():
            is_viewer = viewer_id == pid
            players_payload.append(
                {
                    "player_id": pid,
                    "name": p.name,
                    "hand_count": len(p.get_hand()),
                    "hand": [_card_label(c) for c in p.get_hand()] if is_viewer else [],
                    "cash": [_card_label(c) for c in p.cash],
                    "property_sets": [
                        _property_set_payload(ps)
                        for ps in p.get_property_sets().values()
                    ],
                }
            )
        winner_name = (
            self.player_map[self.winner].name
            if self.winner in self.player_map
            else None
        )
        return {
            "started": self.started,
            "winner": winner_name,
            "turn_player_id": self.current_player_id() if self.started else None,
            "turn_player_name": self.current_player().name if self.started else None,
            "actions_left": self.actions_left
            if self.started and self.winner is None
            else 0,
            "draw_count": len(self.draw),
            "discard_count": len(self.discarded),
            "players": players_payload,
        }

    def play(self) -> PlayerProto:
        raise NotImplementedError(
            "InteractiveGame is driven by API actions, not auto-play"
        )


class Room:
    def __init__(self, host_name: str):
        self.room_id = uuid.uuid4().hex[:6].upper()
        self.players: list[RoomPlayer] = []
        self.game: InteractiveGame | None = None
        self.revision = 0
        self.add_player(host_name)

    def add_player(self, name: str) -> RoomPlayer:
        if self.game is not None:
            raise ValueError("Game already started")
        if len(self.players) >= 5:
            raise ValueError("Room is full")
        rp = RoomPlayer(
            player_id=uuid.uuid4().hex, name=name.strip(), seat=len(self.players)
        )
        self.players.append(rp)
        self.revision += 1
        return rp

    def start(self) -> None:
        if self.game is not None:
            return
        if len(self.players) < 2:
            raise ValueError("Need at least 2 players to start")
        self.game = InteractiveGame(self.players)
        self.game.start()
        self.revision += 1

    def find_player(self, player_id: str) -> RoomPlayer:
        for p in self.players:
            if p.player_id == player_id:
                return p
        raise ValueError("Unknown player")

    def state_for(self, viewer_id: str | None) -> dict[str, Any]:
        game_state = (
            self.game.state_for(viewer_id)
            if self.game
            else {
                "started": False,
                "winner": None,
                "turn_player_id": None,
                "turn_player_name": None,
                "actions_left": 0,
                "draw_count": 0,
                "discard_count": 0,
                "players": [],
            }
        )
        return {
            "room_id": self.room_id,
            "players": [p.__dict__ for p in self.players],
            "game": game_state,
            "revision": self.revision,
        }
