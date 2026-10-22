Claude's text has carried an invisible watermark since August. It is not a hidden character. It is a tilt in which words got picked. Only Anthropic holds the secret that reads it. Every "watermark remover" site deletes hidden characters. That changes nothing. I measured it.
---
How the check works. For each word it takes the four words before it and flips a coin with that secret. Watermarked text comes out heads more often than tails. Change one word, and the coins for it and the next four are flipped fresh. One edit every five words should do.
---
Nobody outside Anthropic can test against their secret. I ran the published method with my own secret on a small AI at home and watermarked 24 texts. Deleting hidden characters: no change. Word-swap rules alone: a small dent. A rewrite by that small AI: 22 of 24 read as clean.
---
Then I counted what the rewrites got wrong: a figure dropped, a name lost, "most" turned into "all". The full rewrite changed 33 of those per thousand words. Now it asks again when one changes, and gets 25. Changing one word in three, kept off those words, gets 5.
---
The reverse: did a machine write this? I wrote the rules down first, then tested on 3,520 human texts and 432 machine ones in three languages. It gives a verdict only on long English texts, and says why everywhere else. Texts my own tool rewrote mostly got past it.
---
All of it also runs in a browser tab, on your own device. While it works on your text, the page cuts its own network access, and a test fails if anything gets out. It counts page visits and which tool was used. Never the text.
---
reflip is open source. Every number above, and how to get it again:
github.com/nerln/reflip
Try it in your browser: nerln.github.io/reflip/app
