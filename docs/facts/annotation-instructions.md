# Instructions for the annotators

You are given pairs of paragraphs: an ORIGINAL and a REWRITE of it. The rewrite was meant to
say the same thing in other words. For each pair, report what the rewrite changed in its
facts. Read both carefully; judge meaning, not wording.

Report, for each pair:

1. **numbers**: every number in the original that is missing from the rewrite, and every
   number in the rewrite that is not in the original. A number is the same whether written in
   digits or words ("12" and "twelve", "3 million" and "three million", "trecentoquarantacinque"
   and "345"). Percentages, years and amounts are numbers. Write each as digits.
2. **names**: names of people, places, organisations, products, works or events present in one
   text and absent from the other. A name that only moved, changed case, or took an apostrophe
   style is the same name. Ordinary capitalised words (the first word of a sentence, a heading
   in Title Case) are not names.
3. **negation**: `true` if a statement's polarity flipped, because a negation (not, never, no,
   none, without, non, mai, nessuno, no, nunca, nadie, sin...) was lost or added in a way that
   reverses what is said. A negation reworded with the same meaning ("did not report" and
   "reported no") is not a flip.
4. **quantifiers**: quantifiers whose strength changed: all, every, most, many, some, few,
   only, at least, at most, more than, less than, about, always, often, sometimes, rarely and
   their equivalents in Italian and Spanish. List each change as "before -> after"; a
   quantifier that disappeared or appeared counts too.
5. **other**: any other change of meaning a careful reader would object to, one short line
   each: a claim added, a claim dropped, a cause turned into a correlation, a different subject,
   a different time. Not style, not word order, not a synonym.

If nothing changed in a category, give an empty list (or `false` for negation). Do not guess:
when you are unsure whether something counts, leave it out and say why in `notes`.
