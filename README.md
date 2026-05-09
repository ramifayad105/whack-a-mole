# 🐹 Whack-a-Mole

A classic Whack-a-Mole arcade game built with Python and Pygame, packaged as a standalone Windows executable.

## Features

- 3×3 mole grid with smooth pop-up animations
- 60-second rounds with a live countdown timer
- Combo multiplier system — chain hits to rack up bigger points
- Difficulty scales over time — moles get faster and more appear at once
- Floating score popups, sound effects, and a high score tracker
- Menu, Game Over, and Play Again screens

## Download & Play

Grab `WhackAMole.exe` from the [`dist/`](dist/) folder and double-click — no install required.

## Run from Source

```bash
pip install pygame
python whackamole.py
```

## Build the Exe Yourself

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "WhackAMole" whackamole.py
```

## Controls

| Action | Input |
|--------|-------|
| Whack a mole | Left click |
| Return to menu | ESC |

## Tech Stack

- Python 3
- Pygame 2
- PyInstaller (for the exe)
