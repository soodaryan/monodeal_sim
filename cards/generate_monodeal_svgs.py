#!/usr/bin/env python3
"""
Generate Monopoly Deal 2024 Edition SVG cards from JSON definitions.

Usage:
  python3 cards/generate_monodeal_svgs.py \
    --cards cards/list_of_cards.json \
    --types cards/type_card_description.json \
    --out cards/svg_cards
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


CARD_W = 630
CARD_H = 880
RADIUS = 28
PADDING = 28

FONT_FAMILY = "Arial, Helvetica, sans-serif"


COLOR_MAP = {
    "brown": "#8b5a2b",
    "light_blue": "#89d9ff",
    "pink": "#ff5ca9",
    "orange": "#ff9f1a",
    "red": "#e63946",
    "yellow": "#ffd60a",
    "green": "#37b24d",
    "dark_blue": "#1d4ed8",
    "railroad": "#222222",
    "utility": "#adb5bd",
    "any": "#ffffff",
}


ACTION_BG = {
    "Deal Breaker": "#d7263d",
    "Sly Deal": "#55c1ff",
    "Forced Deal": "#ffd43b",
    "Debt Collector": "#ff922b",
    "It's My Birthday": "#ff66c4",
    "Pass Go": "#51cf66",
    "Double The Rent": "#339af0",
    "Just Say No": "#845ef7",
    "House": "#8bc34a",
    "Hotel": "#a9e34b",
}


MONEY_BG = {
    1: "#b2f2bb",
    2: "#99e9f2",
    3: "#d0bfff",
    4: "#ffd8a8",
    5: "#ffa8a8",
    10: "#ff922b",
}


def escape_xml(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def wrap_text(text: str, max_chars: int) -> List[str]:
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        proposal = f"{current} {word}"
        if len(proposal) <= max_chars:
            current = proposal
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


@dataclass
class Card:
    card_id: str
    name: str
    category: str
    payload: Dict[str, Any]


class Svg:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.parts: List[str] = []

    def add(self, element: str) -> None:
        self.parts.append(element)

    def rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        fill: str,
        rx: int = 0,
        stroke: Optional[str] = None,
        stroke_width: int = 1,
        opacity: Optional[float] = None,
    ) -> None:
        attrs = [
            f'x="{x}"',
            f'y="{y}"',
            f'width="{w}"',
            f'height="{h}"',
            f'fill="{fill}"',
        ]
        if rx:
            attrs.append(f'rx="{rx}"')
        if stroke:
            attrs.append(f'stroke="{stroke}"')
            attrs.append(f'stroke-width="{stroke_width}"')
        if opacity is not None:
            attrs.append(f'opacity="{opacity}"')
        self.add(f"<rect {' '.join(attrs)} />")

    def circle(
        self,
        cx: int,
        cy: int,
        r: int,
        fill: str,
        stroke: Optional[str] = None,
        stroke_width: int = 1,
    ) -> None:
        attrs = [f'cx="{cx}"', f'cy="{cy}"', f'r="{r}"', f'fill="{fill}"']
        if stroke:
            attrs.append(f'stroke="{stroke}"')
            attrs.append(f'stroke-width="{stroke_width}"')
        self.add(f"<circle {' '.join(attrs)} />")

    def line(self, x1: int, y1: int, x2: int, y2: int, stroke: str, stroke_width: int = 2) -> None:
        self.add(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{stroke_width}" />'
        )

    def text(
        self,
        x: int,
        y: int,
        value: str,
        size: int = 28,
        weight: str = "700",
        fill: str = "#111111",
        anchor: str = "middle",
    ) -> None:
        self.add(
            f'<text x="{x}" y="{y}" font-family="{FONT_FAMILY}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape_xml(value)}</text>'
        )

    def to_string(self) -> str:
        body = "\n  ".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">\n  {body}\n</svg>\n'
        )


def draw_card_frame(svg: Svg) -> None:
    svg.rect(0, 0, CARD_W, CARD_H, "#f8f9fa", rx=RADIUS, stroke="#111111", stroke_width=4)
    svg.rect(10, 10, CARD_W - 20, CARD_H - 20, "#ffffff", rx=RADIUS - 6, stroke="#ced4da", stroke_width=2)


def draw_money_badge(svg: Svg, value: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
    # Defaults place the badge inside the top header strip, left aligned and vertically centered.
    cx = x if x is not None else 72
    cy = y if y is not None else 64
    svg.circle(cx, cy, 34, "#ffffff", stroke="#212529", stroke_width=4)
    text_size = 34 if value < 10 else 30
    svg.text(cx, cy + 11, f"{value}", size=text_size, weight="900")


def draw_dual_color_circle(svg: Svg, cx: int, cy: int, r: int, left: str, right: str) -> None:
    # Left semicircle.
    svg.add(
        f'<path d="M {cx} {cy-r} A {r} {r} 0 0 0 {cx} {cy+r} L {cx} {cy-r} Z" '
        f'fill="{left}" />'
    )
    # Right semicircle.
    svg.add(
        f'<path d="M {cx} {cy-r} A {r} {r} 0 0 1 {cx} {cy+r} L {cx} {cy-r} Z" '
        f'fill="{right}" />'
    )
    svg.circle(cx, cy, r, "none", stroke="#212529", stroke_width=3)


def draw_property_card(svg: Svg, card: Card) -> None:
    draw_card_frame(svg)
    color = card.payload["color"]
    color_hex = COLOR_MAP.get(color, "#ced4da")
    rent: List[int] = card.payload["rent"]
    set_size = card.payload["set_size"]
    bank_value = card.payload["bank_value"]

    svg.rect(18, 18, CARD_W - 36, 132, color_hex, rx=18)
    text_color = "#ffffff" if color in {"brown", "red", "dark_blue", "railroad"} else "#111111"
    svg.text(CARD_W // 2, 86, card.name.upper(), size=32, weight="900", fill=text_color)
    draw_money_badge(svg, bank_value)

    svg.text(CARD_W // 2, 220, "PROPERTY", size=30, weight="900")
    svg.rect(70, 260, CARD_W - 140, 350, "#f1f3f5", rx=12, stroke="#495057", stroke_width=2)
    svg.text(CARD_W // 2, 312, "RENT", size=30, weight="900")

    for idx, value in enumerate(rent, start=1):
        y = 340 + idx * 52
        label = "COMPLETE" if idx == set_size else f"{idx} PROPERTIES"
        svg.text(130, y, label, size=22, weight="700", anchor="start")
        svg.text(CARD_W - 130, y, f"{value}M", size=28, weight="900", anchor="end")
        svg.line(100, y + 14, CARD_W - 100, y + 14, "#dee2e6", 2)

    svg.text(CARD_W // 2, 665, f"SET SIZE: {set_size}", size=26, weight="800")
    start_x = CARD_W // 2 - (set_size * 42) // 2
    for i in range(set_size):
        svg.rect(start_x + i * 42, 690, 30, 44, color_hex, rx=6, stroke="#343a40", stroke_width=2)

    svg.text(CARD_W // 2, CARD_H - 50, "MONODEAL 2024", size=22, weight="700", fill="#495057")


def draw_wild_card(svg: Svg, card: Card) -> None:
    draw_card_frame(svg)
    colors = card.payload["colors"]
    bank_value = card.payload["bank_value"]

    if colors == ["any"]:
        strips = ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"]
        strip_h = 132 // len(strips)
        for i, c in enumerate(strips):
            svg.rect(18, 18 + i * strip_h, CARD_W - 36, strip_h + 1, c, rx=18 if i == 0 else 0)
    else:
        left = COLOR_MAP.get(colors[0], "#ced4da")
        right = COLOR_MAP.get(colors[1], "#ced4da")
        svg.rect(18, 18, (CARD_W - 36) // 2, 132, left, rx=18)
        svg.rect(18 + (CARD_W - 36) // 2, 18, (CARD_W - 36) // 2, 132, right)

    draw_money_badge(svg, bank_value)

    svg.text(CARD_W // 2, 250, "WILD PROPERTY", size=42, weight="900")
    name_lines = wrap_text(card.name, 22)
    for i, line in enumerate(name_lines):
        svg.text(CARD_W // 2, 315 + i * 40, line.upper(), size=30, weight="800")

    details_y = 430 + max(0, (len(name_lines) - 2) * 20)
    svg.rect(90, details_y, CARD_W - 180, 180, "#f1f3f5", rx=16, stroke="#495057", stroke_width=2)
    if colors == ["any"]:
        svg.text(CARD_W // 2, details_y + 85, "ANY COLOR", size=42, weight="900")
    else:
        left_name = colors[0].replace("_", " ").upper()
        right_name = colors[1].replace("_", " ").upper()
        svg.text(CARD_W // 2, details_y + 70, left_name, size=30, weight="800")
        svg.text(CARD_W // 2, details_y + 120, right_name, size=30, weight="800")
        svg.text(CARD_W // 2, details_y + 97, "<->", size=28, weight="900")

    svg.text(CARD_W // 2, 710, "CAN BE MOVED EACH TURN", size=24, weight="700")
    svg.text(CARD_W // 2, CARD_H - 50, "MONODEAL 2024", size=22, weight="700", fill="#495057")


def draw_rent_card(svg: Svg, card: Card) -> None:
    colors = card.payload["colors"]
    bank_value = card.payload["bank_value"]

    draw_card_frame(svg)
    svg.rect(18, 18, CARD_W - 36, CARD_H - 36, "#f8f9fa", rx=20)

    svg.rect(18, 18, CARD_W - 36, 92, "#ffffff", rx=14, opacity=0.92)
    svg.text(CARD_W // 2, 78, "ACTION", size=44, weight="900")
    draw_money_badge(svg, bank_value)

    if colors == ["any"]:
        strips = ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"]
        band_w = 240
        band_h = 68
        band_x = CARD_W // 2 - band_w // 2
        for i, c in enumerate(strips):
            svg.rect(band_x + i * (band_w // len(strips)), 150, (band_w // len(strips)) + 1, band_h, c)
        svg.rect(band_x, 150, band_w, band_h, "none", rx=34, stroke="#212529", stroke_width=2)
    else:
        left = COLOR_MAP.get(colors[0], "#ced4da")
        right = COLOR_MAP.get(colors[1], "#ced4da")
        draw_dual_color_circle(svg, CARD_W // 2, 188, 68, left, right)

    title = "WILD RENT" if colors == ["any"] else "RENT"
    svg.text(CARD_W // 2, 360, title, size=72, weight="900", fill="#111111")

    if colors == ["any"]:
        detail = "CHARGE RENT FOR ANY COLOR SET"
    else:
        detail = f"{colors[0].replace('_', ' ').upper()} / {colors[1].replace('_', ' ').upper()}"
    svg.text(CARD_W // 2, 415, detail, size=24, weight="800")

    svg.rect(70, 450, CARD_W - 140, 260, "#ffffff", rx=16, stroke="#212529", stroke_width=2, opacity=0.9)
    desc_lines = ["Choose one player", "and charge", "full rent."]
    for i, line in enumerate(desc_lines):
        svg.text(CARD_W // 2, 528 + i * 48, line, size=28, weight="700")

    svg.text(CARD_W // 2, CARD_H - 50, "MONODEAL 2024", size=22, weight="700", fill="#212529")


def action_symbol(name: str) -> str:
    symbols = {
        "Deal Breaker": "STEAL SET",
        "Sly Deal": "STEAL 1",
        "Forced Deal": "SWAP",
        "Debt Collector": "PAY 5M",
        "It's My Birthday": "ALL PAY 2M",
        "Pass Go": "DRAW 2",
        "Double The Rent": "x2",
        "Just Say No": "NO",
        "House": "HOUSE",
        "Hotel": "HOTEL",
    }
    return symbols.get(name, "ACTION")


def draw_action_card(svg: Svg, card: Card) -> None:
    name = card.name
    text = card.payload["text"]
    bank_value = card.payload["bank_value"]
    bg = ACTION_BG.get(name, "#adb5bd")

    svg.rect(0, 0, CARD_W, CARD_H, bg, rx=RADIUS, stroke="#111111", stroke_width=4)
    svg.rect(10, 10, CARD_W - 20, CARD_H - 20, "none", rx=RADIUS - 6, stroke="#ffffff", stroke_width=2)
    svg.rect(18, 18, CARD_W - 36, 92, "#ffffff", rx=14, opacity=0.94)
    svg.text(CARD_W // 2, 78, "ACTION", size=44, weight="900")
    draw_money_badge(svg, bank_value)

    title_lines = wrap_text(name.upper(), 16)
    title_size = 54 if len(title_lines) <= 2 else 46
    for i, line in enumerate(title_lines):
        svg.text(CARD_W // 2, 220 + i * 48, line, size=title_size, weight="900")

    symbol_y = 300 + max(0, (len(title_lines) - 2) * 22)
    svg.rect(120, symbol_y, CARD_W - 240, 150, "#ffffff", rx=75, stroke="#212529", stroke_width=3, opacity=0.9)
    symbol_text = action_symbol(name)
    symbol_size = 52 if len(symbol_text) <= 8 else 40
    svg.text(CARD_W // 2, symbol_y + 90, symbol_text, size=symbol_size, weight="900")

    desc_y = symbol_y + 200
    svg.rect(62, desc_y, CARD_W - 124, 250, "#ffffff", rx=16, stroke="#212529", stroke_width=2, opacity=0.92)
    desc_lines = wrap_text(text, 30)
    for i, line in enumerate(desc_lines[:5]):
        svg.text(CARD_W // 2, desc_y + 75 + i * 38, line, size=28, weight="700")

    svg.text(CARD_W // 2, CARD_H - 50, "MONODEAL 2024", size=22, weight="700", fill="#212529")


def draw_money_card(svg: Svg, card: Card) -> None:
    value = card.payload["value"]
    bg = MONEY_BG.get(value, "#ffe066")

    svg.rect(0, 0, CARD_W, CARD_H, bg, rx=RADIUS, stroke="#111111", stroke_width=4)
    svg.rect(10, 10, CARD_W - 20, CARD_H - 20, "none", rx=RADIUS - 6, stroke="#ffffff", stroke_width=2)

    svg.circle(CARD_W // 2, 300, 170, "#ffffff", stroke="#212529", stroke_width=4)
    denom = f"{value}M"
    # Keep denomination centered in one text node so 1-digit and 2-digit values align consistently.
    denom_size = 134 if value < 10 else 106
    svg.text(CARD_W // 2, 340, denom, size=denom_size, weight="900")

    svg.rect(70, 460, CARD_W - 140, 190, "#ffffff", rx=18, stroke="#212529", stroke_width=2, opacity=0.9)
    svg.text(CARD_W // 2, 540, "MONODEAL", size=44, weight="900")
    svg.text(CARD_W // 2, 595, "MONEY CARD", size=30, weight="800")

    svg.text(CARD_W // 2, CARD_H - 50, "MONODEAL 2024", size=22, weight="700", fill="#212529")


def draw_rule_card(svg: Svg, card: Card) -> None:
    draw_card_frame(svg)
    svg.rect(18, 18, CARD_W - 36, 120, "#f1f3f5", rx=18, stroke="#495057", stroke_width=2)
    svg.text(CARD_W // 2, 90, "QUICK START RULE", size=40, weight="900")

    svg.rect(50, 180, CARD_W - 100, 620, "#ffffff", rx=14, stroke="#adb5bd", stroke_width=2)
    lines = [
        "1. Draw 5 cards to start.",
        "2. Play up to 3 cards on your turn.",
        "3. If no cards, draw 5 at turn start.",
        "4. Build 3 full property sets to win.",
        "5. Bank money/action cards face up.",
        "6. Use Just Say No to cancel actions.",
    ]
    svg.text(CARD_W // 2, 230, "REFERENCE", size=28, weight="900")
    for i, line in enumerate(lines):
        svg.text(80, 295 + i * 72, line, size=24, weight="700", anchor="start")

    svg.text(CARD_W // 2, CARD_H - 50, "MONODEAL 2024", size=22, weight="700", fill="#495057")


def build_card_list(card_data: Dict[str, Any]) -> List[Card]:
    cards: List[Card] = []

    for entry in card_data["cards"]:
        kind = entry["type"]

        if kind == "property_group":
            for single in entry["cards"]:
                cards.append(
                    Card(
                        card_id=single["id"],
                        name=single["name"],
                        category="property",
                        payload={
                            "color": entry["color"],
                            "set_size": entry["set_size"],
                            "rent": entry["rent"],
                            "bank_value": entry["bank_value"],
                        },
                    )
                )
            continue

        if kind == "wild":
            count = int(entry["count"])
            for i in range(1, count + 1):
                card_id = f"wild_{slugify(entry['name'])}_{i}"
                cards.append(
                    Card(
                        card_id=card_id,
                        name=entry["name"],
                        category="wild",
                        payload={
                            "colors": entry["colors"],
                            "bank_value": entry["bank_value"],
                        },
                    )
                )
            continue

        if kind == "rent":
            count = int(entry["count"])
            label = "Wild Rent" if entry["colors"] == ["any"] else f"Rent {'/'.join(entry['colors'])}"
            for i in range(1, count + 1):
                card_id = f"rent_{slugify('_'.join(entry['colors']))}_{i}"
                cards.append(
                    Card(
                        card_id=card_id,
                        name=label,
                        category="rent",
                        payload={
                            "colors": entry["colors"],
                            "bank_value": entry["bank_value"],
                        },
                    )
                )
            continue

        if kind == "action":
            count = int(entry["count"])
            for i in range(1, count + 1):
                card_id = f"action_{slugify(entry['name'])}_{i}"
                cards.append(
                    Card(
                        card_id=card_id,
                        name=entry["name"],
                        category="action",
                        payload={
                            "text": entry["text"],
                            "bank_value": entry["bank_value"],
                        },
                    )
                )
            continue

        if kind == "money":
            count = int(entry["count"])
            for i in range(1, count + 1):
                card_id = f"money_{entry['value']}_{i}"
                cards.append(
                    Card(
                        card_id=card_id,
                        name=f"{entry['value']}M",
                        category="money",
                        payload={"value": entry["value"]},
                    )
                )
            continue

        if kind == "rule":
            count = int(entry["count"])
            for i in range(1, count + 1):
                card_id = f"rule_{slugify(entry['name'])}_{i}"
                cards.append(
                    Card(
                        card_id=card_id,
                        name=entry["name"],
                        category="rule",
                        payload={},
                    )
                )
            continue

        raise ValueError(f"Unsupported card type: {kind}")

    return cards


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_svg(path: Path, svg_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg_text, encoding="utf-8")


def render_card(card: Card) -> str:
    svg = Svg(CARD_W, CARD_H)
    if card.category == "property":
        draw_property_card(svg, card)
    elif card.category == "wild":
        draw_wild_card(svg, card)
    elif card.category == "rent":
        draw_rent_card(svg, card)
    elif card.category == "action":
        draw_action_card(svg, card)
    elif card.category == "money":
        draw_money_card(svg, card)
    elif card.category == "rule":
        draw_rule_card(svg, card)
    else:
        raise ValueError(f"Unsupported category: {card.category}")
    return svg.to_string()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Monopoly Deal SVG cards.")
    parser.add_argument("--cards", default="list_of_cards.json", help="Path to list_of_cards.json")
    parser.add_argument("--types", default="type_card_description.json", help="Path to type_card_description.json")
    parser.add_argument("--out", default="out/svg_cards", help="Output directory")
    args = parser.parse_args()

    cards_path = Path(args.cards)
    types_path = Path(args.types)
    out_dir = Path(args.out)

    card_data = load_json(cards_path)
    type_data = load_json(types_path)
    _ = type_data  # Included for future style/profile extensions.

    cards = build_card_list(card_data)

    category_counts = {
        "rule": sum(1 for c in cards if c.category == "rule"),
        "property": sum(1 for c in cards if c.category == "property"),
        "wild": sum(1 for c in cards if c.category == "wild"),
        "rent": sum(1 for c in cards if c.category == "rent"),
        "action": sum(1 for c in cards if c.category == "action"),
        "money": sum(1 for c in cards if c.category == "money"),
    }

    manifest: List[Dict[str, Any]] = []
    for index, card in enumerate(cards, start=1):
        filename = f"{index:03d}_{card.category}_{card.card_id}.svg"
        svg_text = render_card(card)
        save_svg(out_dir / filename, svg_text)
        manifest.append(
            {
                "index": index,
                "filename": filename,
                "id": card.card_id,
                "name": card.name,
                "category": card.category,
            }
        )

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    expected = card_data.get("meta", {}).get("total_cards")
    print(f"Generated {len(cards)} SVG files in: {out_dir}")
    if expected is not None and len(cards) != expected:
        print(f"WARNING: expected total_cards={expected}, but generated {len(cards)}")

    expected_breakdown = type_data.get("deck_breakdown", {})
    checks = [
        ("rule_cards_total", "rule"),
        ("property_cards_total", "property"),
        ("wild_property_cards_total", "wild"),
        ("rent_cards_total", "rent"),
        ("action_cards_total", "action"),
        ("money_cards_total", "money"),
    ]
    for expected_key, actual_key in checks:
        if expected_key in expected_breakdown:
            expected_value = expected_breakdown[expected_key]
            actual_value = category_counts[actual_key]
            if expected_value != actual_value:
                print(
                    f"WARNING: deck_breakdown[{expected_key}]={expected_value}, "
                    f"but computed {actual_value}"
                )


if __name__ == "__main__":
    main()
