// Circle the Wagons — Game Engine (ported from solver.py)
// Pure logic, zero DOM awareness.

// ============================================================================
// Constants
// ============================================================================

export const Terr = Object.freeze({
  Desert: 0, Forest: 1, Snow: 2, Mountains: 3, Plains: 4, Water: 5,
});

export const Icon = Object.freeze({
  Empty: 0, Beer: 1, Cow: 2, Fort: 3, Gun: 4, Mine: 5, Wagon: 6,
});

export const Phase = Object.freeze({
  PLACE_FREE: 0, DRAFT: 1, PLACE_DRAFT: 2,
});

export const TERRAINS = [0, 1, 2, 3, 4, 5];
const N4 = [[1,0],[-1,0],[0,1],[0,-1]];

export const TERR_SHORT = ["Des","For","Snw","Mtn","Pln","Wat"];
export const ICON_SHORT = ["   ","Ber","Cow","Frt","Gun","Min","Wgn"];
export const TERR_NAMES = ["Desert","Forest","Snow","Mountains","Plains","Water"];

// String-based cell keys for correct handling of negative coordinates
export function cellKey(x, y) { return `${x},${y}`; }
export function parseKey(k) {
  const p = k.indexOf(',');
  return [+k.slice(0, p), +k.slice(p + 1)];
}

// ============================================================================
// Cards
// ============================================================================

const D = 0, F = 1, S = 2, M = 3, P = 4, W = 5;
const Be = 1, Co = 2, Fo = 3, Gu = 4, Mi = 5, Wa = 6;

// quads: [BL, BR, TL, TR] each is [terr, icon]
export const CARDS = [
  { cid: 0,  quads: [[P,Mi],[F,Be],[P,Co],[P,Fo]] },
  { cid: 1,  quads: [[D,Be],[M,Wa],[M,Fo],[M,Mi]] },
  { cid: 2,  quads: [[S,Wa],[W,Gu],[W,Mi],[W,Be]] },
  { cid: 3,  quads: [[S,Fo],[W,Mi],[S,Gu],[S,Co]] },
  { cid: 4,  quads: [[D,Co],[M,Fo],[D,Wa],[D,Gu]] },
  { cid: 5,  quads: [[P,Gu],[F,Co],[F,Be],[F,Wa]] },
  { cid: 6,  quads: [[F,Mi],[W,Fo],[W,Gu],[S,Mi]] },
  { cid: 7,  quads: [[D,Be],[F,Mi],[F,Co],[P,Be]] },
  { cid: 8,  quads: [[S,Wa],[D,Be],[D,Fo],[M,Wa]] },
  { cid: 9,  quads: [[S,Fo],[D,Wa],[M,Fo],[P,Fo]] },
  { cid: 10, quads: [[D,Be],[F,Co],[P,Co],[S,Co]] },
  { cid: 11, quads: [[F,Gu],[W,Gu],[S,Gu],[D,Mi]] },
  { cid: 12, quads: [[P,Gu],[S,Wa],[S,Mi],[W,Gu]] },
  { cid: 13, quads: [[W,Fo],[M,Co],[M,Wa],[D,Fo]] },
  { cid: 14, quads: [[M,Co],[P,Gu],[P,Be],[F,Co]] },
  { cid: 15, quads: [[P,Mi],[M,Mi],[W,Mi],[M,Gu]] },
  { cid: 16, quads: [[W,Fo],[M,Wa],[D,Wa],[F,Wa]] },
  { cid: 17, quads: [[M,Be],[P,Be],[F,Co],[W,Be]] },
];

export const CARD_BONUS_MAP = [
  "BADLANDS","HAPPY COWS","THE CLEARING",
  "CIRCLE THE WAGONS","SMALLTOWN CHARM","GOLD COUNTRY",
  "PRAIRIE LIFE","COOL WATER","CLAIM JUMPERS",
  "BOOM OR BUST","WAGON TRAIN","ONE TOO MANY",
  "BOOTLEGGERS","UNDISCOVERED","FORTIFIED",
  "THE HERD","TARGET PRACTICE","RIFLES READY",
];

export const BONUS_DESCRIPTIONS = {
  "BADLANDS": "+4 per Gun between 2 Deserts (H or V)",
  "HAPPY COWS": "+2 per Cow not on/adjacent to Snow",
  "THE CLEARING": "+2 per Fort, \u22121 per Forest cell",
  "CIRCLE THE WAGONS": "+6 per cell whose 4 neighbors all have Wagon",
  "SMALLTOWN CHARM": "Fewer territories? Gain the difference",
  "GOLD COUNTRY": "+2 per Mine on/adjacent to Mountains",
  "PRAIRIE LIFE": "\u230a(#Cow + #Plains) / 2\u230b",
  "COOL WATER": "+3 per Wagon on/adj to largest Water group",
  "CLAIM JUMPERS": "+9 most Mines; \u22125 if opponent has more Guns",
  "BOOM OR BUST": "Per Mine: 0\u20132\u21925, 3\u20136\u21920, 7\u21923, 8+\u21928",
  "WAGON TRAIN": "Wagon lines: 2\u21921, 3\u21922, 4\u21924, 5\u21927, 6+\u219210",
  "ONE TOO MANY": "More Beer? Lose 1 per opponent\u2019s Beer",
  "BOOTLEGGERS": "+2 per Beer adj Wagon, \u22121 if not adj",
  "UNDISCOVERED": "+5 per empty cell fully enclosed (all 8 neighbors)",
  "FORTIFIED": "+7 per 2\u00d72 block where all 4 cells have Fort",
  "THE HERD": "+2 \u00d7 largest connected Cow group",
  "TARGET PRACTICE": "Per Beer: cells between it & closest aligned Gun",
  "RIFLES READY": "+2 per Fort adjacent to a Gun",
};

export function tileAt(card, i, j, rot180) {
  let idx = j * 2 + i;
  if (rot180) idx = 3 - idx;
  return card.quads[idx];
}

// ============================================================================
// TownMap helpers: Map<string, [terr, icon]>
// ============================================================================

export function townGet(m, x, y) { return m.get(cellKey(x, y)); }
export function townHas(m, x, y) { return m.has(cellKey(x, y)); }

function countIcon(m, ic) {
  let n = 0;
  for (const [, tile] of m) if (tile[1] === ic) n++;
  return n;
}

function countTerr(m, tt) {
  let n = 0;
  for (const [, tile] of m) if (tile[0] === tt) n++;
  return n;
}

// ============================================================================
// Connected component helpers
// ============================================================================

export function largestCC(cellSet) {
  if (cellSet.size === 0) return 0;
  const seen = new Set();
  let best = 0;
  for (const k of cellSet) {
    if (seen.has(k)) continue;
    const stack = [k];
    seen.add(k);
    let size = 0;
    while (stack.length > 0) {
      const cur = stack.pop();
      size++;
      const [x, y] = parseKey(cur);
      for (const [dx, dy] of N4) {
        const nk = cellKey(x + dx, y + dy);
        if (cellSet.has(nk) && !seen.has(nk)) {
          seen.add(nk);
          stack.push(nk);
        }
      }
    }
    if (size > best) best = size;
  }
  return best;
}

function connectedComponents(cellSet) {
  const seen = new Set();
  const comps = [];
  for (const k of cellSet) {
    if (seen.has(k)) continue;
    const stack = [k];
    seen.add(k);
    const comp = new Set();
    while (stack.length > 0) {
      const cur = stack.pop();
      comp.add(cur);
      const [x, y] = parseKey(cur);
      for (const [dx, dy] of N4) {
        const nk = cellKey(x + dx, y + dy);
        if (cellSet.has(nk) && !seen.has(nk)) {
          seen.add(nk);
          stack.push(nk);
        }
      }
    }
    comps.push(comp);
  }
  return comps;
}

// ============================================================================
// Terrain scoring
// ============================================================================

export function terrainScore(m) {
  let score = 0;
  for (const t of TERRAINS) {
    const cells = new Set();
    for (const [k, tile] of m) if (tile[0] === t) cells.add(k);
    score += largestCC(cells);
  }
  return score;
}

// ============================================================================
// Bonus scoring functions
// ============================================================================

function bonus_fortified(m) {
  let score = 0;
  for (const k of m.keys()) {
    const [x, y] = parseKey(k);
    const t00 = townGet(m, x, y);
    const t10 = townGet(m, x+1, y);
    const t01 = townGet(m, x, y+1);
    const t11 = townGet(m, x+1, y+1);
    if (t00 && t00[1] === Fo && t10 && t10[1] === Fo &&
        t01 && t01[1] === Fo && t11 && t11[1] === Fo)
      score += 7;
  }
  return score;
}

function bonus_undiscovered(m) {
  let score = 0;
  const checked = new Set();
  for (const k of m.keys()) {
    const [x, y] = parseKey(k);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        if (dx === 0 && dy === 0) continue;
        const nx = x + dx, ny = y + dy;
        const nk = cellKey(nx, ny);
        if (m.has(nk) || checked.has(nk)) continue;
        checked.add(nk);
        if (townHas(m,nx-1,ny-1) && townHas(m,nx,ny-1) && townHas(m,nx+1,ny-1) &&
            townHas(m,nx-1,ny) && townHas(m,nx+1,ny) &&
            townHas(m,nx-1,ny+1) && townHas(m,nx,ny+1) && townHas(m,nx+1,ny+1))
          score += 5;
      }
    }
  }
  return score;
}

function bonus_rifles_ready(m) {
  let score = 0;
  for (const [k, tile] of m) {
    if (tile[1] === Fo) {
      const [x, y] = parseKey(k);
      for (const [dx, dy] of N4) {
        const t = townGet(m, x+dx, y+dy);
        if (t && t[1] === Gu) { score += 2; break; }
      }
    }
  }
  return score;
}

function bonus_target_practice(m) {
  const beers = [], guns = [];
  for (const [k, tile] of m) {
    const [x, y] = parseKey(k);
    if (tile[1] === Be) beers.push([x, y]);
    if (tile[1] === Gu) guns.push([x, y]);
  }
  if (guns.length === 0) return 0;
  let score = 0;
  for (const [bx, by] of beers) {
    let bestDist = null;
    for (const [gx, gy] of guns) {
      if (bx === gx) {
        const d = Math.abs(by - gy);
        if (bestDist === null || d < bestDist) bestDist = d;
      } else if (by === gy) {
        const d = Math.abs(bx - gx);
        if (bestDist === null || d < bestDist) bestDist = d;
      }
    }
    if (bestDist !== null && bestDist > 1) score += bestDist - 1;
  }
  return score;
}

function bonus_the_herd(m) {
  const cows = new Set();
  for (const [k, tile] of m) if (tile[1] === Co) cows.add(k);
  return 2 * largestCC(cows);
}

function bonus_cool_water(m) {
  const waterCells = new Set();
  for (const [k, tile] of m) if (tile[0] === W) waterCells.add(k);
  if (waterCells.size === 0) return 0;
  const comps = connectedComponents(waterCells);
  let maxSize = 0;
  for (const c of comps) if (c.size > maxSize) maxSize = c.size;
  let best = 0;
  for (const comp of comps) {
    if (comp.size !== maxSize) continue;
    let wagCount = 0;
    for (const [k, tile] of m) {
      if (tile[1] !== Wa) continue;
      const [x, y] = parseKey(k);
      if (comp.has(k) || comp.has(cellKey(x+1,y)) || comp.has(cellKey(x-1,y)) ||
          comp.has(cellKey(x,y+1)) || comp.has(cellKey(x,y-1))) {
        wagCount++;
      }
    }
    if (wagCount > best) best = wagCount;
  }
  return 3 * best;
}

function bonus_prairie_life(m) {
  return Math.floor((countIcon(m, Co) + countTerr(m, P)) / 2);
}

function bonus_bootleggers(m) {
  let score = 0;
  for (const [k, tile] of m) {
    if (tile[1] === Be) {
      const [x, y] = parseKey(k);
      let adj = false;
      for (const [dx, dy] of N4) {
        const t = townGet(m, x+dx, y+dy);
        if (t && t[1] === Wa) { adj = true; break; }
      }
      score += adj ? 2 : -1;
    }
  }
  return score;
}

function bonus_wagon_train(m) {
  const table = [0, 0, 1, 2, 4, 7];
  function f(len) {
    if (len < 2) return 0;
    if (len >= 6) return 10;
    return table[len];
  }
  const wagons = new Set();
  for (const [k, tile] of m) if (tile[1] === Wa) wagons.add(k);
  let score = 0;
  for (const k of wagons) {
    const [x, y] = parseKey(k);
    if (!wagons.has(cellKey(x-1, y))) {
      let len = 1;
      while (wagons.has(cellKey(x+len, y))) len++;
      score += f(len);
    }
    if (!wagons.has(cellKey(x, y-1))) {
      let len = 1;
      while (wagons.has(cellKey(x, y+len))) len++;
      score += f(len);
    }
  }
  return score;
}

function bonus_boom_or_bust(m) {
  const n = countIcon(m, Mi);
  if (n === 0) return 0;
  let rate;
  if (n <= 2) rate = 5;
  else if (n <= 6) rate = 0;
  else if (n === 7) rate = 3;
  else rate = 8;
  return n * rate;
}

function bonus_the_clearing(m) {
  return 2 * countIcon(m, Fo) - countTerr(m, F);
}

function bonus_happy_cows(m) {
  let score = 0;
  for (const [k, tile] of m) {
    if (tile[1] !== Co || tile[0] === S) continue;
    const [x, y] = parseKey(k);
    let adjSnow = false;
    for (const [dx, dy] of N4) {
      const nb = townGet(m, x+dx, y+dy);
      if (nb && nb[0] === S) { adjSnow = true; break; }
    }
    if (!adjSnow) score += 2;
  }
  return score;
}

function bonus_badlands(m) {
  let score = 0;
  for (const [k, tile] of m) {
    if (tile[1] !== Gu) continue;
    const [x, y] = parseKey(k);
    const left = townGet(m, x-1, y), right = townGet(m, x+1, y);
    const h = left && left[0] === D && right && right[0] === D;
    const down = townGet(m, x, y-1), up = townGet(m, x, y+1);
    const v = down && down[0] === D && up && up[0] === D;
    if (h || v) score += 4;
  }
  return score;
}

function bonus_gold_country(m) {
  let score = 0;
  for (const [k, tile] of m) {
    if (tile[1] !== Mi) continue;
    if (tile[0] === M) { score += 2; continue; }
    const [x, y] = parseKey(k);
    for (const [dx, dy] of N4) {
      const nb = townGet(m, x+dx, y+dy);
      if (nb && nb[0] === M) { score += 2; break; }
    }
  }
  return score;
}

function bonus_circle_the_wagons(m) {
  let score = 0;
  for (const k of m.keys()) {
    const [x, y] = parseKey(k);
    let ok = true;
    for (const [dx, dy] of N4) {
      const nb = townGet(m, x+dx, y+dy);
      if (!nb || nb[1] !== Wa) { ok = false; break; }
    }
    if (ok) score += 6;
  }
  return score;
}

// Interactive bonuses: return [delta_p1, delta_p2]
function bonus_one_too_many(m1, m2) {
  const b1 = countIcon(m1, Be), b2 = countIcon(m2, Be);
  if (b1 > b2) return [-b2, 0];
  if (b2 > b1) return [0, -b1];
  return [0, 0];
}

function bonus_claim_jumpers(m1, m2) {
  const mi1 = countIcon(m1, Mi), mi2 = countIcon(m2, Mi);
  const g1 = countIcon(m1, Gu), g2 = countIcon(m2, Gu);
  if (mi1 > mi2) {
    let d1 = 9, d2 = 0;
    if (g2 > g1) { d1 -= 5; d2 += 5; }
    return [d1, d2];
  }
  if (mi2 > mi1) {
    let d1 = 0, d2 = 9;
    if (g1 > g2) { d1 += 5; d2 -= 5; }
    return [d1, d2];
  }
  return [0, 0];
}

function bonus_smalltown_charm(m1, m2) {
  const n1 = m1.size, n2 = m2.size;
  if (n1 < n2) return [n2 - n1, 0];
  if (n2 < n1) return [0, n1 - n2];
  return [0, 0];
}

export const LOCAL_BONUSES = {
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
};

export const INTERACTIVE_BONUSES = {
  "ONE TOO MANY": bonus_one_too_many,
  "CLAIM JUMPERS": bonus_claim_jumpers,
  "SMALLTOWN CHARM": bonus_smalltown_charm,
};

// ============================================================================
// Final scoring
// ============================================================================

export function computeScores(m1, m2, bonusNames) {
  let s1 = terrainScore(m1), s2 = terrainScore(m2);
  for (const name of bonusNames) {
    if (LOCAL_BONUSES[name]) {
      s1 += LOCAL_BONUSES[name](m1);
      s2 += LOCAL_BONUSES[name](m2);
    } else if (INTERACTIVE_BONUSES[name]) {
      const [d1, d2] = INTERACTIVE_BONUSES[name](m1, m2);
      s1 += d1; s2 += d2;
    }
  }
  return [s1, s2];
}

export function computeScoreBreakdown(m1, m2, bonusNames) {
  const b1 = { terrain: terrainScore(m1) };
  const b2 = { terrain: terrainScore(m2) };
  for (const name of bonusNames) {
    if (LOCAL_BONUSES[name]) {
      b1[name] = LOCAL_BONUSES[name](m1);
      b2[name] = LOCAL_BONUSES[name](m2);
    } else if (INTERACTIVE_BONUSES[name]) {
      const [d1, d2] = INTERACTIVE_BONUSES[name](m1, m2);
      b1[name] = d1; b2[name] = d2;
    }
  }
  return [b1, b2];
}

export function utility(m1, m2, bonusNames) {
  const [s1, s2] = computeScores(m1, m2, bonusNames);
  return s1 - s2;
}

// ============================================================================
// Placement logic
// ============================================================================

export function footprint(ax, ay) {
  return [[ax,ay],[ax+1,ay],[ax,ay+1],[ax+1,ay+1]];
}

export const ANCHOR_OFFSETS = [
  [-2,-1],[-2,0],[-1,-2],[-1,-1],[-1,0],[-1,1],
  [0,-2],[0,-1],[0,0],[0,1],[1,-1],[1,0],
];

export function candidateAnchors(m) {
  if (m.size === 0) return new Set([cellKey(0, 0)]);
  const cand = new Set();
  for (const k of m.keys()) {
    const [x, y] = parseKey(k);
    for (const [dx, dy] of ANCHOR_OFFSETS) {
      cand.add(cellKey(x + dx, y + dy));
    }
  }
  return cand;
}

export function placeCard(m, card, ax, ay, rot180) {
  for (let i = 0; i < 2; i++)
    for (let j = 0; j < 2; j++)
      m.set(cellKey(ax + i, ay + j), tileAt(card, i, j, rot180));
  return m;
}

export function legalPlacements(m, card) {
  const result = [];
  for (const k of candidateAnchors(m)) {
    const [ax, ay] = parseKey(k);
    result.push([ax, ay, false]);
    result.push([ax, ay, true]);
  }
  return result;
}

// ============================================================================
// Game state
// ============================================================================

export class GameState {
  constructor() {
    this.circle = [];
    this.towns = [new Map(), new Map()];
    this.free = [[], []];
    this.player = 0;
    this.phase = Phase.PLACE_FREE;
    this.drafted = -1;
    this.bonusNames = ["", "", ""];
  }

  copy() {
    const s = new GameState();
    s.circle = this.circle.slice();
    s.towns = [new Map(this.towns[0]), new Map(this.towns[1])];
    s.free = [this.free[0].slice(), this.free[1].slice()];
    s.player = this.player;
    s.phase = this.phase;
    s.drafted = this.drafted;
    s.bonusNames = this.bonusNames;
    return s;
  }

  normalize() {
    if (this.phase === Phase.PLACE_FREE && this.free[this.player].length === 0) {
      if (this.circle.length > 0)
        this.phase = Phase.DRAFT;
    }
  }

  isTerminal() {
    this.normalize();
    return this.circle.length === 0 &&
           this.free[0].length === 0 &&
           this.free[1].length === 0 &&
           this.drafted === -1;
  }
}

export function getActions(state) {
  state.normalize();
  if (state.isTerminal()) return [];
  const p = state.player;
  const m = state.towns[p];

  if (state.phase === Phase.PLACE_FREE) {
    return legalPlacements(m, CARDS[state.free[p][0]]);
  }
  if (state.phase === Phase.DRAFT) {
    const actions = [];
    for (let j = 0; j < state.circle.length; j++)
      actions.push({ type: "draft", offset: j });
    return actions;
  }
  if (state.phase === Phase.PLACE_DRAFT) {
    return legalPlacements(m, CARDS[state.drafted]);
  }
  return [];
}

export function applyAction(state, action) {
  const s = state.copy();
  s.normalize();
  const p = s.player;

  if (s.phase === Phase.DRAFT) {
    const chosen = s.circle[action.offset];
    const skipped = s.circle.slice(0, action.offset);
    s.circle = s.circle.slice(action.offset + 1);
    s.free[1 - p].push(...skipped);
    s.drafted = chosen;
    s.phase = Phase.PLACE_DRAFT;
    s.normalize();
    return s;
  }

  const [ax, ay, rot180] = action;
  if (s.phase === Phase.PLACE_FREE) {
    const cardId = s.free[p].shift();
    s.towns[p] = placeCard(s.towns[p], CARDS[cardId], ax, ay, rot180);
    s.normalize();
    return s;
  }
  if (s.phase === Phase.PLACE_DRAFT) {
    s.towns[p] = placeCard(s.towns[p], CARDS[s.drafted], ax, ay, rot180);
    s.drafted = -1;
    s.player = 1 - p;
    s.phase = Phase.PLACE_FREE;
    s.normalize();
    return s;
  }
  throw new Error(`Bad phase ${s.phase}`);
}

// ============================================================================
// Seeded RNG (mulberry32)
// ============================================================================

export class SeededRNG {
  constructor(seed) { this.state = seed | 0; }
  next() {
    let t = (this.state += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  randInt(n) { return Math.floor(this.next() * n); }
  shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = this.randInt(i + 1);
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
  }
}

export function generateDeal(seed) {
  const rng = new SeededRNG(seed);
  const ids = Array.from({length: 18}, (_, i) => i);
  rng.shuffle(ids);
  const bonusNames = [CARD_BONUS_MAP[ids[0]], CARD_BONUS_MAP[ids[1]], CARD_BONUS_MAP[ids[2]]];
  const circle = ids.slice(3);
  return { bonusNames, circle };
}

export function makeInitialState(circle, bonusNames, startIndex = 0) {
  const s = new GameState();
  s.circle = [...circle.slice(startIndex), ...circle.slice(0, startIndex)];
  s.bonusNames = bonusNames;
  s.player = 0;
  s.phase = Phase.PLACE_FREE;
  s.normalize();
  return s;
}
