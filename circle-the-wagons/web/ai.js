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
  let bestVal = -Infinity;
  let bestAct = actions[0];
  for (const a of actions) {
    const child = applyAction(state, a);
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
// Lookahead agent: greedy for placements, draft-aware for drafts
// ============================================================================

export function pickActionLookahead(state, bonusNames) {
  if (state.phase !== Phase.DRAFT) {
    return pickActionGreedy(state, bonusNames);
  }

  const sign = state.player === 0 ? 1 : -1;
  let bestVal = -Infinity;
  let bestAct = null;

  const draftActions = getActions(state);
  for (const draftAct of draftActions) {
    let child = applyAction(state, draftAct);
    child = advanceGreedy(child, bonusNames);
    const v = sign * utility(child.towns[0], child.towns[1], bonusNames);
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
