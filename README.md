# A Little Christmas

A snowy, softly shaded ASCII Christmas tree that builds itself in your terminal.
The branches grow from the ground up, a single golden garland winds around the
tree, sixteen colored baubles fly into place one at a time, and a shining star
arrives last. Snow keeps falling over the finished scene. Uneven branch layers,
directional needle sprays, and shaded undersides give the fir a more natural
shape. Glossy baubles have lit rims, reflections, and shadows; larger terminals
give them room for fuller rounded bodies.

Requires **Python 3.10+**. No packages to install.

```powershell
python christmas_tree.py
```

On Windows you can also double-click **start.bat**. Windows Terminal gives the
best colors. Make the window at least **40 columns by 22 rows**; **100 by 36** or
larger gives the branches and ornaments more room. Resize it while it runs.

The build takes about 30 seconds. The completed tree stays on screen until you
quit. Everything you see is an ASCII character; ANSI escape sequences provide
color and cursor movement.

| Key | Action |
| --- | --- |
| Space | Pause or resume |
| R | Replay from the seed |
| M | Toggle the optional Jingle Bells melody (Windows) |
| Q / Esc / Ctrl+C | Quit and restore the terminal |

```powershell
python christmas_tree.py --music           # Optional Windows melody
python christmas_tree.py --speed 2          # A quicker Christmas
python christmas_tree.py --once             # Build, enjoy eight seconds, exit
python christmas_tree.py --loop             # Keep rebuilding
python christmas_tree.py --no-color         # Monochrome ASCII
python christmas_tree.py --snapshot --time 13 --width 100 --height 36
```

Music uses Windows' built-in tone generator and stays silent on other systems.
The animation also runs on macOS and Linux terminals. Music is off by default.
`NO_COLOR` disables colors, and redirected output produces a single plain-text
frame instead of filling a file with animation frames. `--time` chooses that
frame; omit it for the finished tree.

Run the regression checks with `python -m unittest discover -v`.
