from dataclasses import dataclass
from typing import Iterable

from . import (
    Action,
    GameProto,
    PlayerProto,
    Variations,
)
from .deck import (
    BirthdayCard,
    Card,
    DealBreakerCard,
    DebtCollectorCard,
    DoubleTheRentCard,
    ForcedDealCard,
    HotelCard,
    HouseCard,
    JustSayNoCard,
    MoneyCard,
    PassGoCard,
    PropertyCard,
    PropertyColour,
    RainbowRentCard,
    RentCard,
    SlyDealCard,
    WildPropertyCard,
)
from .propertyset import PropertySet


@dataclass
class SkipAction(Action):
    def apply(self, g: GameProto) -> None:
        pass

    def action_count(self) -> int:
        return 1


@dataclass
class DiscardAction(Action):
    card: Card

    def action_count(self) -> int:
        return 1

    def apply(self, g: GameProto) -> None:
        # move card from hand to discard pile
        self.player.get_hand().remove(self.card)
        g.discard(self.card)


@dataclass
class PlayPropertyAction(Action):
    card: PropertyCard | WildPropertyCard | HouseCard | HotelCard
    colour: PropertyColour

    def apply(self, g: GameProto) -> None:
        # move from hand to property sets
        self.player.get_hand().remove(self.card)
        self.player.add_property(self.colour, self.card)

    def action_count(self) -> int:
        return 1


@dataclass
class RentAction(DiscardAction):
    propertyset: PropertySet
    double_rent: DoubleTheRentCard | None
    quad_rent: DoubleTheRentCard | None
    target: PlayerProto | None

    def action_count(self) -> int:
        return (
            1
            + (0 if self.double_rent is None else 1)
            + (0 if self.quad_rent is None else 1)
        )

    def apply(self, g: GameProto) -> None:
        rent = self.propertyset.rent_value()
        rent *= 1 if self.double_rent is None else 2
        rent *= 1 if self.quad_rent is None else 2
        rent_target = (
            [self.target] if self.target is not None else g.get_opposition(self.player)
        )

        for p in rent_target:
            if g.check_stop_action(p, self):
                continue
            g.player_owes_money(p, self.player, rent)

        # discard multiple cards
        for card in [self.card, self.double_rent, self.quad_rent]:
            if card is None:
                continue
            self.player.get_hand().remove(card)
            g.discard(card)


class DepositAction(DiscardAction):
    def apply(self, g: GameProto) -> None:
        # move hand -> cash
        self.player.get_hand().remove(self.card)
        self.player.add_money(self.card)


class BirthdayAction(DiscardAction):
    # all other players must send us 2M
    def apply(self, g: GameProto) -> None:
        super().apply(g)
        for p in g.get_opposition(self.player):
            if g.check_stop_action(p, self):
                continue
            g.player_owes_money(p, self.player, 2)


@dataclass
class DebtCollectorAction(DiscardAction):
    # nominated player must send us 5M
    target: PlayerProto

    def apply(self, g: GameProto) -> None:
        super().apply(g)
        if g.check_stop_action(self.target, self):
            return
        g.player_owes_money(self.target, self.player, 5)


@dataclass
class PassGoAction(DiscardAction):
    def apply(self, g: GameProto) -> None:
        super().apply(g)
        g.deal_to(self.player)
        g.deal_to(self.player)


@dataclass
class DealBreakerAction(DiscardAction):
    target: PlayerProto
    propertyset: PropertySet

    def apply(self, g: GameProto) -> None:
        super().apply(g)
        if g.check_stop_action(self.target, self):
            return
        # move cards one by one?
        self.target.remove_property_set(self.propertyset)
        self.player.add_property_set(self.propertyset)


def _receive_stolen_property_card(player: PlayerProto, card: Card) -> None:
    if isinstance(card, PropertyCard):
        player.add_property(card.colour, card)
    elif isinstance(card, WildPropertyCard):
        colour = player.pick_colour_for_recieved_wildcard(card)
        player.add_property(colour, card)
    elif isinstance(card, HouseCard) or isinstance(card, HotelCard):
        optional_colour = player.pick_colour_for_recieved_building(card)
        if optional_colour is not None:
            player.add_property(optional_colour, card)
        else:
            # Buildings can always be banked for cash value.
            player.add_money(card)
    else:
        raise ValueError(f"unsupported property transfer card: {card}")


@dataclass
class SlyDealAction(DiscardAction):
    target: PlayerProto
    target_card: PropertyCard | WildPropertyCard

    def apply(self, g: GameProto) -> None:
        super().apply(g)
        if g.check_stop_action(self.target, self):
            return
        self.target.remove(self.target_card)
        _receive_stolen_property_card(self.player, self.target_card)


@dataclass
class ForcedDealAction(DiscardAction):
    target: PlayerProto
    your_card: PropertyCard | WildPropertyCard
    target_card: PropertyCard | WildPropertyCard

    def apply(self, g: GameProto) -> None:
        super().apply(g)
        if g.check_stop_action(self.target, self):
            return

        self.player.remove(self.your_card)
        self.target.remove(self.target_card)

        _receive_stolen_property_card(self.player, self.target_card)
        _receive_stolen_property_card(self.target, self.your_card)


def _iter_stealable_cards(
    player: PlayerProto,
) -> Iterable[PropertyCard | WildPropertyCard]:
    for ps in player.get_property_sets().values():
        if ps.is_complete():
            continue
        for property_card in ps.properties:
            yield property_card
        for wild_card in ps.wilds:
            yield wild_card


def _rent_multipliers(
    game: GameProto, player: PlayerProto, actions_left: int
) -> list[tuple[DoubleTheRentCard | None, DoubleTheRentCard | None]]:
    dtr_cards = [
        card for card in player.get_hand() if isinstance(card, DoubleTheRentCard)
    ]
    combos: list[tuple[DoubleTheRentCard | None, DoubleTheRentCard | None]] = [
        (None, None)
    ]
    if actions_left >= 2 and len(dtr_cards) >= 1:
        combos.append((dtr_cards[0], None))
    if (
        actions_left >= 3
        and len(dtr_cards) >= 2
        and Variations.ALLOW_QUAD_RENT in game.variations
    ):
        combos.append((dtr_cards[0], dtr_cards[1]))
    return combos


def generate_actions(
    game: GameProto, player: PlayerProto, actions_left: int
) -> list[Action]:
    actions: list[Action] = []

    def append_action(a: Action) -> None:
        if a.action_count() <= actions_left:
            actions.append(a)

    opposition = game.get_opposition(player)
    your_stealable_cards = list(_iter_stealable_cards(player))
    rent_multipliers = _rent_multipliers(game, player, actions_left)

    for c in player.get_hand():
        if isinstance(c, PropertyCard):
            append_action(PlayPropertyAction(player=player, colour=c.colour, card=c))
        else:
            # Every non-property card can be banked for its cash value.
            append_action(DepositAction(player=player, card=c))

            if isinstance(c, BirthdayCard):
                append_action(BirthdayAction(player=player, card=c))
            elif isinstance(c, DebtCollectorCard):
                for op in opposition:
                    append_action(
                        DebtCollectorAction(
                            player=player,
                            card=c,
                            target=op,
                        )
                    )
            elif isinstance(c, WildPropertyCard):
                # one action for each possible colour
                for col in c.colours:
                    append_action(PlayPropertyAction(player=player, colour=col, card=c))
            elif isinstance(c, SlyDealCard):
                for target in opposition:
                    for target_card in _iter_stealable_cards(target):
                        append_action(
                            SlyDealAction(
                                player=player,
                                card=c,
                                target=target,
                                target_card=target_card,
                            )
                        )
            elif isinstance(c, JustSayNoCard):
                pass
            elif isinstance(c, MoneyCard):
                pass
            elif isinstance(c, RentCard):
                for col in c.colours:
                    ps = player.get_property_sets().get(col)
                    if ps is None or ps.rent_value() == 0:
                        continue
                    for double_rent, quad_rent in rent_multipliers:
                        append_action(
                            RentAction(
                                player=player,
                                propertyset=ps,
                                card=c,
                                double_rent=double_rent,
                                quad_rent=quad_rent,
                                target=None,
                            )
                        )

            elif isinstance(c, RainbowRentCard):
                for col in c.colours:
                    ps = player.get_property_sets().get(col)
                    if ps is None or ps.rent_value() == 0:
                        continue
                    for t in opposition:
                        for double_rent, quad_rent in rent_multipliers:
                            append_action(
                                RentAction(
                                    player=player,
                                    propertyset=ps,
                                    card=c,
                                    double_rent=double_rent,
                                    quad_rent=quad_rent,
                                    target=t,
                                )
                            )

            elif isinstance(c, ForcedDealCard):
                for target in opposition:
                    for target_card in _iter_stealable_cards(target):
                        for your_card in your_stealable_cards:
                            append_action(
                                ForcedDealAction(
                                    player=player,
                                    card=c,
                                    target=target,
                                    your_card=your_card,
                                    target_card=target_card,
                                )
                            )
            elif isinstance(c, DoubleTheRentCard):
                # this is dealt with by the RentCard handler
                pass
            elif isinstance(c, PassGoCard):
                append_action(PassGoAction(player=player, card=c))
            elif isinstance(c, DealBreakerCard):
                for t in opposition:
                    for ps in t.get_property_sets().values():
                        if ps.is_complete():
                            append_action(
                                DealBreakerAction(
                                    player=player, card=c, target=t, propertyset=ps
                                )
                            )

            elif isinstance(c, HouseCard):
                for ps in player.get_property_sets().values():
                    if ps.can_build_house():
                        append_action(
                            PlayPropertyAction(
                                player=player, card=c, colour=ps.get_colour()
                            )
                        )
            elif isinstance(c, HotelCard):
                for ps in player.get_property_sets().values():
                    if ps.can_build_hotel():
                        append_action(
                            PlayPropertyAction(
                                player=player, card=c, colour=ps.get_colour()
                            )
                        )

            else:
                raise ValueError(c)
                # actions.append(DepositAction(player=player, card=c))

    return actions
