// Circle the Wagons — AI Agents (ported from solver.py)
// Pure computation, no DOM.

import {
  Phase, CARDS, getActions, applyAction, utility, legalPlacements,
  candidateAnchors, parseKey, ANCHOR_OFFSETS, cellKey, tileAt,
} from './game.js';

// ============================================================================
// Greedy agent: 1-ply evaluation
// ============================================================================

export function pickActionGreedy(state, bonusNames) {
  const actions = getActions(state);
  if (actions.length === 0) return null;
  const sign = state.player === 0 ? 1 : -1;

  if (state.phase === Phase.DRAFT) {
    // Draft: need full state copy to simulate placements
    let bestVal = -Infinity;
    let bestAct = actions[0];
    for (const a of actions) {
      let child = applyAction(state, a);
      child = advanceGreedy(child, bonusNames);
      const v = sign * utility(child.towns[0], child.towns[1], bonusNames);
      if (v > bestVal) { bestVal = v; bestAct = a; }
    }
    return bestAct;
  }

  // Placement: mutate-evaluate-undo to avoid ~80 state copies
  const p = state.player;
  const m = state.towns[p];
  const cardId = state.phase === Phase.PLACE_FREE ? state.free[p][0] : state.drafted;
  const card = CARDS[cardId];
  const [t0, t1, t2, t3] = card.quads;
  const towns0 = state.towns[0], towns1 = state.towns[1];

  let bestVal = -Infinity;
  let bestAct = actions[0];

  for (const [ax, ay, rot180] of actions) {
    const k0 = cellKey(ax, ay), k1 = cellKey(ax+1, ay);
    const k2 = cellKey(ax, ay+1), k3 = cellKey(ax+1, ay+1);

    // Save
    const s0 = m.get(k0), s1v = m.get(k1), s2v = m.get(k2), s3 = m.get(k3);

    // Place
    if (rot180) {
      m.set(k0, t3); m.set(k1, t2); m.set(k2, t1); m.set(k3, t0);
    } else {
      m.set(k0, t0); m.set(k1, t1); m.set(k2, t2); m.set(k3, t3);
    }

    // Evaluate
    const v = sign * utility(towns0, towns1, bonusNames);

    // Restore
    if (s0 === undefined) m.delete(k0); else m.set(k0, s0);
    if (s1v === undefined) m.delete(k1); else m.set(k1, s1v);
    if (s2v === undefined) m.delete(k2); else m.set(k2, s2v);
    if (s3 === undefined) m.delete(k3); else m.set(k3, s3);

    if (v > bestVal) { bestVal = v; bestAct = [ax, ay, rot180]; }
  }
  return bestAct;
}

// ============================================================================
// advanceGreedy: play greedy until next DRAFT or terminal
// ============================================================================

function advanceGreedy(state, bonusNames) {
  while (!state.isTerminal()) {
    if (state.phase === Phase.DRAFT) return state;
    const action = pickActionGreedy(state, bonusNames);
    state = applyAction(state, action);
  }
  return state;
}

// ============================================================================
// Draft minimax: alpha-beta over draft decisions, greedy placements between
// ============================================================================

function draftMinimax(state, bonusNames, depth, alpha = -999999, beta = 999999) {
  if (state.isTerminal() || depth <= 0 || state.phase !== Phase.DRAFT) {
    return utility(state.towns[0], state.towns[1], bonusNames);
  }

  const p = state.player;
  const sign = p === 0 ? 1 : -1;
  const draftActions = getActions(state);

  // Pre-evaluate and sort for better pruning
  const scored = [];
  for (const da of draftActions) {
    let child = applyAction(state, da);
    child = advanceGreedy(child, bonusNames);
    const v = sign * utility(child.towns[0], child.towns[1], bonusNames);
    scored.push([v, child]);
  }
  scored.sort((a, b) => b[0] - a[0]); // best first for current player

  if (p === 0) {
    let best = -999999;
    for (const [, child] of scored) {
      const v = draftMinimax(child, bonusNames, depth - 1, alpha, beta);
      if (v > best) best = v;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break;
    }
    return best;
  } else {
    let best = 999999;
    for (const [, child] of scored) {
      const v = draftMinimax(child, bonusNames, depth - 1, alpha, beta);
      if (v < best) best = v;
      if (best < beta) beta = best;
      if (alpha >= beta) break;
    }
    return best;
  }
}

// ============================================================================
// Lookahead agent: greedy placements + minimax drafts
// ============================================================================

export function pickActionLookahead(state, bonusNames) {
  if (state.phase !== Phase.DRAFT) {
    return pickActionGreedy(state, bonusNames);
  }

  // Auto draft depth: deeper when fewer cards remain
  const n = state.circle.length;
  const draftDepth = n <= 6 ? 3 : n <= 8 ? 2 : 1;

  const sign = state.player === 0 ? 1 : -1;
  let bestVal = -Infinity;
  let bestAct = null;

  // Pre-sort draft actions by greedy evaluation for better minimax pruning
  const draftActions = getActions(state);
  const scored = [];
  for (const da of draftActions) {
    let child = applyAction(state, da);
    child = advanceGreedy(child, bonusNames);
    const v = sign * utility(child.towns[0], child.towns[1], bonusNames);
    scored.push([v, da, child]);
  }
  scored.sort((a, b) => b[0] - a[0]);

  for (const [, draftAct, child] of scored) {
    const v = sign * draftMinimax(child, bonusNames, draftDepth - 1);
    if (v > bestVal) {
      bestVal = v;
      bestAct = draftAct;
    }
  }
  return bestAct;
}

// ============================================================================
// Random agent (for testing)
// ============================================================================

export function pickActionRandom(state, rng) {
  const actions = getActions(state);
  if (actions.length === 0) return null;
  return actions[rng.randInt(actions.length)];
}
