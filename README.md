# Provenance Guard

> ### 👋 Start here
>
> **New to this repo? Read [RUNNING.md](RUNNING.md) first.**
>
> Once `python test.py` passes, in one terminal:
>
> ```bash
> python app.py
> ```
>
> and in another:
>
> ```bash
> curl -X POST http://127.0.0.1:5000/ping \
>   -H "Content-Type: application/json" \
>   -d '{"message": "hello"}'
> ```
>
> That's a web service. Something sent it text and it sent something back.
> Everything this unit is filling in the middle.
>
> **The rest of this file is your submission.** Fill it in as you go.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     Unit 7 asks for the first five sections. Unit 8 adds the five below.

     Everything is pasted as TEXT. A pasted curl response gets full credit;
     a picture of your terminal gets none.
     ───────────────────────────────────────────────────────────────────────── -->

<!-- ═══════════════════════ UNIT 7 — THE BUILD ═══════════════════════ -->

## What This Does

1. **The request arrives.** A writer (or a site) sends `POST /submit` with
   `{"text": ..., "creator_id": ...}`. `app.py::submit` pulls both out.
2. **Bad input is refused.** Missing or non-string `text`, empty `text`, more
   than 20,000 characters, or too short to score (under 3 tokens) gets a 400
   or 413 with a plain-English message, and a `rejected` entry in the log.
   Nothing malformed reaches a signal.
3. **Signal one — the model.** `detector.model_signal` runs gpt2 locally and
   measures perplexity: how predictable the text is. Squashed to 0–1, higher
   = more AI-like.
4. **Signal two — the style.** `stylometry.style_signal` measures the shape:
   sentence-length spread, vocabulary variety, unusual punctuation. Also 0–1,
   higher = more AI-like.
5. **Combine.** `scoring.combine_signals` takes a 0.6/0.4 weighted average,
   and if the two signals disagree by more than 0.5, holds the result inside
   the unsure band.
6. **Label.** `scoring.score_to_label` turns the score into one of three
   sentences a reader sees.
7. **Log and answer.** `audit.log_decision` writes all nine fields to
   `logs/audit.jsonl` under a new `content_id`, and the response returns the
   id, guess, confidence, label and both signal scores. If the writer
   disagrees, `POST /appeal` with that id moves it to `under_review`.

---

## Signals and Scoring

### Signal one — the model signal

**What it measures:** Perplexity under gpt2 — how surprised a language model
is by each next word, averaged over the first 400 tokens. Low perplexity
(predictable) maps to a high score via a logistic curve centred on perplexity
45.

**Why that might differ between human and AI writing:** A language model
writes by repeatedly picking a likely next word, so its output is text a model
finds easy to predict. People make odder, more specific choices.

**What it can't see:** Who wrote it. Predictability is not authorship. Plain
writing in common words and short sentences (a second-language writer, a
younger writer, anyone writing simply on purpose) is as predictable as
machine text. My plain-human calibration paragraph scored **0.77**, close to
the clearly-AI paragraph's **0.91**. The reverse also happens: AI text asked
to be ornate or full of rare words reads as human.

### Signal two — the style signal

**What it measures:** The shape of the text, from three measures, each mapped
to 0–1 (higher = more AI-like) and weighted:

| Measure | What it is | AI-ish end → human-ish end | Weight |
|---|---|---|---|
| Sentence-length spread | stdev / mean of words per sentence | 0.25 → 0.75 | 0.5 |
| Punctuation density | `; : ( ) ! ?` and dashes per 100 words | 0 → 3 | 0.3 |
| Type-token ratio | moving-average TTR over 50-word windows | 0.75 → 0.90 | 0.2 |

One-sentence text has no spread, so that measure counts as a neutral 0.5
there, not as AI.

**Why that might differ between human and AI writing:** Generated prose tends
toward even, mid-length sentences with commas and full stops and little else.
Human writing is lumpier: a three-word sentence next to a forty-word one, an
aside in brackets, a dash.

**What it can't see:** Meaning. It reads no words. Anything that changes the
shape without changing the substance moves it: splitting AI sentences into
short and long ones, scattering in a few dashes or a question, adding typos
(which raise vocabulary variety). That's cheap to do on purpose. It also
shares signal one's victim: plain writing with even sentences and no
semicolons scored **0.93**, *more* AI-like than the AI paragraph (0.86).
And TTR barely separated anything in calibration, which is why it has the
smallest weight.

### The combining rule

**The rule:** Take a weighted average that leans on the model signal. If the
two signals disagree badly, don't let either confident label through: the
score is held inside the unsure band. Two methods that disagree that much
*is* uncertainty, and I'd rather say so than pick a side.

**The numbers:**
- `combined = 0.6 × model_score + 0.4 × style_score`
- if `|model_score − style_score| > 0.5`, clamp `combined` to 0.40–0.84
- Weights, the 0.5 limit and the thresholds are all in `config.py`

The model gets 0.6 because it separated my calibration inputs more cleanly and
because the style signal is the cheaper one to game.

**Where it lives:** `scoring.py::combine_signals`

**A case where my two signals split, and what my rule does with it:**

The lightly edited AI paragraph (I rewrote AI text with a dash, an "honestly"
and some uneven sentences):

| | model | style | combined | label |
|---|---|---|---|---|
| lightly edited AI | 0.726 | 0.351 | 0.576 | unsure |

The model still found it predictable, but the shape now looked human. They're
0.375 apart, under the 0.5 limit, so the plain average applies and lands in
the middle of the unsure band. That's the right answer, because it *is* a
mixed case.

The guard matters for wider splits, and checking it taught me something. I
swept every pair of scores from 0.00 to 1.00 in steps of 0.01. The guard
changes the label in 595 of those pairs, and **every one of them moves
"human" to "unsure"**. It never blocks an "AI" label, because with weights of
0.6/0.4, two signals more than 0.5 apart can't average up to 0.85 in the first
place. So in practice the rule says: *don't tell someone their writing is
clearly human when one of the two checks thinks it's AI* (for example model
0.10 and style 0.70, which averages to 0.34 but is reported as 0.40, unsure).
On the AI side, the high threshold does the protecting.

---

## Label Variants

| Label | Score range | The exact text a reader sees |
|---|---|---|
| high-confidence human | 0.00 – under 0.40 | "This reads like it was written by a person. We didn't find anything that suggests an AI tool wrote it." |
| unsure | 0.40 – under 0.85 | "We can't tell either way, so we're not making a call on this one. Our checks gave mixed results, which happens a lot with ordinary, plainly written work. This is not a finding that AI was used. If you'd like a person to look at it, you can ask for a review." |
| high-confidence AI | 0.85 – 1.00 | "This looks a lot like writing produced by an AI tool — two separate checks both pointed that way. These checks can be wrong. If you wrote this yourself, you can appeal and a person will look at it." |

All three are reachable. In the Sample Run below, the three submissions
produce one of each.

The AI threshold is high on purpose. My plain-human paragraph combined to
**0.83** and the clearly-AI one to **0.89**. Any AI threshold below 0.83
accuses the plain writer, so it sits at 0.85. That margin is thin, and I
expect unit 8 to find text on the wrong side of it.

**Why I worded the "unsure" one this way:**

The person most likely to see it is the plain writer from the blind spot:
someone who wrote every word and is being told a machine couldn't tell. So it
does four things: says plainly that we aren't deciding ("we're not making a
call"); gives a reason that isn't about them ("our checks gave mixed
results"); names the most likely innocent explanation ("happens a lot with
ordinary, plainly written work"); and says outright that it **is not a finding
that AI was used**. It ends by offering a person, not a re-score. It avoids
"suspicious", "flagged" and "may have been generated", because each of those
reads as an accusation with a hedge on it.

---

## Sample Run

**A submission**

```bash
$ curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "Artificial intelligence is transforming the way we live and work. It offers numerous benefits, including increased efficiency, improved decision-making, and enhanced productivity. However, it is important to consider the potential challenges and risks associated with its use. By addressing these concerns, we can ensure that artificial intelligence is used responsibly and ethically. Ultimately, the future of artificial intelligence depends on our ability to balance innovation with responsibility.", "creator_id": "calib_ai"}'
```

```json
{"confidence":0.8899,"content_id":"60af9d04d8c0","guess":"ai","label":"This looks a lot like writing produced by an AI tool — two separate checks both pointed that way. These checks can be wrong. If you wrote this yourself, you can appeal and a person will look at it.","model_score":0.9124,"status":"decided","style_score":0.8561}
```

The other two labels, from the same session:

```bash
$ curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "I work at a store on weekends. I stock the shelves and help people find things. Some days are busy and some days are slow. My manager is nice and she lets me pick my breaks. I like the job because I can save money for school. Next year I want to study nursing. My mom is a nurse and she says it is hard work but good work.", "creator_id": "calib_plain"}'
```

```json
{"confidence":0.8309,"content_id":"1748c00e7207","guess":"unsure","label":"We can't tell either way, so we're not making a call on this one. Our checks gave mixed results, which happens a lot with ordinary, plainly written work. This is not a finding that AI was used. If you'd like a person to look at it, you can ask for a review.","model_score":0.768,"status":"decided","style_score":0.9252}
```

```bash
$ curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"My grandmother kept chickens until she was ninety-one. Not many — four, maybe five at a time, each one named after a country singer she'd liked and then fallen out with. Dolly outlived three Lorettas. When the fox finally got in (it was always going to; the wire was older than my mother), she didn't cry, she just sat on the back step with her coffee going cold and said, well, that's that, then. She bought two more on Saturday.\", \"creator_id\": \"dave\"}"
```

```json
{"confidence":0.2308,"content_id":"e392ee7b7fa7","guess":"human","label":"This reads like it was written by a person. We didn't find anything that suggests an AI tool wrote it.","model_score":0.3641,"status":"decided","style_score":0.0309}
```

**An appeal**

```bash
$ curl -X POST http://127.0.0.1:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "60af9d04d8c0", "reasoning": "I wrote this myself for a class assignment. It sounds formal because the prompt asked for a formal summary."}'
```

```json
{"content_id":"60af9d04d8c0","message":"Thanks — your appeal is recorded and a person will review this piece. The original label is on hold until then.","original_label":"This looks a lot like writing produced by an AI tool — two separate checks both pointed that way. These checks can be wrong. If you wrote this yourself, you can appeal and a person will look at it.","status":"under_review"}
```

**What the log shows afterwards**

```bash
$ curl "http://127.0.0.1:5000/log?limit=3"
```

```json
{"count":3,"entries":[{"combined_score":0.8309,"content_id":"1748c00e7207","creator_id":"calib_plain","guess":"unsure","label":"We can't tell either way, so we're not making a call on this one. Our checks gave mixed results, which happens a lot with ordinary, plainly written work. This is not a finding that AI was used. If you'd like a person to look at it, you can ask for a review.","model_score":0.768,"status":"decided","style_score":0.9252,"timestamp":"2026-10-31T21:58:04+00:00"},{"combined_score":0.2308,"content_id":"e392ee7b7fa7","creator_id":"dave","guess":"human","label":"This reads like it was written by a person. We didn't find anything that suggests an AI tool wrote it.","model_score":0.3641,"status":"decided","style_score":0.0309,"timestamp":"2026-10-31T21:58:04+00:00"},{"content_id":"60af9d04d8c0","creator_id":"calib_ai","event":"appeal","reasoning":"I wrote this myself for a class assignment. It sounds formal because the prompt asked for a formal summary.","status":"under_review","timestamp":"2026-10-31T21:58:09+00:00"}]}
```

The appeal sits after the original decision; it doesn't overwrite it. The
`ai` decision for `60af9d04d8c0` is still earlier in `logs/audit.jsonl`, now
followed by an `under_review` entry with the writer's reasoning.

---

## How I Used AI

**Moment 1**

- *What I asked for:* An implementation of the three style measures and a
  `style_signal` that combines them, with a first guess at the calibration
  ranges.
- *What came back:* Working measures, but with type-token ratio mapped
  0.65 → 0.85. Run on the four calibration inputs, the clearly-AI paragraph
  had a *higher* TTR (0.86) than the plain human one (0.78), so that measure
  was pushing the wrong way.
- *What I changed:* Moved the TTR range to 0.75 → 0.90 and cut its weight to
  0.2, the smallest of the three, and wrote down in the Signals section that
  it barely separates anything.

**Moment 2**

- *What I asked for:* A combining rule and thresholds.
- *What came back:* A 0.6/0.4 weighted average. Calibration showed the
  starter's 0.65 AI threshold would label my plain-human paragraph (0.83)
  high-confidence AI.
- *What I changed:* Raised the AI threshold to 0.85, added the disagreement
  guard so a split between the signals can only ever produce "unsure", and
  rewrote the unsure label to say outright that it is not a finding of AI
  use.

<!-- ═══════════════════════ UNIT 8 — THE TEST ═══════════════════════ -->

---

## Rate Limiting

**My limits:** ___ per minute, ___ per day

**Why those numbers and not others:**
<!-- Think about two people: a real writer submitting their own work a few
     times an hour, and a script sending a thousand variations to map your
     thresholds. Your numbers have to be liveable for the first and hostile to
     the second. -->

**What a caller counts as:** <!-- per address, or per creator_id? They fail
differently — one script can look like a thousand callers, and one household
can look like one. -->

**The run of status codes when I pushed past it:**

<!-- python run_attacks.py --flood 15 -->

```

```

---

## Attack Run — Before

<!-- Every attack with its outcome and a held-or-broke mark.
     `run_attacks.py --label before` produces the table. -->



**Ten audit log entries from the run**

<!-- Choose entries that show the interesting failures, not the ten easiest. -->

```json

```

**The single worst outcome** — the one I'd least want to explain to a writer
whose work got caught by it:



---

## Run Log and Verdicts

<!-- Your five criteria across three trials. `run_eval.py --label before`. -->

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |
| 2.  |  |  |  |  |  |
| 3.  |  |  |  |  |  |
| 4.  |  |  |  |  |  |
| 5.  |  |  |  |  |  |

**Real output from one trial**, pasted as text, naming the file and function
that produced it:

```json

```

**Diagnoses**

<!-- For each miss AND each broken attack: the stage and the mechanism.

     Your service has five stages: the route, signal one, signal two, the
     combining rule, and the label mapping.

     Not a diagnosis:  "The evasion attacks got through."
     A diagnosis:      "Four evasion inputs got through. All four had typos
                        added to AI-generated text. My second signal measures
                        word variety, and typos raise word variety — so it read
                        them as more human. My combining rule weights that
                        signal at 0.6, so it dragged the whole score down."

     Look for a pattern. Five failures on one signal is one problem, not five. -->



---

## The Improvement

**What I changed:**

**Which diagnosis pointed at it:**

### Attack Run — After

<!-- Same format. `run_attacks.py --label after` -->



**Did it help, and how do I know:**

<!-- Widening the unsure band usually fixes one problem and creates another.
     Reporting that trade honestly is worth full credit. -->



---

## What's Still Broken

<!-- For each attack still getting through and each criterion still missed:
     what you'd do, and why you stopped. -->



**The trade I'd make if this ran for real:**

<!-- Two sentences. Fewer wrong accusations means more AI text getting through.
     Say which way you'd go and WHO PAYS FOR IT. -->



<!-- ═════════════════════════════════════════════════════════════════════

     SUBMISSION CHECKLIST — unit 7

       [ ] criteria.md has five numbered criteria, each naming a target
       [ ] Each has a reason underneath
       [ ] POST /submit returns content_id, guess, confidence, label,
           model_score and style_score
       [ ] Two signals that measure DIFFERENT things, each with a named blind spot
       [ ] Three label variants, all reachable, written out in full
       [ ] POST /appeal changes status and writes to the log
       [ ] Signals and Scoring names scoring.py::combine_signals
       [ ] Sample Run: a submission AND an appeal, as pasted text
       [ ] At least four new commits
       [ ] Repository URL submitted — WRITE IT DOWN

     SUBMISSION CHECKLIST — unit 8

       [ ] Rate limiting on /submit, with your numbers justified
       [ ] The pasted run of status codes showing 429
       [ ] Audit log with all nine fields, recording rejections too
       [ ] The attack set run IN FULL, every input with an outcome
       [ ] Ten audit log entries pasted as text
       [ ] Five criteria across three trials
       [ ] A diagnosis for every miss and every broken attack — stage AND mechanism
       [ ] One improvement, with Attack Run — After
       [ ] What's Still Broken, including the production trade
       [ ] At least four new commits
       [ ] The SAME repository URL as last unit

     Do not delete and recreate this repository.
     ═════════════════════════════════════════════════════════════════════ -->

---

📖 **How to run this project: [RUNNING.md](RUNNING.md)**
