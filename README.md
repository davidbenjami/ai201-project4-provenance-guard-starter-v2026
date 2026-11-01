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
machine text. A paragraph I wrote myself in short, plain sentences ("I make
my bed. I work at home. I use the computer…") scored **0.83**, close to a
clearly-AI paragraph's **0.91**. The reverse also happens: AI text asked to be
ornate or full of rare words reads as human.

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
shares signal one's victim: my own plain paragraph, with even sentences and
no semicolons, scored **0.98**, *more* AI-like than the AI paragraph (0.86).
And TTR barely separated anything in calibration, which is why it has the
smallest weight.

*A note on calibration:* the four calibration inputs I tuned on (clearly AI,
clearly human, plain human, lightly edited AI) were written by Claude to
imitate each style. My own writing, tested afterwards, is the real check, and
it came out worse than the imitations did (see Label Variants).

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

All three are reachable; the Sample Run below shows each one coming back from
the live service.

The AI threshold is high on purpose. I set it at 0.85 because a
Claude-written imitation of plain writing combined to 0.83 and a clearly-AI
paragraph to 0.89. **Then my own plain writing combined to 0.89 and was
labelled high-confidence AI.** That is a real false positive on a real person's
work, and exactly the blind spot both signals share. I haven't moved the
threshold to hide it: 0.89 is the same score the AI paragraph got, so no
threshold separates them. That's a unit 8 diagnosis, not a number to tune.

It also shows how hard "human" is to reach. My casual wallet paragraph got
0.78 (unsure), and a Mark Twain passage got 0.44 (unsure). The only input that
reached the human label was a Claude-written imitation of lively, punctuated
human prose.

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

**A submission:** a paragraph I wrote myself, plainly on purpose

```bash
$ curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"I make my bed. I work at home. I use the computer. I type on the keyboard. I don't see anyone. I eat after. I like the weather. I want to find a good job.\", \"creator_id\": \"dave\"}"
```

```json
{"confidence":0.8915,"content_id":"f71a14bba408","guess":"ai","label":"This looks a lot like writing produced by an AI tool — two separate checks both pointed that way. These checks can be wrong. If you wrote this yourself, you can appeal and a person will look at it.","model_score":0.8335,"status":"decided","style_score":0.9785}
```

Every word is mine, and it was labelled high-confidence AI. Both signals
agreed (model 0.83, style 0.98) because both reward the same thing: short
sentences in common words with no unusual punctuation.

The other labels, from the same service:

My own writing, in my normal voice (typos left in):

```bash
$ curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "Yo, I almost lost my wallet. When I could noe find it my heart sank to the bottom of my stomach. I searched everywhere and I was at home so nobody could help me look for it. I later found it in the garage. I left it there when I took the trash out.", "creator_id": "dave"}'
```

```json
{"confidence":0.781,"content_id":"367d74606204","guess":"unsure","label":"We can't tell either way, so we're not making a call on this one. Our checks gave mixed results, which happens a lot with ordinary, plainly written work. This is not a finding that AI was used. If you'd like a person to look at it, you can ask for a review.","model_score":0.7492,"status":"decided","style_score":0.8287}
```

The human label, reached by a Claude-written imitation of casual human prose
(from my first session; it shows the label is reachable, not that it is
reached by real human writing):

```json
{"confidence":0.2308,"content_id":"e392ee7b7fa7","guess":"human","label":"This reads like it was written by a person. We didn't find anything that suggests an AI tool wrote it.","model_score":0.3641,"status":"decided","style_score":0.0309}
```

**An appeal** against the false positive above

```bash
$ curl -X POST http://127.0.0.1:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "f71a14bba408", "reasoning": "I wrote this myself. I wrote it in short simple sentences on purpose."}'
```

```json
{"content_id":"f71a14bba408","message":"Thanks — your appeal is recorded and a person will review this piece. The original label is on hold until then.","original_label":"This looks a lot like writing produced by an AI tool — two separate checks both pointed that way. These checks can be wrong. If you wrote this yourself, you can appeal and a person will look at it.","status":"under_review"}
```

**What the log shows afterwards**

```bash
$ curl "http://127.0.0.1:5000/log?limit=3"
```

```json
{"count":3,"entries":[{"combined_score":0.8915,"content_id":"f71a14bba408","creator_id":"dave","guess":"ai","label":"This looks a lot like writing produced by an AI tool — two separate checks both pointed that way. These checks can be wrong. If you wrote this yourself, you can appeal and a person will look at it.","model_score":0.8335,"status":"decided","style_score":0.9785,"timestamp":"2026-11-01T20:29:49+00:00"},{"combined_score":0.4438,"content_id":"77754bf374da","creator_id":"twain_sample","guess":"unsure","label":"We can't tell either way, so we're not making a call on this one. Our checks gave mixed results, which happens a lot with ordinary, plainly written work. This is not a finding that AI was used. If you'd like a person to look at it, you can ask for a review.","model_score":0.4611,"status":"decided","style_score":0.4179,"timestamp":"2026-11-01T20:30:00+00:00"},{"content_id":"f71a14bba408","creator_id":"dave","event":"appeal","reasoning":"I wrote this myself. I wrote it in short simple sentences on purpose.","status":"under_review","timestamp":"2026-11-01T20:30:13+00:00"}]}
```

The appeal sits after the original decision; it doesn't overwrite it. The
`ai` decision for `f71a14bba408` is still in the log, followed by an
`under_review` entry with my reasoning. (The middle entry is the Mark Twain
passage, submitted between the two.)

---

## How I Used AI

**Moment 1**

- *What I asked for:* I asked Claude to help me complete and review my
  assignment.
- *What came back:* The code for both signals, the scoring, the routes and a
  draft of this write-up. I read the response and looked at the bolded points.
- *What I changed / would change:* I expected the AI's writing wouldn't sound
  human, and it doesn't. Next time I would make the points short and simple
  first, then add a more detailed paragraph.

**Moment 2**

- *What I asked for:* Help finishing the parts that had to be mine.
- *What came back:* Claude pointed out that the "human" sample paragraphs in
  my first draft were written by Claude, not me, so they couldn't test
  anything. It gave me questions to answer instead of writing the paragraphs
  for me.
- *What I changed:* I wrote my own two paragraphs and ran them. My plain one
  was labelled high-confidence AI. The first draft had said the 0.85
  threshold protected plain writers; my own writing showed it doesn't, so this
  write-up now says that.

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
