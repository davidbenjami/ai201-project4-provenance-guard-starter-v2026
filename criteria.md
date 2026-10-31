# Acceptance criteria — Provenance Guard

Five criteria that say what "working" means for this service, written in unit 7
**before** you built it.

**All five are yours.** None are given.

An acceptance criterion names a number or something plainly observable. *"The
detector is accurate"* is an opinion — and perfect AI detection isn't possible
anyway, so it's an opinion about something nobody can deliver. *"Of 10 pieces I
wrote myself, at most 1 is labelled high-confidence AI"* is a criterion.

Under each, write a sentence or two on **why that target**. *"I allow at most 1
false positive in 10 because on a writing site a wrong accusation costs more
than a missed detection"* is a real answer.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

---

## Pick numbers you can defend

**Cover at least three of these five areas.** They're prompts, not a form.

| Area | A question it could answer |
|---|---|
| False positives | How often may a human's writing get called AI? |
| Score spread | How far apart should clearly-AI and clearly-human text score? |
| Label coverage | Is every one of your three labels actually reachable? |
| The appeal path | Does an appeal always change status and always get recorded? |
| Bad input | What happens when `text` is missing, empty, or enormous? |

Two things worth knowing before you pick numbers:

- **The expensive mistake is one-sided.** Missing some AI text costs the site a
  little. Accusing a real writer costs that person a lot. A criterion that
  treats both errors as equally bad is describing a system nobody would ship.
- **Unit 8 tests across three trials, and the target has to hold across all
  three.** Your first signal runs a model, so identical input can score
  differently twice. A target of "at most 1 in 10" against trials of 2, 1, 2 is
  a **miss**.

---
## 1. My own writing is almost never called AI

Of 10 pieces I wrote myself, **at most 1** is labelled high-confidence AI —
in every one of three trials.

**Why this target:** On a writing site a wrong accusation costs the writer far
more than a missed detection costs the site, so this is the criterion I care
about most. I allow 1 rather than 0 because signal one is known to read plain,
simple writing as machine-like, and some of my own writing is plain.

---

## 2. All three labels are reachable

Of 6 prepared inputs — 2 clearly AI, 2 clearly human, 2 borderline (plain
human writing, lightly edited AI) — **each of the three labels is produced
at least once**, in all three trials.

**Why this target:** A label nobody can reach is a range with a gap in it. My
AI threshold is high (0.85) on purpose, so this is the criterion that would
catch me having set it so high that "AI" can never actually happen.

---

## 3. Clearly-AI and clearly-human text score far apart

The mean combined score of 5 clearly-AI texts is **at least 0.30 higher**
than the mean combined score of 5 clearly-human texts, in every trial.

**Why this target:** My unsure band is 0.40–0.85, which is 0.45 wide. If the
two groups sit less than 0.30 apart, most real submissions will land in
"unsure" and the service isn't telling anyone anything. 0.30 is about two
thirds of the band — enough that the ends of the scale mean something.

---

## 4. Bad input is refused, never crashes, and leaves a trace

Of 4 malformed requests — empty `text`, no `text` field, `text: null`, and
250,000 characters of text — **4 of 4** get a 4xx status (never a 5xx), and
each one writes a `rejected` entry to the audit log, in all three trials.

**Why this target:** A crash on malformed input is one of the most common real
failures, and a refused request that leaves no trace is an attack I'd never
find. It has to be 4 of 4: one 500 is a bug, not a rate.

---

## 5. Every appeal is recorded

Of 5 appeals against real `content_id`s, **5 of 5** return status
`under_review` and add exactly one `appeal` entry to the log; an appeal with a
made-up `content_id` gets a 404 and changes nothing.

**Why this target:** The appeal is the only thing between a wrong accusation
and nothing at all. A writer who appeals and is silently dropped is worse off
than one who was never offered an appeal, so anything under 100% is a failure.

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 8 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath, like this:

         ## 2. Uncertain cases land in the unsure band

         The system handles uncertain cases well.

         **Why this target:** ...

         > **Revised in unit 8:** Text I judged borderline scores between
         > 0.4 and 0.6 in at least 4 of 5 cases.
         >
         > **Why revised:** "well" gave me nothing to check. I couldn't
         > reach a verdict from it at all.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "At most 1 of 10 of my own pieces flagged as AI" → "at most 3
            of 10", because 1 of 10 turned out to be hard.

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->
