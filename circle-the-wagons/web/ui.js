// Circle the Wagons — UI Controller
// Wires game engine + AI to the DOM.

import {
  Terr, Icon, Phase, CARDS, CARD_BONUS_MAP, BONUS_DESCRIPTIONS,
  TERR_SHORT, ICON_SHORT, TERR_NAMES, tileAt, cellKey, parseKey,
  townGet, townHas, candidateAnchors,
  terrainScore, computeScores, computeScoreBreakdown, utility,
  generateDeal, makeInitialState, getActions, applyAction, GameState,
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
const draftInfo = $('draft-info');
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
let stateHistory = [];  // for undo
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
// Rendering: card as a 2x2 mini-grid element
// ============================================================================

function makeCardElement(card, r180) {
  const wrapper = document.createElement('div');
  wrapper.style.display = 'grid';
  wrapper.style.gridTemplateColumns = 'var(--cell-size) var(--cell-size)';
  wrapper.style.gridTemplateRows = 'var(--cell-size) var(--cell-size)';
  // Top row first: j=1, then j=0
  for (let j = 1; j >= 0; j--) {
    for (let i = 0; i < 2; i++) {
      const [t, ic] = tileAt(card, i, j, r180);
      wrapper.appendChild(makeCell(t, ic));
    }
  }
  return wrapper;
}

// ============================================================================
// Rendering: card preview (placement panel)
// ============================================================================

function renderCardPreview(cardId, r180) {
  cardPreview.innerHTML = '';
  const grid = makeCardElement(CARDS[cardId], r180);
  // Transfer children into the preview grid
  while (grid.firstChild) cardPreview.appendChild(grid.firstChild);
}

// ============================================================================
// Rendering: circle (radial layout)
// ============================================================================

function renderCircle() {
  circleContainer.innerHTML = '';
  if (!state) return;
  const n = state.circle.length;
  circleCount.textContent = `(${n} cards)`;
  if (n === 0) {
    circleContainer.style.width = '0px';
    circleContainer.style.height = '0px';
    return;
  }
  const isDraftPhase = state.phase === Phase.DRAFT && state.player === 0 && !busy;

  // Card pixel size from CSS variable
  const csVal = getComputedStyle(document.documentElement).getPropertyValue('--cell-size');
  const cs = parseFloat(csVal) || 40;
  const cardW = cs * 2 + 4; // 2 cells + borders
  const halfCard = cardW / 2;

  // Radius: circumference must fit n cards with gaps
  const gap = 14;
  const radius = Math.max(100, (n * (cardW + gap)) / (2 * Math.PI));

  // Container: big enough for the circle + cards
  const size = Math.ceil(2 * radius + cardW + 60);
  circleContainer.style.width = size + 'px';
  circleContainer.style.height = size + 'px';
  circleContainer.style.position = 'relative';
  const cx = size / 2;
  const cy = size / 2;

  // Draw connector ring segments between adjacent cards
  for (let i = 0; i < n; i++) {
    const a1 = (i / n) * 2 * Math.PI - Math.PI / 2;
    const a2 = ((i + 1) % n / n) * 2 * Math.PI - Math.PI / 2;
    const x1 = cx + radius * Math.cos(a1);
    const y1 = cy + radius * Math.sin(a1);
    const x2 = cx + radius * Math.cos(a2);
    const y2 = cy + radius * Math.sin(a2);
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.sqrt(dx * dx + dy * dy);
    const ang = Math.atan2(dy, dx);

    const line = document.createElement('div');
    line.style.cssText = `position:absolute;left:${x1}px;top:${y1}px;width:${len}px;height:2px;background:rgba(255,255,255,0.08);transform-origin:0 50%;transform:rotate(${ang}rad);pointer-events:none;`;
    circleContainer.appendChild(line);
  }

  // Place each card radially
  state.circle.forEach((cid, idx) => {
    const card = CARDS[cid];
    const angle = (idx / n) * 2 * Math.PI - Math.PI / 2; // top = 12 o'clock
    const px = cx + radius * Math.cos(angle) - halfCard;
    const py = cy + radius * Math.sin(angle) - halfCard;

    const el = document.createElement('div');
    el.className = 'circle-card' + (isDraftPhase ? ' clickable' : '');
    el.style.cssText = `position:absolute;left:${px}px;top:${py}px;display:grid;grid-template-columns:var(--cell-size) var(--cell-size);grid-template-rows:var(--cell-size) var(--cell-size);`;

    // Card label
    const label = document.createElement('span');
    label.className = 'card-label';
    label.textContent = `#${cid}`;
    el.appendChild(label);

    // 4 cells
    for (let j = 1; j >= 0; j--)
      for (let i = 0; i < 2; i++) {
        const [t, ic] = tileAt(card, i, j, false);
        el.appendChild(makeCell(t, ic));
      }

    if (isDraftPhase) {
      el.addEventListener('click', () => selectDraft(idx));
    }

    // Selected / skipped state
    if (selectedDraftOffset !== null) {
      if (idx === selectedDraftOffset) {
        el.classList.add('selected');
      } else if (idx < selectedDraftOffset) {
        el.classList.add('skipped');
        const skip = document.createElement('span');
        skip.className = 'skip-label';
        skip.textContent = '\u2192 AI';
        el.appendChild(skip);
      }
    }

    circleContainer.appendChild(el);
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

  const isHumanPlacing = playerIdx === 0 && !busy &&
    (state.phase === Phase.PLACE_FREE || state.phase === Phase.PLACE_DRAFT) &&
    state.player === 0;

  // Empty town with no pending placement: show blank container
  if (m.size === 0 && !isHumanPlacing) {
    el.style.gridTemplateColumns = '';
    el.onmouseleave = null;
    return;
  }

  let { x0, x1, y0, y1 } = getTownBounds(m);

  if (isHumanPlacing && placementAnchors) {
    for (const k of placementAnchors) {
      const [ax, ay] = parseKey(k);
      if (ax < x0) x0 = ax;
      if (ax + 1 > x1) x1 = ax + 1;
      if (ay < y0) y0 = ay;
      if (ay + 1 > y1) y1 = ay + 1;
    }
  }

  x0 -= 1; y0 -= 1; x1 += 1; y1 += 1;
  const cols = x1 - x0 + 1;
  const rows = y1 - y0 + 1;

  el.style.display = 'grid';
  el.style.gridTemplateColumns = `repeat(${cols}, var(--cell-size))`;
  el.style.gridTemplateRows = `repeat(${rows}, var(--cell-size))`;

  const ghostCells = new Map();
  if (isHumanPlacing && ghostAnchor) {
    const [gx, gy] = ghostAnchor;
    const cardId = state.phase === Phase.PLACE_FREE ? state.free[0][0] : state.drafted;
    const card = CARDS[cardId];
    for (let i = 0; i < 2; i++)
      for (let j = 0; j < 2; j++)
        ghostCells.set(cellKey(gx + i, gy + j), tileAt(card, i, j, rot180));
  }

  for (let y = y1; y >= y0; y--) {
    for (let x = x0; x <= x1; x++) {
      const k = cellKey(x, y);
      const tile = m.get(k);
      const ghost = ghostCells.get(k);

      if (ghost) {
        const cell = makeCell(ghost[0], ghost[1]);
        cell.classList.add('ghost');
        // Ghost cells must be clickable to place the card
        if (isHumanPlacing && ghostAnchor) {
          cell.style.cursor = 'pointer';
          const [gx, gy] = ghostAnchor;
          cell.addEventListener('click', () => handlePlacement(gx, gy));
        }
        el.appendChild(cell);
      } else if (tile) {
        el.appendChild(makeCell(tile[0], tile[1]));
      } else {
        const cell = document.createElement('div');
        cell.className = 'cell empty-cell';
        if (isHumanPlacing && placementAnchors && placementAnchors.has(k)) {
          cell.classList.add('anchor-highlight');
          cell.addEventListener('click', () => handlePlacement(x, y));
          cell.addEventListener('mouseenter', () => { ghostAnchor = [x, y]; renderTown(0); });
          cell.addEventListener('mouseleave', () => { ghostAnchor = null; renderTown(0); });
        }
        el.appendChild(cell);
      }
    }
  }

  // Make occupied/empty cells within anchor footprints clickable + highlighted
  if (isHumanPlacing && placementAnchors) {
    const allCells = el.children;
    let cellIdx = 0;
    for (let y = y1; y >= y0; y--) {
      for (let x = x0; x <= x1; x++) {
        const cell = allCells[cellIdx++];
        if (cell.classList.contains('anchor-highlight') || cell.classList.contains('ghost')) continue;
        for (const [dx, dy] of [[0,0],[-1,0],[0,-1],[-1,-1]]) {
          const anchorKey = cellKey(x + dx, y + dy);
          if (placementAnchors.has(anchorKey)) {
            cell.style.cursor = 'pointer';
            cell.classList.add('footprint-cell');
            const ax = x + dx, ay = y + dy;
            cell.addEventListener('click', () => handlePlacement(ax, ay));
            cell.addEventListener('mouseenter', () => { ghostAnchor = [ax, ay]; renderTown(0); });
            cell.addEventListener('mouseleave', () => { ghostAnchor = null; renderTown(0); });
            break;
          }
        }
      }
    }
  }

  // Clear ghost when mouse leaves the town grid entirely
  if (isHumanPlacing) {
    el.onmouseleave = () => {
      if (ghostAnchor) { ghostAnchor = null; renderTown(0); }
    };
  } else {
    el.onmouseleave = null;
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

    const terrRow = document.createElement('div');
    terrRow.className = 'score-row';
    terrRow.innerHTML = `<span class="score-label">Terrain</span><span class="score-val">${breakdown.terrain}</span>`;
    el.appendChild(terrRow);

    for (const name of state.bonusNames) {
      if (!name) continue;
      const val = breakdown[name] || 0;
      const row = document.createElement('div');
      row.className = 'score-row';
      row.innerHTML = `<span class="score-label">${name}</span><span class="score-val">${val > 0 ? '+' : ''}${val}</span>`;
      if (val === 0) row.classList.add('score-zero');
      el.appendChild(row);
    }

    const totalRow = document.createElement('div');
    totalRow.className = 'score-row total';
    const diff = idx === 0 ? s1 - s2 : s2 - s1;
    const diffStr = diff > 0 ? ` (+${diff})` : diff < 0 ? ` (${diff})` : '';
    totalRow.innerHTML = `<span class="score-label">Total</span><span class="score-val">${total}${diffStr}</span>`;
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

function setStatus(html) {
  statusBar.innerHTML = html;
}

// ============================================================================
// Placement logic
// ============================================================================

function computePlacementAnchors() {
  if (!state || state.player !== 0) { placementAnchors = null; return; }
  if (state.phase !== Phase.PLACE_FREE && state.phase !== Phase.PLACE_DRAFT) {
    placementAnchors = null; return;
  }
  placementAnchors = candidateAnchors(state.towns[0]);
}

function showPlacementUI() {
  const isFree = state.phase === Phase.PLACE_FREE;
  if (isFree && state.free[0].length === 0) return; // no free cards to place
  const cardId = isFree ? state.free[0][0] : state.drafted;
  if (cardId === undefined || cardId < 0) return; // invalid card
  const freeCount = isFree ? state.free[0].length : 0;
  placementPanel.style.display = '';
  placementPanel.classList.remove('hidden');
  placementTitle.textContent = isFree
    ? `Place Free Card #${cardId} (${freeCount} left)`
    : `Place Card #${cardId}`;
  renderCardPreview(cardId, rot180);
  computePlacementAnchors();
  setStatus(`Click a highlighted cell to place card <b>#${cardId}</b>. Press <b>R</b> to rotate.`);
}

function hidePlacementUI() {
  placementPanel.classList.add('hidden');
  placementAnchors = null;
  ghostAnchor = null;
}

function handlePlacement(ax, ay) {
  if (busy || state.player !== 0) return;
  const action = [ax, ay, rot180];
  const isFree = state.phase === Phase.PLACE_FREE;
  const cardId = isFree ? state.free[0][0] : state.drafted;
  const label = isFree ? 'free card' : 'card';
  log(`You place ${label} #${cardId} at (${ax},${ay})${rot180 ? ' rotated' : ''}`, 0);
  stateHistory.push(state);
  hidePlacementUI();
  state = applyAction(state, action);
  rot180 = false;
  rotateBtn.classList.remove('active');
  afterAction();
}

// ============================================================================
// Draft logic
// ============================================================================

function selectDraft(offset) {
  if (busy || state.player !== 0 || state.phase !== Phase.DRAFT) return;
  if (offset < 0 || offset >= state.circle.length) return;
  selectedDraftOffset = offset;
  draftControls.style.display = '';
  draftControls.classList.remove('hidden');

  // Show skip warning
  if (offset === 0) {
    draftInfo.textContent = 'Taking the first card (no cards given to AI).';
    draftInfo.className = 'draft-info-ok';
  } else {
    draftInfo.textContent = `Skipping ${offset} card${offset > 1 ? 's' : ''} to AI!`;
    draftInfo.className = offset >= 3 ? 'draft-info-danger' : 'draft-info-warn';
  }

  renderCircle();
}

function confirmDraft() {
  if (selectedDraftOffset === null) return;
  if (selectedDraftOffset >= state.circle.length) return;
  const offset = selectedDraftOffset;
  const cardId = state.circle[offset];
  let msg = `You draft card #${cardId}`;
  if (offset > 0) msg += ` (giving ${offset} card${offset > 1 ? 's' : ''} to AI)`;
  log(msg, 0);
  stateHistory.push(state);
  draftControls.classList.add('hidden');
  draftInfo.textContent = '';
  selectedDraftOffset = null;
  state = applyAction(state, { type: 'draft', offset });
  afterAction();
}

function cancelDraft() {
  selectedDraftOffset = null;
  draftControls.classList.add('hidden');
  draftInfo.textContent = '';
  renderCircle();
}

// ============================================================================
// AI turn
// ============================================================================

async function aiTurn() {
  busy = true;
  renderAll();
  await delay(100);

  while (!state.isTerminal() && state.player === 1) {
    const isDraft = state.phase === Phase.DRAFT;
    if (isDraft) {
      setStatus('AI is thinking...');
      await delay(50); // let the status render before heavy computation
    }

    const t0 = performance.now();
    const action = aiType === 'lookahead'
      ? pickActionLookahead(state, state.bonusNames)
      : pickActionGreedy(state, state.bonusNames);
    const elapsed = performance.now() - t0;
    if (action === null) break;

    if (action.type === 'draft') {
      const cardId = state.circle[action.offset];
      let msg = `AI drafts card #${cardId}`;
      if (action.offset > 0) msg += ` (skipping ${action.offset} to you)`;
      msg += ` [${(elapsed/1000).toFixed(1)}s]`;
      log(msg, 1);
    } else {
      const [ax, ay, r] = action;
      const isFree = state.phase === Phase.PLACE_FREE;
      const cardId = isFree ? state.free[1][0] : state.drafted;
      const label = isFree ? 'free card' : 'card';
      log(`AI places ${label} #${cardId} at (${ax},${ay})${r ? ' rotated' : ''}`, 1);
      if (isFree) {
        setStatus(`AI placing free cards (${state.free[1].length} left)...`);
      }
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
  if (!state) return;
  if (state.isTerminal()) {
    hidePlacementUI();
    renderAll();
    showEndModal();
    return;
  }

  // Set up placement UI (and anchors) BEFORE rendering so renderTown uses them
  if (state.player === 0 &&
      (state.phase === Phase.PLACE_FREE || state.phase === Phase.PLACE_DRAFT)) {
    showPlacementUI();
  } else {
    hidePlacementUI();
  }

  renderAll();

  if (state.player === 0) {
    if (state.phase === Phase.DRAFT) {
      setStatus('Your turn: <b>Draft</b> a card from the circle.');
    }
    // Placement status was set by showPlacementUI
  } else {
    aiTurn();
  }
}

function renderAll() {
  renderCircle();
  renderTown(0);
  renderTown(1);
  renderScores();
  updateTurnBadges();
}

function updateTurnBadges() {
  if (!state) return;
  const headers = [
    townEls[0].parentElement.querySelector('h2'),
    townEls[1].parentElement.querySelector('h2'),
  ];
  headers[0].innerHTML = 'Your Town (P1)' +
    (state.player === 0 && !state.isTerminal() ? ' <span class="turn-badge">YOUR TURN</span>' : '');
  headers[1].innerHTML = 'AI Town (P2)' +
    (state.player === 1 && !state.isTerminal() ? ' <span class="turn-badge">AI TURN</span>' : '');
}

// ============================================================================
// End modal
// ============================================================================

function showEndModal() {
  const [s1, s2] = computeScores(state.towns[0], state.towns[1], state.bonusNames);
  const [b1, b2] = computeScoreBreakdown(state.towns[0], state.towns[1], state.bonusNames);
  const diff = s1 - s2;
  let result;
  if (s1 > s2) result = '<div class="winner">You win!</div>';
  else if (s2 > s1) result = '<div class="winner">AI wins!</div>';
  else result = '<div class="winner">It\'s a tie!</div>';

  let breakdown = `${result}<br>`;
  breakdown += `<div style="text-align:left;font-size:0.85rem;margin:0.5rem auto;max-width:250px">`;
  breakdown += `<div style="display:flex;justify-content:space-between;padding:2px 0"><span></span><span style="color:#7ec8e3">You</span><span style="color:#ff8a80">AI</span></div>`;
  breakdown += `<div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #444"><span>Terrain</span><span style="color:#7ec8e3">${b1.terrain}</span><span style="color:#ff8a80">${b2.terrain}</span></div>`;
  for (const name of state.bonusNames) {
    if (!name) continue;
    const v1 = b1[name] || 0, v2 = b2[name] || 0;
    breakdown += `<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:0.8rem"><span>${name}</span><span style="color:#7ec8e3">${v1}</span><span style="color:#ff8a80">${v2}</span></div>`;
  }
  breakdown += `<div style="display:flex;justify-content:space-between;padding:4px 0;border-top:1px solid #444;font-weight:700"><span>Total</span><span style="color:#7ec8e3">${s1}</span><span style="color:#ff8a80">${s2}</span></div>`;
  breakdown += `</div>`;

  endScores.innerHTML = breakdown;
  endModal.classList.remove('hidden');
  endModal.style.display = '';
  setStatus('Game over!');
  log(`Game over. You: ${s1}, AI: ${s2} (${diff >= 0 ? '+' : ''}${diff}). ${s1 > s2 ? 'You win!' : s2 > s1 ? 'AI wins!' : 'Tie!'}`, null);
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
  stateHistory = [];
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

const undoBtn = $('undo-btn');
const hintBtn = $('hint-btn');
newGameBtn.addEventListener('click', startGame);
endCloseBtn.addEventListener('click', () => {
  // Increment seed so "Play Again" gives a new game
  seedInput.value = (parseInt(seedInput.value) || 42) + 1;
  startGame();
});
draftConfirmBtn.addEventListener('click', confirmDraft);
draftCancelBtn.addEventListener('click', cancelDraft);
undoBtn.addEventListener('click', undoAction);
hintBtn.addEventListener('click', showHint);

rulesToggleBtn.addEventListener('click', () => {
  rulesPanel.classList.toggle('hidden');
});
rulesCloseBtn.addEventListener('click', () => {
  rulesPanel.classList.add('hidden');
});

function doRotate() {
  if (!state) return;
  const isFree = state.phase === Phase.PLACE_FREE;
  const cardId = isFree ? state.free[0]?.[0] : state.drafted;
  if (cardId === undefined || cardId < 0) return;
  rot180 = !rot180;
  rotateBtn.classList.toggle('active', rot180);
  renderCardPreview(cardId, rot180);
  if (ghostAnchor) renderTown(0);
}

rotateBtn.addEventListener('click', doRotate);

document.addEventListener('keydown', (e) => {
  if ((e.key === 'r' || e.key === 'R') && !placementPanel.classList.contains('hidden') &&
      e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
    doRotate();
  }
  // Enter to confirm draft or placement, Escape to cancel
  if (e.key === 'Enter') {
    if (selectedDraftOffset !== null) confirmDraft();
    else if (ghostAnchor) handlePlacement(ghostAnchor[0], ghostAnchor[1]);
  }
  if (e.key === 'Escape') {
    if (selectedDraftOffset !== null) cancelDraft();
    if (!rulesPanel.classList.contains('hidden')) rulesPanel.classList.add('hidden');
    if (!endModal.classList.contains('hidden')) endModal.classList.add('hidden');
  }
  // Ctrl+Z to undo
  if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
    e.preventDefault();
    undoAction();
  }
  // H for hint (but not when typing in input fields)
  if ((e.key === 'h' || e.key === 'H') && !e.ctrlKey && !e.metaKey &&
      e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
    showHint();
  }
});

// ============================================================================
// Helpers
// ============================================================================

function showHint() {
  if (busy || !state || state.player !== 0 || state.isTerminal()) return;
  busy = true;
  setStatus('Computing hint...');
  hintBtn.classList.add('hint-thinking');
  document.body.style.cursor = 'wait';

  // Use setTimeout to let the status render before computation
  setTimeout(() => {
    const action = pickActionLookahead(state, state.bonusNames);
    busy = false;
    hintBtn.classList.remove('hint-thinking');
    document.body.style.cursor = '';
    if (!action) { setStatus('No hint available.'); return; }

    if (action.type === 'draft') {
      // Highlight the suggested card in the circle
      selectDraft(action.offset);
      log(`Hint: draft card #${state.circle[action.offset]}${action.offset > 0 ? ` (skip ${action.offset})` : ''}`, null);
    } else {
      const [ax, ay, r] = action;
      // Apply the rotation and show ghost at the suggested position
      rot180 = r;
      rotateBtn.classList.toggle('active', rot180);
      const isFree = state.phase === Phase.PLACE_FREE;
      const cardId = isFree ? state.free[0][0] : state.drafted;
      renderCardPreview(cardId, rot180);
      ghostAnchor = [ax, ay];
      renderTown(0);
      log(`Hint: place at (${ax},${ay})${r ? ' rotated' : ''}`, null);
    }
    setStatus('Hint shown. Click to accept, or choose a different move.');
  }, 50);
}

function undoAction() {
  if (busy || stateHistory.length === 0) return;
  state = stateHistory.pop();
  rot180 = false;
  rotateBtn.classList.remove('active');
  selectedDraftOffset = null;
  ghostAnchor = null;
  draftControls.classList.add('hidden');
  log('(undo)', null);
  hidePlacementUI();
  afterAction();
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Auto-start on load
startGame();
