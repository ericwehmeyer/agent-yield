# How to write in this repo

Every document here is read by someone tired, at the end of a session, who is
paying for the words. Write accordingly.

The examples below are all real. They are taken from drafts written in this
repo and cut in review. Naming them is the point: a style guide with invented
examples teaches nothing.

---

## 1. Lead with the finding, not the approach

The first sentence carries the number. Not the method, not the context, not
what the document is about.

> **No.** "Every threshold we have measures the wrong thing."
>
> **Yes.** "We spent 3.02 billion tokens. 565 million of them bought nothing."

The first is a claim about our instruments. The second is a claim about money.
Readers care about the second and will read on to learn why.

If you cannot state the finding as a number in one sentence, you have not
finished the analysis. Go back and finish it.

## 2. What, so what, now what

Three movements, in that order, and nothing else.

- **What** — the measurement. Short, numbered, concrete.
- **So what** — what it costs, or saves, in the reader's units.
- **Now what** — what to do differently, tomorrow morning, specifically.

A document that stops after *what* is a lab notebook. A document that never
reaches *now what* has wasted the reader's time no matter how good the
analysis. Most drafts in this repo have died of this.

## 3. Omit needless words

Strunk's rule 17, and the one that does the most work.

| Cut | Keep |
|---|---|
| re-read from scratch on every single call | read again on every call |
| A call re-reads its entire context | A call reads its whole context |
| We went looking for a knee and there is none | We looked for a knee. There is none. |
| It climbs smoothly from the first call | It climbs from the first call |
| That is what was spent above the limits | That is what went above the limits |

Adverbs are the first thing to go. If the verb needs *smoothly* to carry the
meaning, find a better verb.

## 4. Do not tell the reader that something matters

Show the thing. The reader decides whether it matters.

> **No.** "That is a negative result and it matters."
>
> **Yes.** "We looked for a knee in the curve. There is none."

Related: never write *importantly*, *notably*, *crucially*, *it is worth
noting*. Cut the sentence or cut the word.

## 5. No worn phrases, no reaching

These were all cut from drafts here:

- "not the same animal"
- "fit on a napkin"
- "the two halves of one fact"
- "dressing a chosen number as a discovered one"

The last one is the most instructive. It is a decent line, and it is still
wrong, because it is the writer admiring the writing. If a sentence would
survive being moved to a different document about a different subject, it is
decoration. Cut it.

## 6. Say which numbers are measured and which are chosen

The distinction is the whole value of this repo, and it belongs in the prose,
not in a separate section of epistemic throat-clearing.

> The medians are measured. The limits (150,000, 250,000, 400,000) are chosen,
> anchored to the 31,618 a well-briefed agent costs.

Two sentences. An earlier draft spent a fourteen-line table on the same point.

The parentheses are deliberate. An earlier version of this rule used em dashes
here, which spent a whole document's budget under rule 9 on provenance
boilerplate. An editor caught the collision. Rules that contradict each other
get resolved in favour of the one a reader would notice.

## 7. Numbers get their real digits

Write **249,257**, not "about a quarter million", when the figure is measured.
Round only when rounding is the honest thing, and then say so. A rounded number
presented as exact is a small lie that costs the reader their trust in the
exact ones.

**Restating a figure loosely is allowed once the exact one is on the page.**
"It bills a quarter of a million tokens" is fine one sentence after 249,257,
because the reader can see what was rounded. "So halve it: still 280 million"
is fine after 565 million, because the arithmetic is in view. What is banned is
a round number with no exact one anywhere near it.

## 8. Report disagreement plainly, and leave the door open

When the code is wrong, say what is wrong, show the case that breaks it, and
propose the fix. Do not perform balance and do not perform certainty.

> A call carrying 200,000 tokens costs 200,000 tokens. Change the window to two
> million and the same call is cheap; change it to half a million and it is
> steep. The bill never moved.

Leave the door open at the end, and **write that sentence fresh every time.** A
fixed closing formula becomes a worn phrase by rule 5 on its second outing, and
a reader who has seen it twice stops reading it. Say what specifically would
change your mind about this specific claim.

## 9. Punctuation

- The em dash is a good tool and this repo abuses it. **Two per page.** Most
  are a colon, a full stop, or nothing.
- Italics for emphasis: rare. If the sentence needs italics to land, rewrite
  the sentence.
- Bold carries the claim a skimmer must not miss. One per paragraph at most.

## 10. Headings are sentences, not labels

> **No.** "Finding one" · "The proposal" · "Provenance"
>
> **Yes.** "Main sessions and subagents need different limits"

A reader should be able to read only the headings and come away with the
argument.

---

## The pass

Write it. Then edit it twice, and treat the two passes as different jobs:

1. **Structure.** Is the lede the finding? Does it reach *now what*? Cut whole
   paragraphs and sections. **Headings belong to this pass**, because rewriting
   a heading means rethinking what the section is for.
2. **Line.** Sentence by sentence, out loud. Cut adverbs, worn phrases,
   self-admiring lines, and every em dash past the second in the document.

The second pass is a different job from the first and does not work while the
structure is still moving. Do them in order.
