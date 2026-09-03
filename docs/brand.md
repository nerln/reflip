# The mark, the colour, the name

## The mark

A coin, caught mid-flip: an ellipse squashed on its vertical axis, with a thin bright
rim on the leading edge. Nothing else in the frame.

It is the whole idea of the tool in one shape. The watermark is a coin the model
flipped for every word, weighted so heads comes up too often. reflip changes enough
words that every coin is thrown again, unweighted, and the weighting is gone. A coin
in the air has not landed yet, which is the state the detector is left in.

Two drawings were tried and dropped. A pair of quotation marks facing away from each
other said "rewriting" and could have belonged to any text tool. A fingerprint with a
gap in it read as a security product, and it also promised erasure of something the
tool cannot see. The coin promises only what happens: a fresh throw.

The drawing lives twice, in `docs/img/mark.svg` and in `macapp/Tools/make-icon.swift`,
the same shape in two languages. They change together. The icon is generated at build
time rather than committed, so a clone has the code that draws it and not a binary
nobody can review.

## Colour

| Role | Value | Where it is used |
| --- | --- | --- |
| Ink | `#0C1112` | The page, the icon's ground |
| Rim | `#D8B65C` | The coin's edge, one accent per screen |
| Paper | `#ECEDE9` | Text on ink, the coin's face |
| Warn | `#C4685E` | The one red the site is allowed |

The greys carry a little blue and green. A neutral grey next to the rim reads as dead,
and the rim itself has to look like metal rather than like yellow.

The application uses none of these. It draws in the system's semantic colours so that
it follows the machine into dark mode without being asked, and so a person who has
changed their accent colour sees their own. The palette is for the website and the
icon, which are the only places the tool gets to have an opinion about colour.

## The name

reflip. The verb for what the tool does to each of the detector's coins, and short
enough to type in front of a pipe. Lowercase everywhere in running text, `Reflip.app`
only for the bundle.

`unmark` was the first name and is taken on the package index by a tool that removes
pen marks from scanned PDFs. Two other repositories on GitHub already carry it for
this exact purpose, which is a good reason to be somewhere else.
