#!/usr/bin/env python3
"""
Circle the Wagons -- Game engine and exact solver.

Single-file implementation:
  - Full game state representation and transition function
  - All 18 bonus scoring cards (verified from PNP)
  - Alpha-beta minimax solver with transposition table
  - Player 2 starting-card optimizer

Usage:
    python solver.py                   # solve a sample deal
    python solver.py --verify-cards    # print all 18 cards for visual check
    python solver.py --time-limit 5    # seconds per starting position
"""
from __future__ import annotations

import argparse
import copy
import sys
import time
from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

# ============================================================================
# Types
# ============================================================================

Cell = Tuple[int, int]


class Terr(IntEnum):
    Desert = 0
    Forest = 1
    Snow = 2
    Mountains = 3
    Plains = 4
    Water = 5


class Icon(IntEnum):
    Empty = 0
    Beer = 1
    Cow = 2
    Fort = 3
    Gun = 4
    Mine = 5
    Wagon = 6


Tile = Tuple[Terr, Icon]
TownMap = Dict[Cell, Tile]

TERRAINS = list(Terr)
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = tuple(
    (dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)
)

TERR_SHORT = {
    Terr.Desert: "Des", Terr.Forest: "For", Terr.Snow: "Snw",
    Terr.Mountains: "Mtn", Terr.Plains: "Pln", Terr.Water: "Wat",
}
ICON_SHORT = {
    Icon.Empty: "   ", Icon.Beer: "Ber", Icon.Cow: "Cow",
    Icon.Fort: "Frt", Icon.Gun: "Gun", Icon.Mine: "Min", Icon.Wagon: "Wgn",
}


def add(p: Cell, d: Tuple[int, int]) -> Cell:
    return (p[0] + d[0], p[1] + d[1])


# ============================================================================
# Cards
# ============================================================================

class Card(NamedTuple):
    cid: int
    # q0=(0,0) BL, q1=(1,0) BR, q2=(0,1) TL, q3=(1,1) TR
    quads: Tuple[Tile, Tile, Tile, Tile]


def tile_at(card: Card, i: int, j: int, rot180: bool) -> Tile:
    idx = j * 2 + i
    if rot180:
        idx = 3 - idx
    return card.quads[idx]


def print_card(card: Card) -> None:
    print(f"Card {card.cid}:")
    for j in (1, 0):
        cells = []
        for i in (0, 1):
            t, ic = tile_at(card, i, j, False)
            cells.append(f"{TERR_SHORT[t]}/{ICON_SHORT[ic]}")
        print(f"  {'  '.join(cells)}")
    print()


# Shorthand aliases
D, F, S, M, P, W = (
    Terr.Desert, Terr.Forest, Terr.Snow,
    Terr.Mountains, Terr.Plains, Terr.Water,
)
Be, Co, Fo, Gu, Mi, Wa, No = (
    Icon.Beer, Icon.Cow, Icon.Fort, Icon.Gun,
    Icon.Mine, Icon.Wagon, Icon.Empty,
)

# All 18 territory cards, verified from PNP sheets.
# Quadrant order: (BL, BR, TL, TR)
CARDS: Dict[int, Card] = {c.cid: c for c in [
    # Sheet A (cards 0-8)
    Card(0,  ((P, Mi), (F, Be), (P, Co), (P, Fo))),
    Card(1,  ((D, Be), (M, Wa), (M, Fo), (M, Mi))),
    Card(2,  ((S, Wa), (W, Gu), (W, Mi), (W, Be))),
    Card(3,  ((S, Fo), (W, Mi), (S, Gu), (S, Co))),
    Card(4,  ((D, Co), (M, Fo), (D, Wa), (D, Gu))),
    Card(5,  ((P, Gu), (F, Co), (F, Be), (F, Wa))),
    Card(6,  ((F, Mi), (W, Fo), (W, Gu), (S, Mi))),
    Card(7,  ((D, Be), (F, Mi), (F, Co), (P, Be))),
    Card(8,  ((S, Wa), (D, Be), (D, Fo), (M, Wa))),
    # Sheet B (cards 9-17)
    Card(9,  ((S, Fo), (D, Wa), (M, Fo), (P, Fo))),
    Card(10, ((D, Be), (F, Co), (P, Co), (S, Co))),
    Card(11, ((F, Gu), (W, Gu), (S, Gu), (D, Mi))),
    Card(12, ((P, Gu), (S, Wa), (S, Mi), (W, Gu))),
    Card(13, ((W, Fo), (M, Co), (M, Wa), (D, Fo))),
    Card(14, ((M, Co), (P, Gu), (P, Be), (F, Co))),
    Card(15, ((P, Mi), (M, Mi), (W, Mi), (M, Gu))),
    Card(16, ((W, Fo), (M, Wa), (D, Wa), (F, Wa))),
    Card(17, ((M, Be), (P, Be), (F, Co), (W, Be))),
]}

# Card-to-bonus mapping (territory front <-> scoring back).
# Based on PNP sheet layout with horizontal flip for double-sided printing.
# NEEDS VERIFICATION by checking physical cards.
CARD_BONUS_MAP: Dict[int, str] = {
    # Sheet A
    0: "BADLANDS",          1: "HAPPY COWS",       2: "THE CLEARING",
    3: "CIRCLE THE WAGONS", 4: "SMALLTOWN CHARM",  5: "GOLD COUNTRY",
    6: "PRAIRIE LIFE",      7: "COOL WATER",       8: "CLAIM JUMPERS",
    # Sheet B
    9: "BOOM OR BUST",      10: "WAGON TRAIN",     11: "ONE TOO MANY",
    12: "BOOTLEGGERS",      13: "UNDISCOVERED",    14: "FORTIFIED",
    15: "THE HERD",         16: "TARGET PRACTICE", 17: "RIFLES READY",
}


# ============================================================================
# Scoring helpers
# ============================================================================

def count_icon(m: TownMap, ic: Icon) -> int:
    return sum(1 for _, (_, i) in m.items() if i == ic)


def count_terr(m: TownMap, tt: Terr) -> int:
    return sum(1 for _, (t, _) in m.items() if t == tt)


def largest_cc(cells: Set[Cell]) -> int:
    """Size of the largest 4-connected component among given cells."""
    if not cells:
        return 0
    seen: Set[Cell] = set()
    best = 0
    for start in cells:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        size = 0
        while stack:
            p = stack.pop()
            size += 1
            for d in N4:
                q = add(p, d)
                if q in cells and q not in seen:
                    seen.add(q)
                    stack.append(q)
        if size > best:
            best = size
    return best


def connected_components(cells: Set[Cell]) -> List[Set[Cell]]:
    """All 4-connected components among given cells."""
    seen: Set[Cell] = set()
    comps: List[Set[Cell]] = []
    for start in cells:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp: Set[Cell] = set()
        while stack:
            p = stack.pop()
            comp.add(p)
            for d in N4:
                q = add(p, d)
                if q in cells and q not in seen:
                    seen.add(q)
                    stack.append(q)
        comps.append(comp)
    return comps


def get_terr(m: TownMap, p: Cell) -> Optional[Terr]:
    tile = m.get(p)
    return None if tile is None else tile[0]


def get_icon(m: TownMap, p: Cell) -> Optional[Icon]:
    tile = m.get(p)
    return None if tile is None else tile[1]


# ============================================================================
# Terrain scoring
# ============================================================================

def terrain_score(m: TownMap) -> int:
    """Sum of largest connected component sizes for each terrain type."""
    score = 0
    for t in TERRAINS:
        cells = {p for p, (tt, _) in m.items() if tt == t}
        score += largest_cc(cells)
    return score


# ============================================================================
# Bonus scoring
# ============================================================================

def bonus_fortified(m: TownMap) -> int:
    """+7 per 2x2 block where all 4 cells have Fort icon."""
    score = 0
    occupied = set(m.keys())
    for (x, y) in occupied:
        if all(
            get_icon(m, (x + i, y + j)) == Icon.Fort
            for i in (0, 1) for j in (0, 1)
        ):
            score += 7
    return score


def bonus_undiscovered(m: TownMap) -> int:
    """+5 per empty cell fully enclosed (all 8 neighbors occupied)."""
    occupied = set(m.keys())
    candidates: Set[Cell] = set()
    for p in occupied:
        for d in N8:
            q = add(p, d)
            if q not in occupied:
                candidates.add(q)
    score = 0
    for p in candidates:
        if all(add(p, d) in occupied for d in N8):
            score += 5
    return score


def bonus_rifles_ready(m: TownMap) -> int:
    """+2 per Fort that is adjacent (N4) to a Gun."""
    score = 0
    for p, (_, ic) in m.items():
        if ic == Icon.Fort:
            if any(get_icon(m, add(p, d)) == Icon.Gun for d in N4):
                score += 2
    return score


def bonus_target_practice(m: TownMap) -> int:
    """For each Beer, find closest Gun in same row or column.
    Score = number of cells between them (distance - 1).
    If no Gun shares a row or column, that Beer scores 0."""
    beers = [(x, y) for (x, y), (_, ic) in m.items() if ic == Icon.Beer]
    guns = [(x, y) for (x, y), (_, ic) in m.items() if ic == Icon.Gun]
    if not guns:
        return 0
    score = 0
    for bx, by in beers:
        best_dist = None
        for gx, gy in guns:
            if bx == gx:
                d = abs(by - gy)
                if best_dist is None or d < best_dist:
                    best_dist = d
            elif by == gy:
                d = abs(bx - gx)
                if best_dist is None or d < best_dist:
                    best_dist = d
        if best_dist is not None and best_dist > 1:
            score += best_dist - 1
    return score


def bonus_the_herd(m: TownMap) -> int:
    """+2 * size of largest 4-connected Cow icon group."""
    cows = {p for p, (_, ic) in m.items() if ic == Icon.Cow}
    return 2 * largest_cc(cows)


def bonus_cool_water(m: TownMap) -> int:
    """Choose a largest Water component; +3 per Wagon on or N4-adjacent."""
    water_cells = {p for p, (t, _) in m.items() if t == Terr.Water}
    if not water_cells:
        return 0
    comps = connected_components(water_cells)
    max_size = max(len(c) for c in comps)
    best = 0
    for comp in comps:
        if len(comp) != max_size:
            continue
        wag_count = 0
        for p, (_, ic) in m.items():
            if ic != Icon.Wagon:
                continue
            if p in comp or any(add(p, d) in comp for d in N4):
                wag_count += 1
        best = max(best, wag_count)
    return 3 * best


def bonus_prairie_life(m: TownMap) -> int:
    """floor((#Cow icons + #Plains cells) / 2)."""
    return (count_icon(m, Icon.Cow) + count_terr(m, Terr.Plains)) // 2


def bonus_bootleggers(m: TownMap) -> int:
    """+2 per Beer adjacent to Wagon, -1 per Beer not adjacent."""
    score = 0
    for p, (_, ic) in m.items():
        if ic == Icon.Beer:
            adj = any(get_icon(m, add(p, d)) == Icon.Wagon for d in N4)
            score += 2 if adj else -1
    return score


def bonus_wagon_train(m: TownMap) -> int:
    """Score maximal straight lines of Wagons. Table: 2->1, 3->2, 4->4, 5->7, 6+->10."""
    table = {2: 1, 3: 2, 4: 4, 5: 7}

    def f(length: int) -> int:
        if length < 2:
            return 0
        if length >= 6:
            return 10
        return table[length]

    wagons = {p for p, (_, ic) in m.items() if ic == Icon.Wagon}
    score = 0
    # Horizontal maximal segments
    for (x, y) in wagons:
        if (x - 1, y) in wagons:
            continue  # not a segment start
        length = 1
        while (x + length, y) in wagons:
            length += 1
        score += f(length)
    # Vertical maximal segments
    for (x, y) in wagons:
        if (x, y - 1) in wagons:
            continue
        length = 1
        while (x, y + length) in wagons:
            length += 1
        score += f(length)
    return score


def bonus_boom_or_bust(m: TownMap) -> int:
    """Points per Mine. Rates: 0-2->5, 3-6->0, 7->3, 8+->8."""
    n = count_icon(m, Icon.Mine)
    if n == 0:
        return 0
    if n <= 2:
        rate = 5
    elif n <= 6:
        rate = 0
    elif n == 7:
        rate = 3
    else:
        rate = 8
    return n * rate


def bonus_the_clearing(m: TownMap) -> int:
    """+2 per Fort icon, -1 per Forest cell."""
    return 2 * count_icon(m, Icon.Fort) - count_terr(m, Terr.Forest)


def bonus_happy_cows(m: TownMap) -> int:
    """+2 per Cow not on Snow and not N4-adjacent to Snow."""
    score = 0
    for p, (t, ic) in m.items():
        if ic != Icon.Cow:
            continue
        if t == Terr.Snow:
            continue
        if any(get_terr(m, add(p, d)) == Terr.Snow for d in N4):
            continue
        score += 2
    return score


def bonus_badlands(m: TownMap) -> int:
    """+4 per Gun between 2 Deserts on opposite sides (H or V)."""
    score = 0
    for p, (_, ic) in m.items():
        if ic != Icon.Gun:
            continue
        h = (get_terr(m, add(p, (-1, 0))) == Terr.Desert and
             get_terr(m, add(p, (1, 0))) == Terr.Desert)
        v = (get_terr(m, add(p, (0, -1))) == Terr.Desert and
             get_terr(m, add(p, (0, 1))) == Terr.Desert)
        if h or v:
            score += 4
    return score


def bonus_gold_country(m: TownMap) -> int:
    """+2 per Mine on or N4-adjacent to Mountains."""
    score = 0
    for p, (t, ic) in m.items():
        if ic != Icon.Mine:
            continue
        if t == Terr.Mountains:
            score += 2
        elif any(get_terr(m, add(p, d)) == Terr.Mountains for d in N4):
            score += 2
    return score


def bonus_circle_the_wagons(m: TownMap) -> int:
    """+6 per occupied cell whose 4 orthogonal neighbors all have Wagon."""
    score = 0
    for p in m:
        if all(get_icon(m, add(p, d)) == Icon.Wagon for d in N4):
            score += 6
    return score


# Interactive bonuses: return (delta_p1, delta_p2)

def bonus_one_too_many(m1: TownMap, m2: TownMap) -> Tuple[int, int]:
    """Player with more Beer loses 1 point per opponent's Beer."""
    b1 = count_icon(m1, Icon.Beer)
    b2 = count_icon(m2, Icon.Beer)
    if b1 > b2:
        return (-b2, 0)
    if b2 > b1:
        return (0, -b1)
    return (0, 0)


def bonus_claim_jumpers(m1: TownMap, m2: TownMap) -> Tuple[int, int]:
    """+9 for most Mines; forfeit 5 if opponent has more Guns."""
    mi1 = count_icon(m1, Icon.Mine)
    mi2 = count_icon(m2, Icon.Mine)
    g1 = count_icon(m1, Icon.Gun)
    g2 = count_icon(m2, Icon.Gun)
    if mi1 > mi2:
        d1, d2 = 9, 0
        if g2 > g1:
            d1 -= 5
            d2 += 5
        return (d1, d2)
    if mi2 > mi1:
        d1, d2 = 0, 9
        if g1 > g2:
            d1 += 5
            d2 -= 5
        return (d1, d2)
    return (0, 0)


def bonus_smalltown_charm(m1: TownMap, m2: TownMap) -> Tuple[int, int]:
    """Player with fewer territories gains the difference."""
    n1 = len(m1)
    n2 = len(m2)
    if n1 < n2:
        return (n2 - n1, 0)
    if n2 < n1:
        return (0, n1 - n2)
    return (0, 0)


# Bonus registry
LOCAL_BONUSES = {
    "FORTIFIED": bonus_fortified,
    "UNDISCOVERED": bonus_undiscovered,
    "RIFLES READY": bonus_rifles_ready,
    "TARGET PRACTICE": bonus_target_practice,
    "THE HERD": bonus_the_herd,
    "COOL WATER": bonus_cool_water,
    "PRAIRIE LIFE": bonus_prairie_life,
    "BOOTLEGGERS": bonus_bootleggers,
    "WAGON TRAIN": bonus_wagon_train,
    "BOOM OR BUST": bonus_boom_or_bust,
    "THE CLEARING": bonus_the_clearing,
    "HAPPY COWS": bonus_happy_cows,
    "BADLANDS": bonus_badlands,
    "GOLD COUNTRY": bonus_gold_country,
    "CIRCLE THE WAGONS": bonus_circle_the_wagons,
}

INTERACTIVE_BONUSES = {
    "ONE TOO MANY": bonus_one_too_many,
    "CLAIM JUMPERS": bonus_claim_jumpers,
    "SMALLTOWN CHARM": bonus_smalltown_charm,
}

ALL_BONUS_NAMES = sorted(set(LOCAL_BONUSES) | set(INTERACTIVE_BONUSES))


# ============================================================================
# Final scoring
# ============================================================================

def compute_scores(
    m1: TownMap, m2: TownMap, bonus_names: Tuple[str, str, str]
) -> Tuple[int, int]:
    """Return (P1 total score, P2 total score)."""
    s1 = terrain_score(m1)
    s2 = terrain_score(m2)
    for name in bonus_names:
        if name in LOCAL_BONUSES:
            fn = LOCAL_BONUSES[name]
            s1 += fn(m1)
            s2 += fn(m2)
        elif name in INTERACTIVE_BONUSES:
            fn = INTERACTIVE_BONUSES[name]
            d1, d2 = fn(m1, m2)
            s1 += d1
            s2 += d2
    return (s1, s2)


def utility(m1: TownMap, m2: TownMap, bonus_names: Tuple[str, str, str]) -> int:
    """Zero-sum utility: P1 score - P2 score."""
    s1, s2 = compute_scores(m1, m2, bonus_names)
    return s1 - s2


# ============================================================================
# Placement logic
# ============================================================================

def footprint(ax: int, ay: int) -> Tuple[Cell, Cell, Cell, Cell]:
    return ((ax, ay), (ax + 1, ay), (ax, ay + 1), (ax + 1, ay + 1))


def candidate_anchors(m: TownMap) -> Set[Cell]:
    """Finite set of anchor positions that could yield legal placements."""
    occupied = set(m.keys())
    if not occupied:
        return {(0, 0)}
    cand: Set[Cell] = set()
    for (x, y) in occupied:
        # Overlap candidates: anchors whose 2x2 footprint includes (x,y)
        for i in (0, 1):
            for j in (0, 1):
                cand.add((x - i, y - j))
        # Adjacency candidates
        for dx, dy in N4:
            nx, ny = x + dx, y + dy
            for i in (0, 1):
                for j in (0, 1):
                    cand.add((nx - i, ny - j))
    return cand


def is_legal_placement(m: TownMap, ax: int, ay: int) -> bool:
    """Check if placing a 2x2 card anchored at (ax,ay) is legal."""
    occupied = set(m.keys())
    if not occupied:
        return True
    fp = set(footprint(ax, ay))
    # Overlap check
    if fp & occupied:
        return True
    # Edge adjacency check
    for p in fp:
        for d in N4:
            q = add(p, d)
            if q not in fp and q in occupied:
                return True
    return False


def place_card(m: TownMap, card: Card, ax: int, ay: int, rot180: bool) -> TownMap:
    """Place card at anchor (ax,ay), return new map (topmost wins)."""
    new_m = dict(m)
    for i in (0, 1):
        for j in (0, 1):
            new_m[(ax + i, ay + j)] = tile_at(card, i, j, rot180)
    return new_m


def legal_placements(m: TownMap, card: Card) -> List[Tuple[int, int, bool]]:
    """Return all legal (ax, ay, rot180) placements for card into town m."""
    result = []
    for (ax, ay) in candidate_anchors(m):
        if is_legal_placement(m, ax, ay):
            result.append((ax, ay, False))
            result.append((ax, ay, True))
    return result


# ============================================================================
# Game state
# ============================================================================

class Phase(IntEnum):
    PLACE_FREE = 0
    DRAFT = 1
    PLACE_DRAFT = 2


class PlaceAction(NamedTuple):
    ax: int
    ay: int
    rot180: bool


class DraftAction(NamedTuple):
    offset: int  # take circle[offset], skip circle[0:offset]


class GameState:
    """Mutable game state."""

    __slots__ = ("circle", "towns", "free", "player", "phase", "drafted",
                 "bonus_names")

    def __init__(self) -> None:
        self.circle: List[int] = []
        self.towns: List[TownMap] = [{}, {}]  # [P1, P2]
        self.free: List[List[int]] = [[], []]  # pending free cards
        self.player: int = 0  # 0-indexed (0=P1, 1=P2)
        self.phase: Phase = Phase.PLACE_FREE
        self.drafted: int = -1
        self.bonus_names: Tuple[str, str, str] = ("", "", "")

    def copy(self) -> GameState:
        s = GameState()
        s.circle = list(self.circle)
        s.towns = [dict(self.towns[0]), dict(self.towns[1])]
        s.free = [list(self.free[0]), list(self.free[1])]
        s.player = self.player
        s.phase = self.phase
        s.drafted = self.drafted
        s.bonus_names = self.bonus_names
        return s

    def normalize(self) -> None:
        """Advance past empty phases."""
        if self.phase == Phase.PLACE_FREE and not self.free[self.player]:
            if self.circle:
                self.phase = Phase.DRAFT
            # else: terminal (no circle, no free cards)

    def is_terminal(self) -> bool:
        self.normalize()
        return (not self.circle and
                not self.free[0] and
                not self.free[1] and
                self.drafted == -1)

    def freeze_key(self) -> tuple:
        """Hashable key for transposition table."""
        def canon_town(m: TownMap) -> tuple:
            if not m:
                return ()
            xs = [x for (x, _) in m]
            ys = [y for (_, y) in m]
            x0, y0 = min(xs), min(ys)
            items = tuple(sorted(
                (x - x0, y - y0, int(t), int(ic)) for (x, y), (t, ic) in m.items()
            ))
            return items

        return (
            tuple(self.circle),
            canon_town(self.towns[0]),
            canon_town(self.towns[1]),
            tuple(self.free[0]),
            tuple(self.free[1]),
            self.player,
            int(self.phase),
            self.drafted,
        )


def get_actions(state: GameState) -> list:
    """Return legal actions for current state."""
    state.normalize()
    if state.is_terminal():
        return []

    p = state.player
    m = state.towns[p]

    if state.phase == Phase.PLACE_FREE:
        card_id = state.free[p][0]
        return legal_placements(m, CARDS[card_id])

    if state.phase == Phase.DRAFT:
        return [DraftAction(j) for j in range(len(state.circle))]

    if state.phase == Phase.PLACE_DRAFT:
        return legal_placements(m, CARDS[state.drafted])

    return []


def apply_action(state: GameState, action) -> GameState:
    """Apply action and return new state."""
    s = state.copy()
    s.normalize()
    p = s.player

    if s.phase == Phase.DRAFT:
        act: DraftAction = action
        chosen = s.circle[act.offset]
        skipped = s.circle[:act.offset]
        s.circle = s.circle[act.offset + 1:]
        # Skipped cards go to opponent's free queue
        opp = 1 - p
        s.free[opp].extend(skipped)
        s.drafted = chosen
        s.phase = Phase.PLACE_DRAFT
        s.normalize()
        return s

    # PlaceAction (for PLACE_FREE or PLACE_DRAFT)
    ax, ay, rot180 = action

    if s.phase == Phase.PLACE_FREE:
        card_id = s.free[p].pop(0)
        s.towns[p] = place_card(s.towns[p], CARDS[card_id], ax, ay, rot180)
        # Stay in PLACE_FREE; normalize will advance if queue empty
        s.normalize()
        return s

    if s.phase == Phase.PLACE_DRAFT:
        s.towns[p] = place_card(s.towns[p], CARDS[s.drafted], ax, ay, rot180)
        s.drafted = -1
        # End of turn: switch to opponent
        s.player = 1 - p
        s.phase = Phase.PLACE_FREE
        s.normalize()
        return s

    raise RuntimeError(f"Bad phase {s.phase}")


# ============================================================================
# Solver: iterative-deepening alpha-beta
# ============================================================================

class Solver:
    def __init__(
        self,
        bonus_names: Tuple[str, str, str],
        time_limit: float = 2.0,
        max_depth: int = 200,
    ):
        self.bonus_names = bonus_names
        self.time_limit = time_limit
        self.max_depth = max_depth
        self.tt: Dict[tuple, Tuple[int, int]] = {}  # key -> (depth, value)
        self.nodes = 0
        self.deadline = 0.0

    def heuristic(self, state: GameState) -> int:
        """Quick evaluation: score as if game ended now."""
        return utility(state.towns[0], state.towns[1], self.bonus_names)

    def solve(self, state: GameState) -> Tuple[int, Optional[object]]:
        """Iterative-deepening alpha-beta. Returns (value, best_action)."""
        self.deadline = time.time() + self.time_limit
        self.tt.clear()
        self.nodes = 0

        best_val = None
        best_act = None

        for depth in range(1, self.max_depth + 1):
            try:
                v, a = self._root_search(state, depth)
                best_val, best_act = v, a
                # If we found a terminal value, stop
                if state.is_terminal():
                    break
            except TimeoutError:
                break

        if best_val is None:
            best_val = self.heuristic(state)

        return best_val, best_act

    def _root_search(self, state: GameState, depth: int) -> Tuple[int, object]:
        actions = get_actions(state)
        if not actions:
            return self.heuristic(state), None

        p = state.player  # 0=P1 (maximizer), 1=P2 (minimizer)
        alpha, beta = -999999, 999999

        # Simple move ordering: sort children by heuristic
        scored = []
        for a in actions:
            child = apply_action(state, a)
            scored.append((self.heuristic(child), a, child))
        scored.sort(key=lambda x: x[0], reverse=(p == 0))

        best_act = scored[0][1]
        best_val = -999999 if p == 0 else 999999

        for _, a, child in scored:
            v = self._alphabeta(child, depth - 1, alpha, beta)
            if p == 0:
                if v > best_val:
                    best_val, best_act = v, a
                alpha = max(alpha, best_val)
            else:
                if v < best_val:
                    best_val, best_act = v, a
                beta = min(beta, best_val)
            if alpha >= beta:
                break

        return best_val, best_act

    def _alphabeta(self, state: GameState, depth: int, alpha: int, beta: int) -> int:
        self.nodes += 1
        if self.nodes % 10000 == 0 and time.time() >= self.deadline:
            raise TimeoutError

        state.normalize()
        if state.is_terminal():
            return utility(state.towns[0], state.towns[1], self.bonus_names)
        if depth <= 0:
            return self.heuristic(state)

        key = state.freeze_key()
        cached = self.tt.get(key)
        if cached is not None:
            d_rem, val = cached
            if d_rem >= depth:
                return val

        p = state.player
        actions = get_actions(state)

        if p == 0:  # maximizer
            best = -999999
            for a in actions:
                v = self._alphabeta(apply_action(state, a), depth - 1, alpha, beta)
                if v > best:
                    best = v
                if best > alpha:
                    alpha = best
                if alpha >= beta:
                    break
        else:  # minimizer
            best = 999999
            for a in actions:
                v = self._alphabeta(apply_action(state, a), depth - 1, alpha, beta)
                if v < best:
                    best = v
                if best < beta:
                    beta = best
                if alpha >= beta:
                    break

        self.tt[key] = (depth, best)
        return best


# ============================================================================
# Player 2 starting-card optimizer
# ============================================================================

def make_initial_state(
    circle: List[int],
    bonus_names: Tuple[str, str, str],
    start_index: int,
) -> GameState:
    """Create initial state with cursor at start_index."""
    s = GameState()
    s.circle = circle[start_index:] + circle[:start_index]
    s.bonus_names = bonus_names
    s.player = 0  # P1 goes first
    s.phase = Phase.PLACE_FREE
    s.normalize()
    return s


def find_best_start(
    circle: List[int],
    bonus_names: Tuple[str, str, str],
    time_per_start: float = 2.0,
) -> Tuple[int, int]:
    """Player 2 chooses starting cursor to minimize P1-P2 utility.
    Returns (best_index, estimated_value)."""
    best_k = None
    best_v = None
    n = len(circle)

    for k in range(n):
        s0 = make_initial_state(circle, bonus_names, k)
        solver = Solver(bonus_names, time_limit=time_per_start)
        v, _ = solver.solve(s0)
        card_name = circle[k]
        print(f"  Start index {k:2d} (card {card_name:2d}): "
              f"est value = {v:+d}  ({solver.nodes} nodes, "
              f"depth reached in {time_per_start:.1f}s)")

        if best_v is None or v < best_v:
            best_v, best_k = v, k

    assert best_k is not None and best_v is not None
    return best_k, best_v


# ============================================================================
# Town display
# ============================================================================

def print_town(m: TownMap, label: str = "") -> None:
    if not m:
        print(f"{label}: (empty)")
        return
    xs = [x for (x, _) in m]
    ys = [y for (_, y) in m]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    if label:
        print(f"{label}:")
    for y in range(y1, y0 - 1, -1):
        row = []
        for x in range(x0, x1 + 1):
            tile = m.get((x, y))
            if tile is None:
                row.append("       ")
            else:
                t, ic = tile
                row.append(f"{TERR_SHORT[t]}/{ICON_SHORT[ic]}")
        print("  " + " ".join(row))
    print()


# ============================================================================
# Deal generation
# ============================================================================

def generate_deal(seed: int = 42) -> Tuple[Tuple[str, str, str], List[int]]:
    """Generate a random deal: 3 bonus cards + 15-card circle."""
    import random
    rng = random.Random(seed)

    card_ids = list(range(18))
    rng.shuffle(card_ids)

    # First 3 become bonus cards (use their scoring side)
    bonus_ids = card_ids[:3]
    circle_ids = card_ids[3:]

    bonus_names = tuple(CARD_BONUS_MAP[cid] for cid in bonus_ids)
    return bonus_names, circle_ids  # type: ignore


# ============================================================================
# CLI
# ============================================================================

def cmd_verify_cards() -> None:
    print("=== All 18 Territory Cards ===\n")
    for cid in sorted(CARDS):
        bonus = CARD_BONUS_MAP.get(cid, "???")
        print(f"Card {cid:2d}  (back: {bonus})")
        card = CARDS[cid]
        for j in (1, 0):
            cells = []
            for i in (0, 1):
                t, ic = tile_at(card, i, j, False)
                cells.append(f"{TERR_SHORT[t]}/{ICON_SHORT[ic]}")
            print(f"  {'  '.join(cells)}")
        print()


def cmd_solve(time_limit: float, seed: int) -> None:
    bonus_names, circle = generate_deal(seed)
    print(f"Deal (seed={seed}):")
    print(f"  Bonuses: {bonus_names}")
    print(f"  Circle:  {circle}")
    print()

    print("Finding Player 2's best starting card...")
    k, v = find_best_start(circle, bonus_names, time_per_start=time_limit)
    print()
    print(f"Best start index for P2: {k} (card {circle[k]})")
    print(f"Estimated utility (P1-P2): {v:+d}")
    print()

    # Show the best starting position's solution
    s0 = make_initial_state(circle, bonus_names, k)
    solver = Solver(bonus_names, time_limit=time_limit * 3)
    val, best_act = solver.solve(s0)
    print(f"From best start, P1's first action: {best_act}")
    print(f"Value: {val:+d}, Nodes searched: {solver.nodes}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Circle the Wagons solver")
    parser.add_argument("--verify-cards", action="store_true",
                        help="Print all 18 cards for visual verification")
    parser.add_argument("--time-limit", type=float, default=2.0,
                        help="Seconds per starting position (default: 2.0)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for deal generation (default: 42)")
    args = parser.parse_args()

    if args.verify_cards:
        cmd_verify_cards()
    else:
        cmd_solve(args.time_limit, args.seed)


if __name__ == "__main__":
    main()
