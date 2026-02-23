#!/usr/bin/env python3
"""
Circle the Wagons -- Game engine and solver.

Single-file implementation:
  - Full game state representation and transition function
  - All 18 bonus scoring cards (verified from PNP)
  - Lookahead agent: draft minimax + greedy placement (strongest)
  - Alpha-beta endgame solver with aspiration windows
  - MCTS solver, player 2 starting-card optimizer
  - Benchmark, analysis, and playthrough modes

Usage:
    python solver.py                       # solve a sample deal
    python solver.py --verify-cards        # print all 18 cards
    python solver.py --play --seed 42      # play through a complete game
    python solver.py --benchmark -n 20     # solver vs random benchmark
    python solver.py --time-limit 5        # seconds per starting position
"""
from __future__ import annotations

import argparse
import math
import random as random_module
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
            x, y = stack.pop()
            size += 1
            for q in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
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
            x, y = stack.pop()
            comp.add((x, y))
            for q in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                if q in cells and q not in seen:
                    seen.add(q)
                    stack.append(q)
        comps.append(comp)
    return comps



# ============================================================================
# Terrain scoring
# ============================================================================

def terrain_score(m: TownMap) -> int:
    """Sum of largest connected component sizes for each terrain type.
    Optimized: single pass to group cells by terrain, then BFS inline."""
    # Group cells by terrain in one pass
    by_terr: List[List[Cell]] = [[] for _ in range(6)]
    for p, (tt, _) in m.items():
        by_terr[tt].append(p)

    score = 0
    for cells_list in by_terr:
        if not cells_list:
            continue
        cells_set = set(cells_list)
        seen: Set[Cell] = set()
        best = 0
        for start in cells_list:
            if start in seen:
                continue
            stack = [start]
            seen.add(start)
            size = 0
            while stack:
                x, y = stack.pop()
                size += 1
                for q in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if q in cells_set and q not in seen:
                        seen.add(q)
                        stack.append(q)
            if size > best:
                best = size
        score += best
    return score


# ============================================================================
# Bonus scoring
# ============================================================================

def bonus_fortified(m: TownMap) -> int:
    """+7 per 2x2 block where all 4 cells have Fort icon."""
    score = 0
    Ft = Icon.Fort
    for x, y in m:
        t00 = m.get((x, y))
        t10 = m.get((x+1, y))
        t01 = m.get((x, y+1))
        t11 = m.get((x+1, y+1))
        if (t00 is not None and t00[1] == Ft and
            t10 is not None and t10[1] == Ft and
            t01 is not None and t01[1] == Ft and
            t11 is not None and t11[1] == Ft):
            score += 7
    return score


def bonus_undiscovered(m: TownMap) -> int:
    """+5 per empty cell fully enclosed (all 8 neighbors occupied).
    Optimized: use dict membership directly, skip cells in m early."""
    score = 0
    checked: Set[Cell] = set()
    m_contains = m.__contains__  # avoid attribute lookup in inner loop
    checked_contains = checked.__contains__
    checked_add = checked.add
    for x, y in m:
        for dx, dy in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            nx, ny = x + dx, y + dy
            key = (nx, ny)
            if m_contains(key) or checked_contains(key):
                continue
            checked_add(key)
            # Check all 8 neighbors — fail fast on first missing
            if (m_contains((nx-1, ny-1)) and m_contains((nx, ny-1)) and
                m_contains((nx+1, ny-1)) and m_contains((nx-1, ny)) and
                m_contains((nx+1, ny)) and m_contains((nx-1, ny+1)) and
                m_contains((nx, ny+1)) and m_contains((nx+1, ny+1))):
                score += 5
    return score


def bonus_rifles_ready(m: TownMap) -> int:
    """+2 per Fort that is adjacent (N4) to a Gun."""
    score = 0
    for (x, y), (_, ic) in m.items():
        if ic == Icon.Fort:
            for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                t = m.get((nx, ny))
                if t is not None and t[1] == Icon.Gun:
                    score += 2
                    break
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
        for (x, y), (_, ic) in m.items():
            if ic != Icon.Wagon:
                continue
            if ((x, y) in comp or (x+1,y) in comp or (x-1,y) in comp or
                (x,y+1) in comp or (x,y-1) in comp):
                wag_count += 1
        best = max(best, wag_count)
    return 3 * best


def bonus_prairie_life(m: TownMap) -> int:
    """floor((#Cow icons + #Plains cells) / 2)."""
    return (count_icon(m, Icon.Cow) + count_terr(m, Terr.Plains)) // 2


def bonus_bootleggers(m: TownMap) -> int:
    """+2 per Beer adjacent to Wagon, -1 per Beer not adjacent."""
    score = 0
    for (x, y), (_, ic) in m.items():
        if ic == Icon.Beer:
            adj = False
            for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                t = m.get((nx, ny))
                if t is not None and t[1] == Icon.Wagon:
                    adj = True
                    break
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
    Snw = Terr.Snow
    score = 0
    for (x, y), (t, ic) in m.items():
        if ic != Icon.Cow or t == Snw:
            continue
        adj_snow = False
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            nb = m.get((nx, ny))
            if nb is not None and nb[0] == Snw:
                adj_snow = True
                break
        if not adj_snow:
            score += 2
    return score


def bonus_badlands(m: TownMap) -> int:
    """+4 per Gun between 2 Deserts on opposite sides (H or V)."""
    Ds = Terr.Desert
    score = 0
    for (x, y), (_, ic) in m.items():
        if ic != Icon.Gun:
            continue
        left = m.get((x-1, y))
        right = m.get((x+1, y))
        h = (left is not None and left[0] == Ds and
             right is not None and right[0] == Ds)
        down = m.get((x, y-1))
        up = m.get((x, y+1))
        v = (down is not None and down[0] == Ds and
             up is not None and up[0] == Ds)
        if h or v:
            score += 4
    return score


def bonus_gold_country(m: TownMap) -> int:
    """+2 per Mine on or N4-adjacent to Mountains."""
    Mtn = Terr.Mountains
    score = 0
    for (x, y), (t, ic) in m.items():
        if ic != Icon.Mine:
            continue
        if t == Mtn:
            score += 2
            continue
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            nb = m.get((nx, ny))
            if nb is not None and nb[0] == Mtn:
                score += 2
                break
    return score


def bonus_circle_the_wagons(m: TownMap) -> int:
    """+6 per occupied cell whose 4 orthogonal neighbors all have Wagon."""
    Wg = Icon.Wagon
    score = 0
    for x, y in m:
        ok = True
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            nb = m.get((nx, ny))
            if nb is None or nb[1] != Wg:
                ok = False
                break
        if ok:
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

def resolve_bonus_fns(
    bonus_names: Tuple[str, str, str],
) -> Tuple[list, list]:
    """Resolve bonus names to function lists once per deal.
    Returns (local_fns, interactive_fns)."""
    local_fns = []
    interactive_fns = []
    for name in bonus_names:
        if name in LOCAL_BONUSES:
            local_fns.append(LOCAL_BONUSES[name])
        elif name in INTERACTIVE_BONUSES:
            interactive_fns.append(INTERACTIVE_BONUSES[name])
    return local_fns, interactive_fns

# Cache for resolved bonus functions (keyed by bonus_names tuple)
_bonus_fn_cache: Dict[tuple, Tuple[list, list]] = {}

def _get_bonus_fns(bonus_names: Tuple[str, str, str]) -> Tuple[list, list]:
    key = bonus_names
    if key not in _bonus_fn_cache:
        _bonus_fn_cache[key] = resolve_bonus_fns(bonus_names)
    return _bonus_fn_cache[key]


def compute_scores(
    m1: TownMap, m2: TownMap, bonus_names: Tuple[str, str, str]
) -> Tuple[int, int]:
    """Return (P1 total score, P2 total score)."""
    s1 = terrain_score(m1)
    s2 = terrain_score(m2)
    local_fns, interactive_fns = _get_bonus_fns(bonus_names)
    for fn in local_fns:
        s1 += fn(m1)
        s2 += fn(m2)
    for fn in interactive_fns:
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

# Precomputed: all (dx,dy) offsets from an occupied cell that yield valid anchors.
# Covers both overlap (footprint covers the cell) and edge-adjacency (footprint
# touches a N4 neighbor). 12 offsets vs the old code's 20 iterations.
_ANCHOR_OFFSETS = (
    (-2, -1), (-2, 0), (-1, -2), (-1, -1), (-1, 0), (-1, 1),
    (0, -2), (0, -1), (0, 0), (0, 1), (1, -1), (1, 0),
)


def candidate_anchors(m: TownMap) -> Set[Cell]:
    """Finite set of anchor positions that yield legal placements.
    All returned anchors are guaranteed legal (overlap or edge-adjacent)."""
    if not m:
        return {(0, 0)}
    cand: Set[Cell] = set()
    for x, y in m:
        for dx, dy in _ANCHOR_OFFSETS:
            cand.add((x + dx, y + dy))
    return cand



def place_card(m: TownMap, card: Card, ax: int, ay: int, rot180: bool) -> TownMap:
    """Place card at anchor (ax,ay), mutating m in-place. Returns m."""
    for i in (0, 1):
        for j in (0, 1):
            m[(ax + i, ay + j)] = tile_at(card, i, j, rot180)
    return m


def legal_placements(m: TownMap, card: Card) -> List[Tuple[int, int, bool]]:
    """Return all legal (ax, ay, rot180) placements for card into town m.
    Note: candidate_anchors only returns legal positions, no extra check needed."""
    result = []
    for (ax, ay) in candidate_anchors(m):
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
# Solver: alpha-beta with move ordering (used for endgame)
# ============================================================================

def _remaining_cards(state: GameState) -> int:
    """Total cards still to be placed (circle + free queues + drafted)."""
    n = len(state.circle) + len(state.free[0]) + len(state.free[1])
    if state.drafted >= 0:
        n += 1
    return n


def _order_actions(state: GameState, actions: list) -> list:
    """Cheap move ordering for alpha-beta inner nodes.
    Draft: prefer low offsets (skip fewer cards).
    Place: prefer overlapping placements (overlap first, then adjacency)."""
    if not actions:
        return actions
    if isinstance(actions[0], DraftAction):
        return actions  # already sorted by offset (0, 1, 2, ...)

    # Placement actions: prefer overlap (more compact towns score better)
    p = state.player
    m = state.towns[p]
    if not m:
        return actions
    m_contains = m.__contains__

    def place_key(act):
        ax, ay = act[0], act[1]
        # Count overlapping cells without creating a set
        return -(m_contains((ax, ay)) + m_contains((ax+1, ay)) +
                 m_contains((ax, ay+1)) + m_contains((ax+1, ay+1)))

    return sorted(actions, key=place_key)


class AlphaBetaSolver:
    """Alpha-beta solver with move ordering. Best for endgame positions.
    No transposition table: TT hit rate is <0.2% for this game
    (placements create unique states), so freeze_key overhead isn't worth it."""

    def __init__(
        self,
        bonus_names: Tuple[str, str, str],
        time_limit: float = 2.0,
        max_depth: int = 200,
    ):
        self.bonus_names = bonus_names
        self.time_limit = time_limit
        self.max_depth = max_depth
        self.nodes = 0
        self.deadline = 0.0
        self.depth_reached = 0

    def heuristic(self, state: GameState) -> int:
        return utility(state.towns[0], state.towns[1], self.bonus_names)

    def solve(self, state: GameState) -> Tuple[int, Optional[object]]:
        self.deadline = time.time() + self.time_limit
        self.nodes = 0
        self.depth_reached = 0

        best_val = None
        best_act = None

        for depth in range(1, self.max_depth + 1):
            try:
                if best_val is not None:
                    # Aspiration window: search with narrow bounds first
                    window = 20
                    v, a = self._root_search(state, depth,
                                             best_val - window, best_val + window)
                    if v <= best_val - window or v >= best_val + window:
                        # Fell outside window, re-search with full bounds
                        v, a = self._root_search(state, depth)
                else:
                    v, a = self._root_search(state, depth)
                best_val, best_act = v, a
                self.depth_reached = depth
                if state.is_terminal():
                    break
            except TimeoutError:
                break

        if best_val is None:
            best_val = self.heuristic(state)

        return best_val, best_act

    def _root_search(self, state: GameState, depth: int,
                     alpha: int = -999999, beta: int = 999999) -> Tuple[int, object]:
        actions = get_actions(state)
        if not actions:
            return self.heuristic(state), None

        p = state.player
        actions = _order_actions(state, actions)

        best_act = actions[0]
        best_val = -999999 if p == 0 else 999999

        for a in actions:
            v = self._alphabeta(apply_action(state, a), depth - 1, alpha, beta)
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
        if self.nodes % 5000 == 0 and time.time() >= self.deadline:
            raise TimeoutError

        state.normalize()
        if state.is_terminal():
            return utility(state.towns[0], state.towns[1], self.bonus_names)
        if depth <= 0:
            return self.heuristic(state)

        p = state.player
        actions = _order_actions(state, get_actions(state))

        if p == 0:
            best = -999999
            for a in actions:
                v = self._alphabeta(apply_action(state, a), depth - 1, alpha, beta)
                if v > best:
                    best = v
                if best > alpha:
                    alpha = best
                if alpha >= beta:
                    break
        else:
            best = 999999
            for a in actions:
                v = self._alphabeta(apply_action(state, a), depth - 1, alpha, beta)
                if v < best:
                    best = v
                if best < beta:
                    beta = best
                if alpha >= beta:
                    break

        return best


# ============================================================================
# Solver: MCTS (Monte Carlo Tree Search)
# ============================================================================

class MCTSNode:
    __slots__ = ("state", "action", "parent", "children",
                 "visits", "total_value", "untried_actions")

    def __init__(self, state: GameState, action=None, parent=None):
        self.state = state
        self.action = action  # action that led here from parent
        self.parent: Optional[MCTSNode] = parent
        self.children: List[MCTSNode] = []
        self.visits = 0
        self.total_value = 0.0
        self.untried_actions: Optional[list] = None

    def is_fully_expanded(self) -> bool:
        if self.untried_actions is None:
            return False  # not yet initialized by MCTSSolver._init_actions
        if not self.untried_actions:
            return True
        # Progressive widening: limit children to ~sqrt(visits)
        max_children = max(2, int(math.sqrt(self.visits + 1)))
        return len(self.children) >= max_children

    def best_child(self, c: float = 1.41) -> MCTSNode:
        """UCB1 selection."""
        log_parent = math.log(self.visits)
        best_score = -999999.0
        best = self.children[0]
        # P1 (player 0) maximizes, P2 (player 1) minimizes
        sign = 1.0 if self.state.player == 0 else -1.0
        for child in self.children:
            exploit = sign * (child.total_value / child.visits)
            explore = c * math.sqrt(log_parent / child.visits)
            score = exploit + explore
            if score > best_score:
                best_score = score
                best = child
        return best

    def most_visited_child(self) -> MCTSNode:
        best = self.children[0]
        for child in self.children[1:]:
            if child.visits > best.visits:
                best = child
        return best


class MCTSSolver:
    """MCTS solver with UCT.
    Uses greedy rollouts by default for higher-quality value estimates.
    Falls back to alpha-beta for endgame positions."""

    def __init__(
        self,
        bonus_names: Tuple[str, str, str],
        time_limit: float = 2.0,
        endgame_cards: int = 5,
        rollout_rng: Optional[random_module.Random] = None,
        rollout_policy: str = "greedy",  # "greedy", "random", or "none" (leaf eval)
    ):
        self.bonus_names = bonus_names
        self.time_limit = time_limit
        self.endgame_cards = endgame_cards
        self.rng = rollout_rng or random_module.Random()
        self.rollouts = 0
        self.rollout_policy = rollout_policy

    def _init_actions(self, node: MCTSNode) -> None:
        """Initialize and heuristic-sort untried actions for a node."""
        actions = get_actions(node.state)
        state = node.state
        if actions and isinstance(actions[0], DraftAction):
            # Draft actions: already in offset order (low=skip nothing).
            # Prefer low offsets (give fewer free cards to opponent).
            pass  # keep natural order: offset 0, 1, 2, ...
        elif actions and len(actions) > 1:
            # Placement actions: sort by overlap count (more overlap = more compact)
            p = state.player
            occupied = set(state.towns[p].keys())
            if occupied:
                def place_key(act):
                    ax, ay, rot = act
                    overlap = 0
                    for cx, cy in ((ax, ay), (ax+1, ay), (ax, ay+1), (ax+1, ay+1)):
                        if (cx, cy) in occupied:
                            overlap += 1
                    return -overlap
                actions.sort(key=place_key)
        node.untried_actions = actions

    def solve(self, state: GameState) -> Tuple[int, Optional[object]]:
        """Run MCTS. Returns (estimated value, best action)."""
        state.normalize()
        if state.is_terminal():
            return utility(state.towns[0], state.towns[1], self.bonus_names), None

        # If few enough cards remain, use exact alpha-beta
        rem = _remaining_cards(state)
        if rem <= self.endgame_cards:
            ab = AlphaBetaSolver(self.bonus_names, time_limit=self.time_limit)
            return ab.solve(state)

        root = MCTSNode(state)
        self._init_actions(root)
        self.rollouts = 0
        deadline = time.time() + self.time_limit

        while time.time() < deadline:
            node = self._select(root)
            if not node.state.is_terminal():
                node = self._expand(node)
            if self.rollout_policy == "greedy":
                value = self._greedy_rollout(node.state)
            elif self.rollout_policy == "random":
                value = self._random_rollout(node.state)
            else:
                value = float(utility(
                    node.state.towns[0], node.state.towns[1], self.bonus_names))
            self._backprop(node, value)
            self.rollouts += 1

        if not root.children:
            return utility(state.towns[0], state.towns[1], self.bonus_names), None

        best = root.most_visited_child()
        avg_value = best.total_value / best.visits if best.visits > 0 else 0
        return int(round(avg_value)), best.action

    def _select(self, node: MCTSNode) -> MCTSNode:
        while not node.state.is_terminal():
            if node.untried_actions is None:
                self._init_actions(node)
            if not node.is_fully_expanded():
                return node
            node = node.best_child()
        return node

    def _expand(self, node: MCTSNode) -> MCTSNode:
        if node.untried_actions is None:
            self._init_actions(node)
        if not node.untried_actions:
            return node
        action = node.untried_actions.pop(0)  # pop from front (best heuristic first)
        child_state = apply_action(node.state, action)
        child = MCTSNode(child_state, action=action, parent=node)
        node.children.append(child)
        return child

    def _greedy_rollout(self, state: GameState) -> float:
        """Greedy rollout: use greedy placements, weighted-random drafts.
        Much higher quality than random rollouts while still fast enough."""
        circle = list(state.circle)
        towns_0 = dict(state.towns[0])
        towns_1 = dict(state.towns[1])
        free_0 = list(state.free[0])
        free_1 = list(state.free[1])
        player = state.player
        phase = int(state.phase)
        drafted = state.drafted
        bonus_names = state.bonus_names
        rng = self.rng

        PH_FREE = 0
        PH_DRAFT = 1
        PH_PLACE = 2

        free = [free_0, free_1]
        towns = [towns_0, towns_1]

        if phase == PH_FREE and not free[player]:
            if circle:
                phase = PH_DRAFT

        def _greedy_place(m, card_id):
            """Pick the placement using a fast heuristic.
            Uses overlap + terrain matching rather than full terrain_score
            to keep rollouts fast while being much better than random."""
            card = CARDS[card_id]
            quads = card.quads
            if not m:
                m[(0, 0)] = quads[0]; m[(1, 0)] = quads[1]
                m[(0, 1)] = quads[2]; m[(1, 1)] = quads[3]
                return
            # Fast heuristic: overlap cells matching terrain = +2,
            # overlap any = +1, adjacent (no overlap) = 0.
            # This favors compact towns and terrain grouping.
            anchors = candidate_anchors(m)
            best_val = -999999
            best_ax = best_ay = 0
            best_rot = False
            for ax, ay in anchors:
                for rot_idx in (0, 1):
                    if rot_idx:
                        q = (quads[3], quads[2], quads[1], quads[0])
                    else:
                        q = quads
                    val = 0
                    for idx, (cx, cy) in enumerate((
                        (ax, ay), (ax+1, ay), (ax, ay+1), (ax+1, ay+1)
                    )):
                        existing = m.get((cx, cy))
                        if existing is not None:
                            val += 1  # overlap
                            if existing[0] == q[idx][0]:
                                val += 2  # terrain match bonus
                        else:
                            # Check N4 adjacency for terrain grouping
                            new_terr = q[idx][0]
                            for nx, ny in ((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)):
                                nb = m.get((nx, ny))
                                if nb is not None and nb[0] == new_terr:
                                    val += 1
                                    break
                    if val > best_val:
                        best_val = val
                        best_ax, best_ay, best_rot = ax, ay, bool(rot_idx)
            if best_rot:
                m[(best_ax, best_ay)] = quads[3]; m[(best_ax+1, best_ay)] = quads[2]
                m[(best_ax, best_ay+1)] = quads[1]; m[(best_ax+1, best_ay+1)] = quads[0]
            else:
                m[(best_ax, best_ay)] = quads[0]; m[(best_ax+1, best_ay)] = quads[1]
                m[(best_ax, best_ay+1)] = quads[2]; m[(best_ax+1, best_ay+1)] = quads[3]

        for _ in range(200):
            if not circle and not free_0 and not free_1 and drafted == -1:
                break

            p = player
            m = towns[p]

            if phase == PH_FREE:
                if not free[p]:
                    break
                card_id = free[p].pop(0)
                _greedy_place(m, card_id)
                if not free[p]:
                    if circle:
                        phase = PH_DRAFT

            elif phase == PH_DRAFT:
                n = len(circle)
                # Weighted random: bias toward low offsets (skip fewer cards)
                # Weight = 1/(offset+1), so offset 0 is most likely
                weights = [1.0 / (i + 1) for i in range(n)]
                total_w = sum(weights)
                r = rng.random() * total_w
                offset = 0
                acc = 0.0
                for i, w in enumerate(weights):
                    acc += w
                    if r <= acc:
                        offset = i
                        break
                chosen = circle[offset]
                if offset > 0:
                    free[1 - p].extend(circle[:offset])
                del circle[:offset + 1]
                drafted = chosen
                phase = PH_PLACE

            elif phase == PH_PLACE:
                _greedy_place(m, drafted)
                drafted = -1
                player = 1 - p
                phase = PH_FREE
                if not free[player]:
                    if circle:
                        phase = PH_DRAFT

        return float(utility(towns_0, towns_1, bonus_names))

    def _random_rollout(self, state: GameState) -> float:
        """Fast random playout to terminal state.
        Inlines state transitions and samples placements without full
        enumeration, avoiding apply_action copy overhead and candidate_anchors."""
        circle = list(state.circle)
        towns_0 = dict(state.towns[0])
        towns_1 = dict(state.towns[1])
        free_0 = list(state.free[0])
        free_1 = list(state.free[1])
        player = state.player
        phase = int(state.phase)
        drafted = state.drafted
        bonus_names = state.bonus_names
        rng = self.rng

        PH_FREE = 0
        PH_DRAFT = 1
        PH_PLACE = 2

        free = [free_0, free_1]
        towns = [towns_0, towns_1]

        if phase == PH_FREE and not free[player]:
            if circle:
                phase = PH_DRAFT

        for _ in range(200):
            if not circle and not free_0 and not free_1 and drafted == -1:
                break

            p = player
            m = towns[p]

            if phase == PH_FREE:
                if not free[p]:
                    break
                card_id = free[p].pop(0)
                quads = CARDS[card_id].quads
                if not m:
                    ax, ay = 0, 0
                else:
                    keys = list(m)
                    x, y = keys[rng.randrange(len(keys))]
                    dx, dy = _ANCHOR_OFFSETS[rng.randrange(12)]
                    ax, ay = x + dx, y + dy
                if rng.randrange(2):
                    m[(ax, ay)] = quads[3]; m[(ax+1, ay)] = quads[2]
                    m[(ax, ay+1)] = quads[1]; m[(ax+1, ay+1)] = quads[0]
                else:
                    m[(ax, ay)] = quads[0]; m[(ax+1, ay)] = quads[1]
                    m[(ax, ay+1)] = quads[2]; m[(ax+1, ay+1)] = quads[3]
                if not free[p]:
                    if circle:
                        phase = PH_DRAFT

            elif phase == PH_DRAFT:
                n = len(circle)
                offset = rng.randrange(n)
                chosen = circle[offset]
                if offset > 0:
                    free[1 - p].extend(circle[:offset])
                del circle[:offset + 1]
                drafted = chosen
                phase = PH_PLACE

            elif phase == PH_PLACE:
                quads = CARDS[drafted].quads
                if not m:
                    ax, ay = 0, 0
                else:
                    keys = list(m)
                    x, y = keys[rng.randrange(len(keys))]
                    dx, dy = _ANCHOR_OFFSETS[rng.randrange(12)]
                    ax, ay = x + dx, y + dy
                if rng.randrange(2):
                    m[(ax, ay)] = quads[3]; m[(ax+1, ay)] = quads[2]
                    m[(ax, ay+1)] = quads[1]; m[(ax+1, ay+1)] = quads[0]
                else:
                    m[(ax, ay)] = quads[0]; m[(ax+1, ay)] = quads[1]
                    m[(ax, ay+1)] = quads[2]; m[(ax+1, ay+1)] = quads[3]
                drafted = -1
                player = 1 - p
                phase = PH_FREE
                if not free[player]:
                    if circle:
                        phase = PH_DRAFT

        return float(utility(towns_0, towns_1, bonus_names))

    def _backprop(self, node: MCTSNode, value: float) -> None:
        while node is not None:
            node.visits += 1
            node.total_value += value
            node = node.parent


# ============================================================================
# Agent: picks actions using a solver
# ============================================================================

def pick_action_random(state: GameState, rng: random_module.Random) -> object:
    """Random agent."""
    actions = get_actions(state)
    return rng.choice(actions)


def pick_action_greedy(
    state: GameState,
    bonus_names: Tuple[str, str, str],
) -> object:
    """Greedy 1-ply agent: pick action maximizing immediate utility.
    For draft decisions, simulates greedy placements through to next
    draft to compare cards with their placements resolved.
    For placements, uses mutate-evaluate-undo to avoid state copies."""
    actions = get_actions(state)
    sign = 1 if state.player == 0 else -1

    if state.phase == Phase.DRAFT:
        # Draft: need full state copy to simulate placements
        best_val = None
        best_act = actions[0]
        for a in actions:
            child = apply_action(state, a)
            child = _advance_greedy(child, bonus_names)
            v = sign * utility(child.towns[0], child.towns[1], bonus_names)
            if best_val is None or v > best_val:
                best_val = v
                best_act = a
        return best_act

    # Placement: mutate-evaluate-undo avoids ~80 state copies per decision
    p = state.player
    m = state.towns[p]
    card_id = state.free[p][0] if state.phase == Phase.PLACE_FREE else state.drafted
    card = CARDS[card_id]
    t0, t1, t2, t3 = card.quads

    best_val = None
    best_act = actions[0]
    towns_0, towns_1 = state.towns[0], state.towns[1]

    for ax, ay, rot180 in actions:
        # Save existing cells
        k0 = (ax, ay); k1 = (ax+1, ay); k2 = (ax, ay+1); k3 = (ax+1, ay+1)
        s0 = m.get(k0); s1 = m.get(k1); s2 = m.get(k2); s3 = m.get(k3)

        # Place card (mutate in-place)
        if rot180:
            m[k0] = t3; m[k1] = t2; m[k2] = t1; m[k3] = t0
        else:
            m[k0] = t0; m[k1] = t1; m[k2] = t2; m[k3] = t3

        # Evaluate
        v = sign * utility(towns_0, towns_1, bonus_names)

        # Restore
        if s0 is None: del m[k0]
        else: m[k0] = s0
        if s1 is None: del m[k1]
        else: m[k1] = s1
        if s2 is None: del m[k2]
        else: m[k2] = s2
        if s3 is None: del m[k3]
        else: m[k3] = s3

        if best_val is None or v > best_val:
            best_val = v
            best_act = (ax, ay, rot180)

    return best_act


def _advance_greedy(state: GameState, bonus_names: Tuple[str, str, str]) -> GameState:
    """Apply greedy placements until the next draft decision or terminal."""
    while not state.is_terminal():
        if state.phase == Phase.DRAFT:
            return state
        action = pick_action_greedy(state, bonus_names)
        state = apply_action(state, action)
    return state


def pick_action_lookahead(
    state: GameState,
    bonus_names: Tuple[str, str, str],
    endgame_cards: int = 4,
    endgame_time: float = 2.0,
    draft_depth: int = -1,  # -1 = auto (2 when <=8 cards, 1 otherwise)
) -> object:
    """Lookahead agent: greedy for placements, minimax for drafts.
    For drafts: N-ply minimax over draft decisions (greedy placements between).
    For placements: standard greedy.
    Falls back to exact alpha-beta when few enough cards remain."""
    rem = _remaining_cards(state)
    if rem <= endgame_cards:
        ab = AlphaBetaSolver(bonus_names, time_limit=endgame_time)
        _, action = ab.solve(state)
        if action is not None:
            return action

    if state.phase != Phase.DRAFT:
        return pick_action_greedy(state, bonus_names)

    # Auto-select draft depth: deeper when fewer cards remain
    # Alpha-beta pruning at root + move ordering make deeper search feasible
    if draft_depth < 0:
        n_circle = len(state.circle)
        if n_circle <= 8:
            draft_depth = 3
        elif n_circle <= 10:
            draft_depth = 2
        else:
            draft_depth = 1

    p = state.player
    sign = 1 if p == 0 else -1

    # Pre-sort draft actions by greedy evaluation for better pruning
    draft_actions = get_actions(state)
    scored = []
    for da in draft_actions:
        child = apply_action(state, da)
        child = _advance_greedy(child, bonus_names)
        v = sign * utility(child.towns[0], child.towns[1], bonus_names)
        scored.append((v, da, child))
    scored.sort(reverse=True)  # best first for current player

    # Alpha-beta at root: prune draft actions that can't improve on best
    best_act = scored[0][1]
    alpha, beta = -999999, 999999
    if p == 0:
        for _, draft_act, child in scored:
            v = _draft_minimax(child, bonus_names, draft_depth - 1, alpha, beta)
            if v > alpha:
                alpha = v
                best_act = draft_act
            if alpha >= beta:
                break
    else:
        for _, draft_act, child in scored:
            v = _draft_minimax(child, bonus_names, draft_depth - 1, alpha, beta)
            if v < beta:
                beta = v
                best_act = draft_act
            if alpha >= beta:
                break

    return best_act


def _draft_minimax(
    state: GameState,
    bonus_names: Tuple[str, str, str],
    depth: int,
    alpha: int = -999999,
    beta: int = 999999,
) -> int:
    """Alpha-beta minimax over draft decisions with greedy placements between.
    Returns utility from P1's perspective."""
    if state.is_terminal() or depth <= 0 or state.phase != Phase.DRAFT:
        return utility(state.towns[0], state.towns[1], bonus_names)

    p = state.player
    draft_actions = get_actions(state)

    # Pre-sort by greedy evaluation for better pruning
    sign = 1 if p == 0 else -1
    scored = []
    for da in draft_actions:
        child = apply_action(state, da)
        child = _advance_greedy(child, bonus_names)
        v = sign * utility(child.towns[0], child.towns[1], bonus_names)
        scored.append((v, da, child))
    scored.sort(reverse=True)  # best first for current player

    if p == 0:
        best = -999999
        for _, _, child in scored:
            v = _draft_minimax(child, bonus_names, depth - 1, alpha, beta)
            if v > best:
                best = v
            alpha = max(alpha, best)
            if alpha >= beta:
                break
    else:
        best = 999999
        for _, _, child in scored:
            v = _draft_minimax(child, bonus_names, depth - 1, alpha, beta)
            if v < best:
                best = v
            beta = min(beta, best)
            if alpha >= beta:
                break

    return best


def pick_action_mcts(
    state: GameState,
    bonus_names: Tuple[str, str, str],
    time_limit: float = 0.5,
    rng: Optional[random_module.Random] = None,
    rollout_policy: str = "greedy",
) -> object:
    """MCTS agent."""
    solver = MCTSSolver(
        bonus_names, time_limit=time_limit,
        rollout_rng=rng, rollout_policy=rollout_policy,
    )
    _, action = solver.solve(state)
    return action


# ============================================================================
# Play a complete game
# ============================================================================

def play_game(
    circle: List[int],
    bonus_names: Tuple[str, str, str],
    start_index: int,
    agent_p1: str = "mcts",
    agent_p2: str = "mcts",
    time_limit: float = 0.5,
    rng: Optional[random_module.Random] = None,
    verbose: bool = False,
) -> Tuple[int, int, int]:
    """Play a complete game. Returns (p1_score, p2_score, utility)."""
    if rng is None:
        rng = random_module.Random()
    state = make_initial_state(circle, bonus_names, start_index)
    agents = [agent_p1, agent_p2]
    turn_num = 0

    while not state.is_terminal():
        p = state.player
        agent = agents[p]

        if agent == "random":
            action = pick_action_random(state, rng)
        elif agent == "greedy":
            action = pick_action_greedy(state, bonus_names)
        elif agent == "lookahead":
            action = pick_action_lookahead(state, bonus_names)
        elif agent == "mcts":
            action = pick_action_mcts(state, bonus_names, time_limit, rng)
        else:
            action = pick_action_random(state, rng)

        if verbose and state.phase == Phase.DRAFT:
            turn_num += 1
            act: DraftAction = action
            skipped = act.offset
            card = state.circle[act.offset]
            player_name = "P1" if p == 0 else "P2"
            print(f"  Turn {turn_num:2d} ({player_name}): "
                  f"draft card {card:2d} (skip {skipped}), "
                  f"circle has {len(state.circle)} cards")

        state = apply_action(state, action)

    s1, s2 = compute_scores(state.towns[0], state.towns[1], bonus_names)
    u = s1 - s2

    if verbose:
        print()
        print_town(state.towns[0], "P1 Town")
        print_town(state.towns[1], "P2 Town")
        t1 = terrain_score(state.towns[0])
        t2 = terrain_score(state.towns[1])
        print(f"Terrain:  P1={t1}  P2={t2}")
        print(f"Total:    P1={s1}  P2={s2}")
        print(f"Utility:  {u:+d}  ({'P1 wins' if u > 0 else 'P2 wins' if u < 0 else 'Tie'})")

    return s1, s2, u


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
        solver = MCTSSolver(bonus_names, time_limit=time_per_start)
        v, _ = solver.solve(s0)
        card_name = circle[k]
        print(f"  Start {k:2d} (card {card_name:2d}): "
              f"val={v:+d}  ({solver.rollouts} rollouts)")

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
    rng = random_module.Random(seed)
    card_ids = list(range(18))
    rng.shuffle(card_ids)
    bonus_ids = card_ids[:3]
    circle_ids = card_ids[3:]
    bonus_names = tuple(CARD_BONUS_MAP[cid] for cid in bonus_ids)
    return bonus_names, circle_ids  # type: ignore


# ============================================================================
# CLI commands
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


def cmd_play(seed: int, time_limit: float) -> None:
    bonus_names, circle = generate_deal(seed)
    print(f"Deal (seed={seed}):")
    print(f"  Bonuses: {', '.join(bonus_names)}")
    print(f"  Circle ({len(circle)} cards): {circle}")
    print()

    print("Lookahead (P1) vs Lookahead (P2), starting at index 0:")
    print()
    play_game(
        circle, bonus_names, start_index=0,
        agent_p1="lookahead", agent_p2="lookahead",
        time_limit=time_limit, verbose=True,
    )


def cmd_benchmark(n_games: int, time_limit: float, seed: int) -> None:
    print(f"Benchmark: {n_games} games, {time_limit:.1f}s/move")
    print()

    results = {
        "rand_v_rand": [],
        "greedy_v_rand": [],
        "look_v_rand": [],
        "look_v_greedy": [],
    }

    for i in range(n_games):
        game_seed = seed + i
        bonus_names, circle = generate_deal(game_seed)

        # Random vs Random
        _, _, u = play_game(
            circle, bonus_names, start_index=0,
            agent_p1="random", agent_p2="random",
            rng=random_module.Random(game_seed + 10000),
        )
        results["rand_v_rand"].append(u)

        # Greedy vs Random
        _, _, u = play_game(
            circle, bonus_names, start_index=0,
            agent_p1="greedy", agent_p2="random",
            rng=random_module.Random(game_seed + 20000),
        )
        results["greedy_v_rand"].append(u)

        # Lookahead vs Random
        _, _, u_lr = play_game(
            circle, bonus_names, start_index=0,
            agent_p1="lookahead", agent_p2="random",
            rng=random_module.Random(game_seed),
        )
        results["look_v_rand"].append(u_lr)

        # Lookahead vs Greedy
        _, _, u_lg = play_game(
            circle, bonus_names, start_index=0,
            agent_p1="lookahead", agent_p2="greedy",
            rng=random_module.Random(game_seed + 30000),
        )
        results["look_v_greedy"].append(u_lg)

        def avg(vals):
            return sum(vals) / len(vals) if vals else 0

        print(f"  Game {i+1:3d}/{n_games}: "
              f"LvG={u_lg:+d}  "
              f"(avg LvG={avg(results['look_v_greedy']):+.1f})")

    print()
    print("=== Results ===")

    for label, key in [
        ("Random vs Random", "rand_v_rand"),
        ("Greedy vs Random", "greedy_v_rand"),
        ("Lookahead vs Random", "look_v_rand"),
        ("Lookahead vs Greedy", "look_v_greedy"),
    ]:
        vals = results[key]
        avg_v = sum(vals) / len(vals)
        wins = sum(1 for v in vals if v > 0)
        losses = sum(1 for v in vals if v < 0)
        ties = sum(1 for v in vals if v == 0)
        print(f"  {label:22s}: avg={avg_v:+.1f}  "
              f"W/L/T={wins}/{losses}/{ties}")


def cmd_endgame(seed: int) -> None:
    """Demonstrate exact endgame solving."""
    print("=== Endgame Exact Solving Demo ===\n")

    for n_cards in (1, 2, 3):
        # Try different seeds to find a clean endgame (at a draft decision)
        best_state = None
        best_bn = None
        for trial in range(20):
            bonus_names, circle = generate_deal(seed + trial)
            state = make_initial_state(circle, bonus_names, 0)
            rng = random_module.Random(seed + trial + 1000)
            # Play forward until n_cards remain
            while _remaining_cards(state) > n_cards and not state.is_terminal():
                action = pick_action_random(state, rng)
                state = apply_action(state, action)
            rem = _remaining_cards(state)
            if not state.is_terminal() and rem == n_cards:
                # Prefer draft-phase positions (cleaner to display)
                if best_state is None or state.phase == Phase.DRAFT:
                    best_state = state
                    best_bn = bonus_names
                    if state.phase == Phase.DRAFT:
                        break

        if best_state is None:
            print(f"  {n_cards}-card endgame: skipped (no suitable position)")
            continue

        state = best_state
        bonus_names = best_bn
        rem = _remaining_cards(state)
        free_count = len(state.free[0]) + len(state.free[1])
        circle_count = len(state.circle)
        drafted = 1 if state.drafted >= 0 else 0

        print(f"  {rem}-card endgame (circle={circle_count} free={free_count} "
              f"drafted={drafted}):")
        print(f"    Player to move: P{state.player + 1}")
        print(f"    Phase: {state.phase.name}")
        print(f"    Town sizes: P1={len(state.towns[0])} P2={len(state.towns[1])}")

        ab = AlphaBetaSolver(bonus_names, time_limit=60.0, max_depth=200)
        t0 = time.time()
        val, best_act = ab.solve(state)
        elapsed = time.time() - t0

        solved = ab.depth_reached >= 100 or elapsed < ab.time_limit * 0.9
        status = "EXACT" if solved else f"depth-{ab.depth_reached}"
        print(f"    Value: {val:+d} ({status})")
        print(f"    Best action: {best_act}")
        print(f"    Nodes: {ab.nodes:,}")
        print(f"    Time: {elapsed:.3f}s ({ab.nodes / max(elapsed, 0.001):,.0f} nodes/s)")
        print()


def cmd_analyze(n_games: int, seed: int) -> None:
    """Analyze game statistics across many games for the paper."""
    print(f"=== Game Analysis ({n_games} games, Lookahead vs Lookahead) ===\n")

    # Accumulators
    terrain_totals = [0, 0]  # P1, P2 terrain score sums
    bonus_totals: Dict[str, List[int]] = {}  # bonus_name -> [P1 total, P2 total, game_count]
    skip_counts = []  # how many cards each player skips per draft
    utilities = []
    town_sizes = [[], []]  # final town sizes
    game_lengths = []  # number of draft decisions per game
    card_draft_counts: Dict[int, int] = {i: 0 for i in range(18)}  # how often each card is drafted

    for i in range(n_games):
        game_seed = seed + i
        bonus_names, circle = generate_deal(game_seed)
        state = make_initial_state(circle, bonus_names, 0)

        drafts = 0
        while not state.is_terminal():
            p = state.player
            if state.phase == Phase.DRAFT:
                action = pick_action_lookahead(state, bonus_names)
                drafts += 1
                if action.offset > 0:
                    skip_counts.append(action.offset)
                card_id = state.circle[action.offset]
                card_draft_counts[card_id] = card_draft_counts.get(card_id, 0) + 1
            else:
                action = pick_action_greedy(state, bonus_names)
            state = apply_action(state, action)

        game_lengths.append(drafts)
        s1, s2 = compute_scores(state.towns[0], state.towns[1], bonus_names)
        u = s1 - s2
        utilities.append(u)

        ts1 = terrain_score(state.towns[0])
        ts2 = terrain_score(state.towns[1])
        terrain_totals[0] += ts1
        terrain_totals[1] += ts2

        town_sizes[0].append(len(state.towns[0]))
        town_sizes[1].append(len(state.towns[1]))

        local_fns, interactive_fns = _get_bonus_fns(bonus_names)
        for name in bonus_names:
            if name not in bonus_totals:
                bonus_totals[name] = [0, 0, 0]
            bonus_totals[name][2] += 1
            if name in LOCAL_BONUSES:
                fn = LOCAL_BONUSES[name]
                bonus_totals[name][0] += fn(state.towns[0])
                bonus_totals[name][1] += fn(state.towns[1])
            elif name in INTERACTIVE_BONUSES:
                fn = INTERACTIVE_BONUSES[name]
                d1, d2 = fn(state.towns[0], state.towns[1])
                bonus_totals[name][0] += d1
                bonus_totals[name][1] += d2

        if (i + 1) % 10 == 0:
            avg_u = sum(utilities) / len(utilities)
            wins = sum(1 for v in utilities if v > 0)
            print(f"  {i+1}/{n_games}: P1 wins {wins}/{i+1} ({100*wins/(i+1):.0f}%), avg utility={avg_u:+.1f}")

    n = len(utilities)
    print()
    print("=== Summary ===")
    print()

    # Outcome distribution
    wins_p1 = sum(1 for v in utilities if v > 0)
    wins_p2 = sum(1 for v in utilities if v < 0)
    ties = sum(1 for v in utilities if v == 0)
    avg_u = sum(utilities) / n
    print(f"Outcomes: P1 wins {wins_p1}/{n} ({100*wins_p1/n:.0f}%), "
          f"P2 wins {wins_p2}/{n} ({100*wins_p2/n:.0f}%), "
          f"Ties {ties}/{n}")
    print(f"Average utility: {avg_u:+.1f}")
    print(f"Utility range: [{min(utilities):+d}, {max(utilities):+d}]")
    print()

    # Score composition
    avg_ts = [t / n for t in terrain_totals]
    print(f"Average terrain score: P1={avg_ts[0]:.1f}  P2={avg_ts[1]:.1f}")
    print()

    # Bonus analysis
    print("Bonus breakdown (avg per game when active):")
    bonus_ranked = []
    for name in sorted(bonus_totals.keys()):
        p1_total, p2_total, count = bonus_totals[name]
        avg1 = p1_total / count if count > 0 else 0
        avg2 = p2_total / count if count > 0 else 0
        avg_combined = (p1_total + p2_total) / count if count > 0 else 0
        print(f"  {name:22s}: P1={avg1:+5.1f}  P2={avg2:+5.1f}  "
              f"combined={avg_combined:+5.1f}  (in {count} games)")
        bonus_ranked.append((avg_combined, name))
    print()

    # Bonus power ranking
    bonus_ranked.sort(reverse=True)
    print("Bonus power ranking (highest avg combined score):")
    for rank, (avg_val, name) in enumerate(bonus_ranked, 1):
        bar = "#" * max(0, int(avg_val / 2))
        print(f"  {rank:2d}. {name:22s}  {avg_val:+5.1f}  {bar}")
    print()

    # Town sizes
    avg_town = [sum(s) / n for s in town_sizes]
    print(f"Average town size: P1={avg_town[0]:.1f}  P2={avg_town[1]:.1f}")
    print()

    # Draft statistics
    avg_drafts = sum(game_lengths) / n
    avg_skip = sum(skip_counts) / len(skip_counts) if skip_counts else 0
    skip_rate = len(skip_counts) / sum(game_lengths) if game_lengths else 0
    print(f"Drafting: avg {avg_drafts:.1f} drafts/game, "
          f"{100*skip_rate:.0f}% involve skips, avg skip={avg_skip:.1f} cards")
    print()

    # Card popularity
    print("Most drafted cards:")
    sorted_cards = sorted(card_draft_counts.items(), key=lambda x: -x[1])
    for cid, count in sorted_cards[:6]:
        bonus = CARD_BONUS_MAP.get(cid, "???")
        print(f"  Card {cid:2d} ({bonus:22s}): drafted {count} times")
    print()
    print("Least drafted cards:")
    for cid, count in sorted_cards[-3:]:
        bonus = CARD_BONUS_MAP.get(cid, "???")
        print(f"  Card {cid:2d} ({bonus:22s}): drafted {count} times")


def _pick_action_fast(state: GameState, bonus_names) -> object:
    """Fast greedy agent for bulk analysis. No draft simulation."""
    actions = get_actions(state)
    if not actions:
        return None
    sign = 1 if state.player == 0 else -1

    if state.phase == Phase.DRAFT:
        # Simple heuristic: prefer low offsets (skip fewer cards)
        return actions[0]

    # Placement: mutate-evaluate-undo
    p = state.player
    m = state.towns[p]
    card_id = state.free[p][0] if state.phase == Phase.PLACE_FREE else state.drafted
    card = CARDS[card_id]
    t0, t1, t2, t3 = card.quads

    best_val = None
    best_act = actions[0]
    towns_0, towns_1 = state.towns[0], state.towns[1]

    for ax, ay, rot180 in actions:
        k0 = (ax, ay); k1 = (ax+1, ay); k2 = (ax, ay+1); k3 = (ax+1, ay+1)
        s0 = m.get(k0); s1_v = m.get(k1); s2_v = m.get(k2); s3 = m.get(k3)
        if rot180:
            m[k0] = t3; m[k1] = t2; m[k2] = t1; m[k3] = t0
        else:
            m[k0] = t0; m[k1] = t1; m[k2] = t2; m[k3] = t3
        v = sign * utility(towns_0, towns_1, bonus_names)
        if s0 is None: del m[k0]
        else: m[k0] = s0
        if s1_v is None: del m[k1]
        else: m[k1] = s1_v
        if s2_v is None: del m[k2]
        else: m[k2] = s2_v
        if s3 is None: del m[k3]
        else: m[k3] = s3
        if best_val is None or v > best_val:
            best_val = v
            best_act = (ax, ay, rot180)
    return best_act


def cmd_openings(n_games: int, seed: int) -> None:
    """Analyze starting position advantage across many deals."""
    print(f"=== Starting Position Analysis ({n_games} deals) ===")
    print("  For each deal, play fast greedy at all 15 starting positions.\n")

    # Per-position stats
    position_utils = [[] for _ in range(15)]

    for i in range(n_games):
        game_seed = seed + i
        bonus_names, circle = generate_deal(game_seed)
        n = len(circle)

        pos_results = []
        for start_idx in range(n):
            state = make_initial_state(circle, bonus_names, start_idx)
            while not state.is_terminal():
                action = _pick_action_fast(state, bonus_names)
                state = apply_action(state, action)
            s1, s2 = compute_scores(state.towns[0], state.towns[1], bonus_names)
            u = s1 - s2
            position_utils[start_idx].append(u)
            pos_results.append(u)

        if (i + 1) % 10 == 0 or i == 0:
            avg_range = sum(max(position_utils[j]) - min(position_utils[j])
                           for j in range(n) if position_utils[j]) / n
            print(f"  {i+1}/{n_games}: avg position swing = {avg_range:.1f}")

    print()
    print("=== Position Analysis ===\n")

    # Overall utility by starting position
    print("Average utility by starting position (P1 - P2):")
    print("  Higher = better for P1 (worse for P2 who chose this start)")
    print()
    for idx in range(15):
        vals = position_utils[idx]
        if not vals:
            continue
        avg_u = sum(vals) / len(vals)
        p1_wins = sum(1 for v in vals if v > 0)
        bar = "#" * max(0, int((avg_u + 10) / 2))
        print(f"  Start {idx:2d}: avg={avg_u:+5.1f}  P1 wins {p1_wins}/{len(vals)}  {bar}")

    print()

    # Utility range (how much starting position matters)
    avg_utils = [sum(v)/len(v) for v in position_utils if v]
    swing = max(avg_utils) - min(avg_utils)
    best_for_p2 = min(range(15), key=lambda i: sum(position_utils[i])/len(position_utils[i]))
    worst_for_p2 = max(range(15), key=lambda i: sum(position_utils[i])/len(position_utils[i]))
    print(f"Starting position swing: {swing:.1f} utility points")
    print(f"Best start for P2 (lowest P1 utility): position {best_for_p2} "
          f"(avg {sum(position_utils[best_for_p2])/len(position_utils[best_for_p2]):+.1f})")
    print(f"Worst start for P2: position {worst_for_p2} "
          f"(avg {sum(position_utils[worst_for_p2])/len(position_utils[worst_for_p2]):+.1f})")


def cmd_solve(time_limit: float, seed: int) -> None:
    bonus_names, circle = generate_deal(seed)
    print(f"Deal (seed={seed}):")
    print(f"  Bonuses: {bonus_names}")
    print(f"  Circle:  {circle}")
    print()

    print("Finding Player 2's best starting card (MCTS)...")
    k, v = find_best_start(circle, bonus_names, time_per_start=time_limit)
    print()
    print(f"Best start index for P2: {k} (card {circle[k]})")
    print(f"Estimated utility (P1-P2): {v:+d}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Circle the Wagons solver")
    parser.add_argument("--verify-cards", action="store_true",
                        help="Print all 18 cards for visual verification")
    parser.add_argument("--play", action="store_true",
                        help="Play a complete game")
    parser.add_argument("--benchmark", action="store_true",
                        help="Benchmark agents over multiple games")
    parser.add_argument("--endgame", action="store_true",
                        help="Demo exact endgame solving")
    parser.add_argument("--analyze", action="store_true",
                        help="Detailed game statistics for the paper")
    parser.add_argument("--openings", action="store_true",
                        help="Analyze starting position advantage")
    parser.add_argument("-n", type=int, default=20,
                        help="Number of benchmark/analysis games (default: 20)")
    parser.add_argument("--time-limit", type=float, default=1.0,
                        help="Seconds per move/position (default: 1.0)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    args = parser.parse_args()

    if args.verify_cards:
        cmd_verify_cards()
    elif args.play:
        cmd_play(args.seed, args.time_limit)
    elif args.benchmark:
        cmd_benchmark(args.n, args.time_limit, args.seed)
    elif args.endgame:
        cmd_endgame(args.seed)
    elif args.analyze:
        cmd_analyze(args.n, args.seed)
    elif args.openings:
        cmd_openings(args.n, args.seed)
    else:
        cmd_solve(args.time_limit, args.seed)


if __name__ == "__main__":
    main()
