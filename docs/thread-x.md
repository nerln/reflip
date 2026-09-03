Claude's text has carried an invisible watermark since August. It is not a hidden character. It is a tilt in which words got picked. Only Anthropic holds the secret that reads it. Every "watermark remover" site deletes hidden characters. That changes nothing. I measured it.
---
How the check works. For each word it takes the four words before it and flips a coin with that secret. Watermarked text comes out heads more often than tails. Change one word, and the coins for it and the next four are flipped fresh. One edit every five words should do.
---
Nobody outside Anthropic can test against their secret. I ran the published method with my own secret on a small AI at home and watermarked 24 texts. Deleting hidden characters: no change. Word-swap rules alone: a small dent. A rewrite by that small AI: 23 of 24 read as clean.
---
What I did not expect: the careful version I built first, changing one word in three and keeping the rest, worked. It also cost more than a full rewrite by the same small AI, and read worse. So the default is the plain rewrite, checked afterwards. Nothing leaves the laptop.
---
reflip, open source, with the measurements and how to repeat them:
github.com/nerln/reflip
