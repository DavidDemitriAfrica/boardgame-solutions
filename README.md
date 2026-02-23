# Board Game Solutions

Exact and approximate solvers for recently released board games, with playable web demos.

Part of a research project exploring computational complexity and optimal play in modern tabletop games.

## Games

### Circle the Wagons

A two-player micro card game by Steven Aramini, Danny Devine, and Paul Shortino (Button Shy Games). Players draft cards from a shared circle and build overlapping frontier towns, scoring for terrain majorities and three bonus cards.

**[Play in your browser](https://daviddemitriafrica.github.io/boardgame-solutions/circle-the-wagons/web/)** against the AI.

**Solver** (`circle-the-wagons/solver.py`):
- Complete game engine with all 18 territory cards and 18 bonus scoring rules
- Four agents: Random, Greedy (1-ply), Lookahead (draft minimax + greedy placements), MCTS
- Alpha-beta endgame solver (~5,000 nodes/s)
- Lookahead beats Greedy 72% over 50 games (36-14, avg +2.7), both crush Random 100%
- Draft minimax with alpha-beta pruning: 3-ply at ≤6 cards, 2-ply at ≤8, 1-ply otherwise
- Greedy placement uses mutate-evaluate-undo for zero-copy scoring
- Game analysis mode with bonus power rankings, drafting patterns, card popularity

**Web demo** (`circle-the-wagons/web/`):
- Vanilla JS/HTML/CSS, runs entirely client-side
- Game engine ported from Python with full scoring parity
- Easy (Greedy) and Hard (Lookahead) difficulty levels
- Undo support (Ctrl+Z), AI hints (H), score breakdowns
- Cards displayed in a circle matching the physical game layout

## Running the solver

```bash
cd circle-the-wagons

# Print all 18 cards for verification
python solver.py --verify-cards

# Play a full game (Lookahead vs Lookahead)
python solver.py --play --seed 42

# Benchmark agents over N games
python solver.py --benchmark -n 50 --seed 1

# Exact endgame solving demo
python solver.py --endgame --seed 42

# Detailed game statistics + bonus power rankings
python solver.py --analyze -n 50 --seed 1

# Starting position advantage analysis
python solver.py --openings -n 50 --seed 1
```

## Game statistics (from `--analyze` and `--openings`)

- **First-mover advantage**: P1 wins ~65% (Lookahead vs Lookahead, 20 games)
- **Starting position swing**: ~5.4 utility points — P2's choice of starting position matters
- **Branching factor**: ~80 for placements, ~10 for drafts
- **Avg game length**: ~9.6 draft decisions, ~30 total actions
- **Scoring**: terrain ~30 pts, bonuses ~15 pts per player
- **Strongest bonuses**: TARGET PRACTICE (+28), COOL WATER (+24), BOOM OR BUST (+19)
- **Weakest bonuses**: ONE TOO MANY (-1), CIRCLE THE WAGONS (+3), FORTIFIED (+3.5)

## Project structure

```
circle-the-wagons/
  solver.py          # Game engine + all agents + CLI (~2100 lines)
  assets/            # PNP PDF and rules image
  web/
    index.html       # Playable web version
    game.js          # JS port of game engine
    ai.js            # Greedy + Lookahead agents
    ui.js            # DOM rendering + game flow
    style.css        # Dark theme, colorblind-friendly terrain colors
```
