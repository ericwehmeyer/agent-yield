# How to draw in this repo

Companion to `style.md`, which governs the prose. Same reader: tired, at the end
of a session, paying for the words.

Every example is a chart that was drawn in this repo and thrown away. Naming
them is the point.

---

## 1. A chart contains data or it is not a chart

The first figure on the cost page was a token axis with six threshold markers on
it. It had no data in it at all. Not one measured value was plotted. It was an
annotated ruler showing our own policy constants, drawn large.

Before drawing anything, answer: **which measurements are on this canvas?** If
the answer is none, you want a table, a sentence, or nothing.

## 2. Show the quantity as geometry, not as a label

The same figure carried its most important number, 89.6% of spending, as text
inside a shaded rectangle. The reader was told the number. The picture did not
show it.

If a number matters enough to put in a chart, it must be a **length, a position
or an area** the reader can measure against an axis. A number that only appears
as a caption belongs in the caption.

## 3. One figure, one sentence

Write the sentence first. If you cannot, you do not know what the figure is for.

> The alarm we had catches 4% of calls and 10% of the money.

That sentence is the caption's first line, in bold. Everything else in the
figure exists to let the reader check it.

A figure carrying three messages is three figures, or more often one figure and
two paragraphs.

## 4. Prefer the instrument that fits the claim

The claim was "a small share of calls makes most of the bill". That claim has a
standard instrument: a **concentration curve**, every observation ranked,
cumulative share against cumulative share. Using it turned an assertion into
something you read off an axis, and used all 20,255 measurements instead of
five summary numbers.

Before inventing a layout, ask what the claim is and whether a known form
already carries it: distribution, concentration, time series, small multiples,
a trade-off curve, or a table.

## 5. Do not draw the same thing twice

The number line asserted what the cumulative curve already proved. When two
figures make the same point, the weaker one goes, and the weaker one is usually
the one with less data in it.

## 6. Reference lines earn their place

The concentration curve carries a dotted diagonal: what the curve would look
like if every call cost the same. That line is not decoration. It is the null
hypothesis, drawn, so the reader can see how far the data departs from it.

Every rule, band and annotation on a chart must answer: **what would the reader
not know without it?** If there is no answer, erase it.

## 7. Colour has a job

- **Identity** (which series): distinct hues, fixed order, never recycled.
- **Magnitude** (how much): one hue, light to dark.
- **State** (good, bad): reserved, never reused for a series.

Run the palette through the validator rather than judging by eye. Two ramps in
this repo passed inspection and failed the contrast check at the light end.

## 8. Both themes, and the numbers keep their digits

Charts are read in light and dark. Take colours from tokens, never literals, so
a figure that works on paper still works at midnight.

Axis labels get real numbers with real separators. `249,257`, not `~250k`, when
the figure is measured.

## 9. Interactive means the reader can interrogate it

A static picture answers the question you thought of. Hover, a crosshair and a
readout let the reader ask their own. Every figure here shows the underlying
pair on hover, so a reader who distrusts the caption can check it.

## 10. Say what is measured and what is chosen

Same rule as the prose. On the cost page the curve is measured and the four
markers on it are chosen. The caption says so. A chart that mixes evidence and
policy without labelling which is which is an argument disguised as a
photograph.

---

## The three passes

Draw it, then review it three times, and treat them as different jobs.

1. **Is there data in it?** If not, stop. Rule 1.
2. **Does the geometry carry the message?** Cover the caption and look at the
   picture. If the message is gone, the caption was doing the work. Rule 2.
3. **Is anything here twice, or here for nothing?** Erase the redundant figure,
   the unearned annotation, the third message. Rules 5 and 6.

The first draft of the cost page failed all three. It took a reader saying *I
can't tell what the message is* to notice, which is the cheapest review
available and the one most often skipped.
