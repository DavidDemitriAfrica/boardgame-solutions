// Circle the Wagons — AI Agents (ported from solver.py)
// Pure computation, no DOM.

import {
  Phase, CARDS, getActions, applyAction, utility, legalPlacements,
  placeCard, candidateAnchors, parseKey, ANCHOR_OFFSETS, cellKey,
} from './game.js';

// ============================================================================
// Greedy agent: 1-ply evaluation
// ============================================================================

export function pickActionGreedy(state, bonusNames) {
  const actions = getActions(state);
  if (actions.length === 0) return null;
  const sign = state.player === 0 ? 1 : -1;
  const isDraft = state.phase === Phase.DRAFT;
  let bestVal = -Infinity;
  let bestAct = actions[0];
  for (const a of actions) {
    let child = applyAction(state, a);
    if (isDraft) {
      // Simulate greedy placements to evaluate draft quality
      child = advanceGreedy(child, bonusNames);
    }
    const v = sign * utility(child.towns[0], child.towns[1], bonusNames);
    if (v > bestVal) {
      bestVal = v;
      bestAct = a;
    }
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

  const draftActions = getActions(state);
  for (const draftAct of draftActions) {
    let child = applyAction(state, draftAct);
    child = advanceGreedy(child, bonusNames);
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
