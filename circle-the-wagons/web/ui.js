// Circle the Wagons — UI Controller
// Wires game engine + AI to the DOM.

import {
  Terr, Icon, Phase, CARDS, CARD_BONUS_MAP, BONUS_DESCRIPTIONS,
  TERR_SHORT, ICON_SHORT, TERR_NAMES, tileAt, cellKey, parseKey,
  townGet, townHas, candidateAnchors, placeCard, legalPlacements,
  terrainScore, computeScores, computeScoreBreakdown, utility,
  generateDeal, makeInitialState, getActions, applyAction, GameState,
  footprint,
} from './game.js';

import { pickActionGreedy, pickActionLookahead } from './ai.js';

// ============================================================================
// DOM references
// ============================================================================

const $ = id => document.getElementById(id);
const seedInput = $('seed-input');
const aiSelect = $('ai-select');
const newGameBtn = $('new-game-btn');
const rulesToggleBtn = $('rules-toggle-btn');
const rulesPanel = $('rules-panel');
const rulesCloseBtn = $('rules-close-btn');
const statusBar = $('status-bar');
const circleContainer = $('circle-container');
const circleCount = $('circle-count');
const draftControls = $('draft-controls');
const draftConfirmBtn = $('draft-confirm-btn');
const draftCancelBtn = $('draft-cancel-btn');
const townEls = [$('town-0'), $('town-1')];
const placementPanel = $('placement-panel');
const placementTitle = $('placement-title');
const cardPreview = $('card-preview');
const rotateBtn = $('rotate-btn');
const scoreEls = [$('score-0'), $('score-1')];
const logContent = $('log-content');
const endModal = $('end-modal');
const endTitle = $('end-title');
const endScores = $('end-scores');
const endCloseBtn = $('end-close-btn');

// ============================================================================
// Game state
// ============================================================================

let state = null;       // GameState
let aiType = 'lookahead';
let rot180 = false;     // current rotation for placement
let selectedDraftOffset = null;
let placementAnchors = null;  // Set of "x,y" strings for valid anchors
let ghostAnchor = null;       // [x, y] currently hovered anchor
let busy = false;             // prevent clicks during AI turn

// ============================================================================
// Rendering: cells
// ============================================================================

function makeCell(terr, icon) {
  const div = document.createElement('div');
  div.className = `cell terr-${terr}`;
  if (icon !== Icon.Empty) {
    div.textContent = ICON_SHORT[icon];
  }
  return div;
}

// ============================================================================
// Rendering: card preview
// ============================================================================

function renderCardPreview(cardId, r180) {
  cardPreview.innerHTML = '';
  const card = CARDS[cardId];
  // Grid order: TL(0,1) TR(1,1) / BL(0,0) BR(1,0) — top row first
  for (let j = 1; j >= 0; j--) {
    for (let i = 0; i < 2; i++) {
      const [t, ic] = tileAt(card, i, j, r180);
      cardPreview.appendChild(makeCell(t, ic));
    }
  }
}

// ============================================================================
// Rendering: circle
// ============================================================================

function renderCircle() {
  circleContainer.innerHTML = '';
  if (!state) return;
  const n = state.circle.length;
  circleCount.textContent = `(${n} cards)`;
  if (n === 0) {
    circleContainer.style.width = '0';
    circleContainer.style.height = '0';
    return;
  }
  const isDraftPhase = state.phase === Phase.DRAFT && state.player === 0 && !busy;

  // Card dimensions (read from CSS variable)
  const cs = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--cell-size'));
  const cardW = cs * 2 + 6; // 2 cells + border
  const cardH = cs * 2 + 6;

  // Compute radius so cards don't overlap
  // Circumference must fit n cards with gaps: 2*pi*r >= n * (cardW + gap)
  const gap = 12;
  const minRadius = Math.max(80, (n * (cardW + gap)) / (2 * Math.PI));
  const radius = minRadius;

  // Container size
  const containerSize = Math.ceil(2 * radius + cardW + 40);
  circleContainer.style.width = containerSize + 'px';
  circleContainer.style.height = containerSize + 'px';
  const cx = containerSize / 2;
  const cy = containerSize / 2;

  // Draw connector lines between adjacent cards
  for (let idx = 0; idx < n; idx++) {
    const angle1 = (idx / n) * 2 * Math.PI - Math.PI / 2;
    const angle2 = ((idx + 1) % n / n) * 2 * Math.PI - Math.PI / 2;
    const x1 = cx + radius * Math.cos(angle1);
    const y1 = cy + radius * Math.sin(angle1);
    const x2 = cx + radius * Math.cos(angle2);
    const y2 = cy + radius * Math.sin(angle2);
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.sqrt(dx * dx + dy * dy);
    const ang = Math.atan2(dy, dx) * 180 / Math.PI;

    const line = document.createElement('div');
    line.className = 'circle-connector';
    line.style.left = x1 + 'px';
    line.style.top = y1 + 'px';
    line.style.width = len + 'px';
    line.style.transform = `rotate(${ang}deg)`;
    circleContainer.appendChild(line);
  }

  // Place cards radially
  state.circle.forEach((cid, idx) => {
    const card = CARDS[cid];
    const angle = (idx / n) * 2 * Math.PI - Math.PI / 2; // start at top
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);

    const wrapper = document.createElement('div');
    wrapper.className = 'circle-card';
    wrapper.style.left = x + 'px';
    wrapper.style.top = y + 'px';
    wrapper.style.transform = 'translate(-50%, -50%)';
    if (isDraftPhase) wrapper.classList.add('clickable');

    // Card label
    const label = document.createElement('div');
    label.className = 'card-label';
    label.textContent = `#${cid}`;
    wrapper.appendChild(label);

    // 2x2 grid: TL TR / BL BR
    for (let j = 1; j >= 0; j--) {
      for (let i = 0; i < 2; i++) {
        const [t, ic] = tileAt(card, i, j, false);
        wrapper.appendChild(makeCell(t, ic));
      }
    }

    // Draft interaction
    if (isDraftPhase) {
      wrapper.addEventListener('click', () => selectDraft(idx));
    }

    // Mark selected/skipped
    if (selectedDraftOffset !== null) {
      if (idx === selectedDraftOffset) {
        wrapper.classList.add('selected');
      } else if (idx < selectedDraftOffset) {
        wrapper.classList.add('skipped');
        const skipLabel = document.createElement('div');
        skipLabel.className = 'skip-label';
        skipLabel.textContent = '\u2192 AI';
        wrapper.appendChild(skipLabel);
      }
    }

    circleContainer.appendChild(wrapper);
  });
}

// ============================================================================
// Rendering: towns
// ============================================================================

function getTownBounds(m) {
  if (m.size === 0) return { x0: 0, x1: 1, y0: 0, y1: 1 };
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const k of m.keys()) {
    const [x, y] = parseKey(k);
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  return { x0, x1, y0, y1 };
}

function renderTown(playerIdx) {
  const el = townEls[playerIdx];
  el.innerHTML = '';
  const m = state.towns[playerIdx];
  if (m.size === 0) {
    el.style.gridTemplateColumns = '';
    return;
  }

  const isHumanPlacing = playerIdx === 0 && !busy &&
    (state.phase === Phase.PLACE_FREE || state.phase === Phase.PLACE_DRAFT) &&
    state.player === 0;

  // Determine bounds — expand for placement anchors if human is placing
  let { x0, x1, y0, y1 } = getTownBounds(m);

  if (isHumanPlacing && placementAnchors) {
    for (const k of placementAnchors) {
      const [ax, ay] = parseKey(k);
      // footprint is 2x2 from anchor
      if (ax < x0) x0 = ax;
      if (ax + 1 > x1) x1 = ax + 1;
      if (ay < y0) y0 = ay;
      if (ay + 1 > y1) y1 = ay + 1;
    }
  }

  // Add 1 cell of padding
  x0 -= 1; y0 -= 1; x1 += 1; y1 += 1;
  const cols = x1 - x0 + 1;
  const rows = y1 - y0 + 1;

  el.style.display = 'grid';
  el.style.gridTemplateColumns = `repeat(${cols}, var(--cell-size))`;
  el.style.gridTemplateRows = `repeat(${rows}, var(--cell-size))`;

  // Ghost cells for placement preview
  const ghostCells = new Map();
  if (isHumanPlacing && ghostAnchor) {
    const [gx, gy] = ghostAnchor;
    const cardId = state.phase === Phase.PLACE_FREE ? state.free[0][0] : state.drafted;
    const card = CARDS[cardId];
    for (let i = 0; i < 2; i++) {
      for (let j = 0; j < 2; j++) {
        ghostCells.set(cellKey(gx + i, gy + j), tileAt(card, i, j, rot180));
      }
    }
  }

  // Render cells top-to-bottom (high y first)
  for (let y = y1; y >= y0; y--) {
    for (let x = x0; x <= x1; x++) {
      const k = cellKey(x, y);
      const tile = m.get(k);
      const ghost = ghostCells.get(k);

      if (ghost) {
        const cell = makeCell(ghost[0], ghost[1]);
        cell.classList.add('ghost');
        el.appendChild(cell);
      } else if (tile) {
        el.appendChild(makeCell(tile[0], tile[1]));
      } else {
        const cell = document.createElement('div');
        cell.className = 'cell empty-cell';

        // Highlight valid anchor positions
        if (isHumanPlacing && placementAnchors && placementAnchors.has(k)) {
          cell.classList.add('anchor-highlight');
          cell.addEventListener('click', () => handlePlacement(x, y));
          cell.addEventListener('mouseenter', () => {
            ghostAnchor = [x, y];
            renderTown(0);
          });
          cell.addEventListener('mouseleave', () => {
            ghostAnchor = null;
            renderTown(0);
          });
        }

        el.appendChild(cell);
      }
    }
  }

  // Also make occupied cells clickable if they're anchor positions
  if (isHumanPlacing && placementAnchors) {
    // For overlapping placements, occupied cells that are within an anchor's footprint
    // need to be clickable too. We handle this by checking each anchor.
    // Already done through the anchor set — anchors are bottom-left of 2x2.
    // We need to let user click anywhere in the footprint to place.
    // Let's add click handlers to ALL cells in the grid that belong to an anchor footprint.
    const allCells = el.children;
    let cellIdx = 0;
    for (let y = y1; y >= y0; y--) {
      for (let x = x0; x <= x1; x++) {
        const cell = allCells[cellIdx];
        cellIdx++;
        if (cell.classList.contains('anchor-highlight')) continue;
        if (cell.classList.contains('ghost')) continue;

        // Check if this cell is part of any anchor's footprint
        for (const [dx, dy] of [[0,0],[-1,0],[0,-1],[-1,-1]]) {
          const anchorKey = cellKey(x + dx, y + dy);
          if (placementAnchors && placementAnchors.has(anchorKey)) {
            cell.style.cursor = 'pointer';
            const ax = x + dx, ay = y + dy;
            cell.addEventListener('click', () => handlePlacement(ax, ay));
            cell.addEventListener('mouseenter', () => {
              ghostAnchor = [ax, ay];
              renderTown(0);
            });
            cell.addEventListener('mouseleave', () => {
              ghostAnchor = null;
              renderTown(0);
            });
            break;
          }
        }
      }
    }
  }
}

// ============================================================================
// Rendering: scores
// ============================================================================

function renderScores() {
  if (!state) return;
  const [b1, b2] = computeScoreBreakdown(state.towns[0], state.towns[1], state.bonusNames);
  const [s1, s2] = computeScores(state.towns[0], state.towns[1], state.bonusNames);

  [b1, b2].forEach((breakdown, idx) => {
    const el = scoreEls[idx];
    el.innerHTML = '';
    const total = idx === 0 ? s1 : s2;

    // Terrain
    const terrRow = document.createElement('div');
    terrRow.className = 'score-row';
    terrRow.innerHTML = `<span class="score-label">Terrain</span><span class="score-val">${breakdown.terrain}</span>`;
    el.appendChild(terrRow);

    // Bonuses
    for (const name of state.bonusNames) {
      if (!name) continue;
      const val = breakdown[name] || 0;
      const row = document.createElement('div');
      row.className = 'score-row';
      row.innerHTML = `<span class="score-label">${name}</span><span class="score-val">${val >= 0 ? '+' : ''}${val}</span>`;
      el.appendChild(row);
    }

    // Total
    const totalRow = document.createElement('div');
    totalRow.className = 'score-row total';
    totalRow.innerHTML = `<span class="score-label">Total</span><span class="score-val">${total}</span>`;
    el.appendChild(totalRow);
  });
}

// ============================================================================
// Rendering: bonuses
// ============================================================================

function renderBonuses() {
  if (!state) return;
  state.bonusNames.forEach((name, idx) => {
    const el = $(`bonus-${idx}`);
    if (!name) { el.innerHTML = ''; return; }
    el.innerHTML = `<div class="bonus-name">${name}</div><div class="bonus-desc">${BONUS_DESCRIPTIONS[name] || ''}</div>`;
  });
}

// ============================================================================
// Game log
// ============================================================================

function log(msg, player = null) {
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  if (player !== null) entry.classList.add(`log-p${player}`);
  entry.textContent = msg;
  logContent.appendChild(entry);
  logContent.scrollTop = logContent.scrollHeight;
}

// ============================================================================
// Status
// ============================================================================

function setStatus(html) {
  statusBar.innerHTML = html;
}

// ============================================================================
// Placement logic
// ============================================================================

function computePlacementAnchors() {
  if (!state || state.player !== 0) { placementAnchors = null; return; }
  if (state.phase !== Phase.PLACE_FREE && state.phase !== Phase.PLACE_DRAFT) {
    placementAnchors = null;
    return;
  }
  const m = state.towns[0];
  placementAnchors = candidateAnchors(m);
}

function showPlacementUI() {
  const cardId = state.phase === Phase.PLACE_FREE ? state.free[0][0] : state.drafted;
  placementPanel.classList.remove('hidden');
  placementTitle.textContent = `Place Card #${cardId}`;
  renderCardPreview(cardId, rot180);
  computePlacementAnchors();
  setStatus('Click a highlighted cell on your town to place the card. Press <b>R</b> to rotate.');
}

function hidePlacementUI() {
  placementPanel.classList.add('hidden');
  placementAnchors = null;
  ghostAnchor = null;
}

function handlePlacement(ax, ay) {
  if (busy || state.player !== 0) return;
  const action = [ax, ay, rot180];
  const cardId = state.phase === Phase.PLACE_FREE ? state.free[0][0] : state.drafted;
  log(`You place card #${cardId} at (${ax},${ay})${rot180 ? ' rotated' : ''}`, 0);

  hidePlacementUI();
  state = applyAction(state, action);
  rot180 = false;
  afterAction();
}

// ============================================================================
// Draft logic
// ============================================================================

function selectDraft(offset) {
  if (busy || state.player !== 0 || state.phase !== Phase.DRAFT) return;
  selectedDraftOffset = offset;
  draftControls.classList.remove('hidden');
  renderCircle();
}

function confirmDraft() {
  if (selectedDraftOffset === null) return;
  const offset = selectedDraftOffset;
  const cardId = state.circle[offset];
  const skipped = offset;

  let msg = `You draft card #${cardId}`;
  if (skipped > 0) msg += ` (skipping ${skipped} card${skipped > 1 ? 's' : ''} to AI)`;
  log(msg, 0);

  draftControls.classList.add('hidden');
  selectedDraftOffset = null;
  state = applyAction(state, { type: 'draft', offset });
  afterAction();
}

function cancelDraft() {
  selectedDraftOffset = null;
  draftControls.classList.add('hidden');
  renderCircle();
}

// ============================================================================
// AI turn
// ============================================================================

async function aiTurn() {
  busy = true;
  setStatus('AI is thinking...');
  renderAll();

  // Small delay so the UI updates before blocking computation
  await delay(100);

  while (!state.isTerminal() && state.player === 1) {
    const action = aiType === 'lookahead'
      ? pickActionLookahead(state, state.bonusNames)
      : pickActionGreedy(state, state.bonusNames);

    if (action === null) break;

    if (action.type === 'draft') {
      const cardId = state.circle[action.offset];
      const skipped = action.offset;
      let msg = `AI drafts card #${cardId}`;
      if (skipped > 0) msg += ` (skipping ${skipped})`;
      log(msg, 1);
    } else {
      const [ax, ay, r] = action;
      const cardId = state.phase === Phase.PLACE_FREE ? state.free[1][0] : state.drafted;
      log(`AI places card #${cardId} at (${ax},${ay})${r ? ' rotated' : ''}`, 1);
    }

    state = applyAction(state, action);
    renderAll();
    await delay(300);
  }

  busy = false;
  afterAction();
}

// ============================================================================
// Game flow
// ============================================================================

function afterAction() {
  renderAll();

  if (state.isTerminal()) {
    showEndModal();
    return;
  }

  if (state.player === 0) {
    // Human turn
    if (state.phase === Phase.DRAFT) {
      setStatus('Your turn: <b>Draft</b> a card from the circle.');
    } else {
      showPlacementUI();
      renderTown(0);
    }
  } else {
    // AI turn
    aiTurn();
  }
}

function renderAll() {
  renderCircle();
  renderTown(0);
  renderTown(1);
  renderScores();
}

// ============================================================================
// End modal
// ============================================================================

function showEndModal() {
  const [s1, s2] = computeScores(state.towns[0], state.towns[1], state.bonusNames);
  let resultText;
  if (s1 > s2) {
    resultText = `<div class="winner">You win!</div>`;
  } else if (s2 > s1) {
    resultText = `<div class="winner">AI wins!</div>`;
  } else {
    resultText = `<div class="winner">It's a tie!</div>`;
  }

  endScores.innerHTML = `${resultText}<br>You: <b>${s1}</b> &nbsp; AI: <b>${s2}</b>`;
  endModal.classList.remove('hidden');
  setStatus('Game over!');
  log(`Game over. You: ${s1}, AI: ${s2}. ${s1 > s2 ? 'You win!' : s2 > s1 ? 'AI wins!' : 'Tie!'}`, null);
}

// ============================================================================
// New game
// ============================================================================

function startGame() {
  const seed = parseInt(seedInput.value) || 42;
  aiType = aiSelect.value;
  rot180 = false;
  selectedDraftOffset = null;
  ghostAnchor = null;
  busy = false;
  logContent.innerHTML = '';
  endModal.classList.add('hidden');
  draftControls.classList.add('hidden');
  hidePlacementUI();

  const { bonusNames, circle } = generateDeal(seed);
  state = makeInitialState(circle, bonusNames, 0);

  log(`New game (seed ${seed})`);
  log(`Bonuses: ${bonusNames.join(', ')}`);
  log(`Circle: ${circle.length} cards`);

  renderBonuses();
  renderAll();
  afterAction();
}

// ============================================================================
// Event listeners
// ============================================================================

newGameBtn.addEventListener('click', startGame);
endCloseBtn.addEventListener('click', startGame);
draftConfirmBtn.addEventListener('click', confirmDraft);
draftCancelBtn.addEventListener('click', cancelDraft);

rulesToggleBtn.addEventListener('click', () => {
  rulesPanel.classList.toggle('hidden');
});
rulesCloseBtn.addEventListener('click', () => {
  rulesPanel.classList.add('hidden');
});

rotateBtn.addEventListener('click', () => {
  rot180 = !rot180;
  const cardId = state.phase === Phase.PLACE_FREE ? state.free[0][0] : state.drafted;
  renderCardPreview(cardId, rot180);
  if (ghostAnchor) renderTown(0);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'r' || e.key === 'R') {
    if (!placementPanel.classList.contains('hidden')) {
      rot180 = !rot180;
      const cardId = state.phase === Phase.PLACE_FREE ? state.free[0][0] : state.drafted;
      renderCardPreview(cardId, rot180);
      if (ghostAnchor) renderTown(0);
    }
  }
});

// ============================================================================
// Helpers
// ============================================================================

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
