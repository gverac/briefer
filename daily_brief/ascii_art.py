"""A small curated gallery of ASCII art, cycled one piece per day.

Kept narrow (roughly <= 24 columns) so it stays legible on a 58mm roll. Each
entry is (name, art); the renderer draws it in a monospace font. Add your own
favourites (e.g. from asciiart.eu) to the GALLERY list.
"""

from __future__ import annotations

from datetime import date

# NOTE: raw strings + a leading/trailing newline so backslashes are literal and
# nothing sits immediately before the closing quotes.
GALLERY: list[tuple[str, str]] = [
    ("cat", r"""
 /\_/\
( o.o )
 > ^ <
"""),
    ("dog", r"""
 / \__
(    @\___
 /         O
/   (_____/
/_____/   U
"""),
    ("bunny", r"""
(\__/)
(='.'=)
(")_(")
"""),
    ("duck", r"""
  __
<(o )___
 ( ._> /
  `---'
"""),
    ("fish", r"""
   ><>
><(((o>
   ><>
"""),
    ("snail", r"""
    _......_
  .'  o     '.
 /  _________ \
 '-'         '-'
"""),
    ("coffee", r"""
   ( (
    ) )
 ........
 |      |]
 \      /
  `----'
"""),
    ("sun", r"""
   \ | /
 -- (_) --
   / | \
"""),
    ("heart", r"""
 _   _
( \_/ )
 \   /
  \ /
   v
"""),
    ("mushroom", r"""
  _____
 /     \
/ .   . \
\   ^   /
 \_____/
   | |
  /___\
"""),
    ("penguin", r"""
  .--.
 |o_o |
 |:_/ |
//   \ \
(|   | )
/'\_ _/`\
\___X___/
"""),
    ("robot", r"""
 .-------.
 |[o] [o]|
 |   >   |
 |  ---  |
 '-------'
  || | ||
"""),
    ("ghost", r"""
  .-.
 (o o)
 | O |
 |   |
  '~'~'
"""),
    ("tree", r"""
    /\
   /  \
  /    \
 /______\
    ||
    ||
"""),
    ("rocket", r"""
   /\
  |==|
  |  |
  |SS|
 /|  |\
/ |==| \
  /||\
 ` || `
"""),
    ("flower", r"""
  _.._
 .'    '.
:  o  o  :
 '.    .'
   '||'
    ||
  __||__
"""),
    ("whale", r"""
   .-'
'--./ /  _.---.
'-,  (__..-`    \
   \          . |
    `,.__.  ,__.-/
      '._/_.'__.-`
"""),
    ("star", r"""
    .
   .:.
  .:::.
.:::::::.
  ':::'
   ':'
"""),
]


def art_for(day: date) -> tuple[str, str]:
    """Pick (name, art) deterministically for the given date."""
    return GALLERY[day.toordinal() % len(GALLERY)]
