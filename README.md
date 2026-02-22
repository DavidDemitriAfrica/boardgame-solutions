# Board Game Solutions

Exact and approximate solvers for recently released board games, with playable web demos.

Part of a research project exploring computational complexity and optimal play in modern tabletop games.

## Games

### Circle the Wagons

A two-player micro card game by Steven Aramini, Danny Devine, and Paul Shortino (Button Shy Games). Players draft cards from a shared circle and build overlapping frontier towns, scoring for terrain majorities and three bonus cards.

**[Play in your browser](https://daviddemitriafrica.github.io/boardgame-solutions/circle-the-wagons/web/)** against the Lookahead AI.

**Solver** (`circle-the-wagons/solver.py`):
- Complete game engine with all 18 territory cards and 18 bonus scoring rules
- Four agents: Random, Greedy (1-ply), Lookahead (draft-aware greedy), MCTS
- Alpha-beta endgame solver with transposition table
- Lookahead beats Greedy 64% (32-15-3 over 50 games), both crush Random

**Web demo** (`circle-the-wagons/web/`):
- Vanilla JS/HTML/CSS, runs entirely client-side
- Game engine ported from Python with full scoring parity
- Play as P1 against Greedy or Lookahead AI
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
```

## Project structure

```
circle-the-wagons/
  solver.py          # Game engine + all agents + CLI
  assets/            # PNP PDF and rules image
  web/
    index.html       # Playable web version
    game.js          # JS port of game engine
    ai.js            # Greedy + Lookahead agents
    ui.js            # DOM rendering + game flow
    style.css        # Dark theme, colorblind-friendly terrain colors
```
