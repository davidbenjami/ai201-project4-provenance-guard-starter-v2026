"""
Signal two: the style signal. ← YOU BUILD THIS IN MILESTONE 4

Signal one reads the text for meaning. This one measures it *as text* — the
shape of it, without understanding a word.

Three measures are stubbed below because the brief names those three. They are
stubs, not implementations: what they compute is yours, and so is how you
combine them.

    sentence_length_spread   do sentences vary in length, or march in step?
    type_token_ratio         how much of the vocabulary repeats?
    punctuation_density      how much punctuation, and how varied?

Why these might differ between human and AI writing: generated prose tends
toward even, mid-length sentences and a narrower band of vocabulary, because
that's what "most likely next word" produces on average. Human writing is
lumpier — a three-word sentence next to a forty-word one.

⚠️ **The blind spot, which you have to name in Milestone 1.**

This signal cannot read. It has no idea what the text says. Anything that
changes the shape without changing the substance moves it — adding typos,
breaking up sentences, pasting in a quotation. That is a very cheap thing for
someone to do on purpose, and unit 8's attack set will do it to you.

Build each function on its own and call it from a terminal before you wire
anything together:

    python stylometry.py "some text to look at"
"""

import re
import statistics


def sentences(text: str) -> list[str]:
    """Split into sentences. Rough and good enough — given to you."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


def words(text: str) -> list[str]:
    """Split into lowercase words, punctuation stripped. Given to you."""
    return re.findall(r"[a-z0-9']+", text.lower())


# ── The three measures — YOU BUILD THESE ─────────────────────────────────────

def sentence_length_spread(text: str) -> float:
    """
    How much sentence length varies.

    Returns:
        A float. Decide yourself what scale it's on and which direction means
        "more human" — then write that down, because your combining rule
        depends on knowing it.

    A hint on what you're reaching for: the standard deviation of sentence
    lengths, probably divided by the mean so a long text and a short one are
    comparable. `statistics.stdev` is imported for you.

    Watch the edge case: a one-sentence submission has no spread at all, and
    `stdev` raises on fewer than two values. Decide what that should return
    before the attack set decides for you.

    My choice: coefficient of variation (stdev / mean) of words per sentence.
    Roughly 0.2 for prose that marches in step, 0.7+ for lumpy prose. Higher
    means more human. Fewer than two sentences returns 0.0 — there is no
    spread to measure — and `style_signal` treats that as "no evidence", not
    as "AI".
    """
    lengths = [len(words(s)) for s in sentences(text)]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 2:
        return 0.0
    return round(statistics.stdev(lengths) / statistics.mean(lengths), 4)


def type_token_ratio(text: str) -> float:
    """
    Unique words over total words.

    Returns:
        A float between 0 and 1. Higher means more varied vocabulary.

    Worth knowing before you rely on it: this measure falls as text gets
    longer, because common words repeat. Two texts of different lengths aren't
    directly comparable on it, and if your test inputs vary a lot in length,
    that alone can look like a signal.

    My choice: a moving-average TTR over 50-word windows, which keeps a long
    text and a short one comparable. Under 50 words it falls back to plain
    TTR. Empty text returns 0.0.
    """
    tokens = words(text)
    if not tokens:
        return 0.0
    window = 50
    if len(tokens) <= window:
        return round(len(set(tokens)) / len(tokens), 4)
    ratios = [
        len(set(tokens[i:i + window])) / window
        for i in range(len(tokens) - window + 1)
    ]
    return round(statistics.mean(ratios), 4)


def punctuation_density(text: str) -> float:
    """
    How much punctuation, relative to length.

    Returns:
        A float. Whether you count all punctuation or only some kinds — commas,
        semicolons, dashes — is a real choice. Semicolons and em dashes are
        more interesting than full stops, because they vary more between
        writers.

    My choice: only the marks that vary between writers — ; : ( ) ! ? and
    dashes — per 100 words. Full stops and commas are left out because every
    writer, human or model, uses them at about the same rate. Higher means
    more human. Empty text returns 0.0.
    """
    n_words = len(words(text))
    if n_words == 0:
        return 0.0
    marks = re.findall(r"[;:()!?\u2014\u2013]|(?<=\s)-(?=\s)|--", text)
    return round(100 * len(marks) / n_words, 4)


# ── Combining them ───────────────────────────────────────────────────────────

def style_signal(text: str) -> float:
    """
    The style signal as a 0–1 score. **Higher means more likely AI.**

    Combine your three measures into one number. Same direction as
    `detector.model_signal`, so that `scoring.combine_signals` can treat them
    the same way — if one of your signals runs backwards, everything above it
    is wrong in a way that's hard to see.

    Two things to decide and write down:

      1. Which direction each measure points. Low spread means more AI-ish, so
         it needs flipping. Work out which of your three need that.
      2. How to get each onto a comparable scale. A raw type-token ratio sits
         between 0 and 1; a raw punctuation count doesn't. Adding them
         unscaled means whichever has the bigger numbers wins by default.

    Test it on the four calibration inputs from Milestone 4 — clearly AI,
    clearly human, plain conventional human writing, lightly-edited AI — before
    you trust it. Plain and ordinary, not formal: formal prose reads as *human*
    to signal one, and it is plain writing that gets accused.

    My rule. All three measures point "higher = more human", so each is
    flipped and mapped linearly onto 0-1 between two calibration ends, then
    clipped:

        spread       0.25 -> 1.0 (AI-ish)    0.75 -> 0.0 (human-ish)
        TTR          0.75 -> 1.0             0.90 -> 0.0
        punctuation  0.0  -> 1.0             3.0  -> 0.0   (per 100 words)

    Weighted 0.5 spread, 0.3 punctuation, 0.2 TTR. Spread gets the most
    weight because it is the measure the brief's argument rests on. TTR gets
    the least because on my calibration inputs it barely separated anything:
    the clearly-AI paragraph had a HIGHER ratio than the plain human one.
    With fewer than two sentences, spread is unmeasurable and counts as 0.5.
    """
    def flip(value, ai_end, human_end):
        return min(max((human_end - value) / (human_end - ai_end), 0.0), 1.0)

    if len(sentences(text)) < 2:
        spread = 0.5
    else:
        spread = flip(sentence_length_spread(text), 0.25, 0.75)
    ttr = flip(type_token_ratio(text), 0.75, 0.90)
    punct = flip(punctuation_density(text), 0.0, 3.0)

    return round(0.5 * spread + 0.2 * ttr + 0.3 * punct, 4)


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or (
        "The system works well. It handles most cases correctly and provides "
        "good results. Users generally find it easy to use and understand."
    )

    print(f"{len(sentences(text))} sentences, {len(words(text))} words\n")
    print(f"sentence_length_spread   {sentence_length_spread(text)}")
    print(f"type_token_ratio         {type_token_ratio(text)}")
    print(f"punctuation_density      {punctuation_density(text)}")
    print(f"style_signal             {style_signal(text)}   (higher = more likely AI)")
