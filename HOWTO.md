# HOWTO: Classifying Your Mistakes

This is the field guide for the app's core activity — turning engine-detected
mistakes into a labelled dataset of *why* you went wrong. Written for a future
user (or future self) who has forgotten the system. The theory is in
[README.md](./README.md#classification-system) and DESIGN.md; this is practice.

## The one question that matters

For every mistake the engine finds, you answer: **which part of my thinking
process failed, and was I aware of the idea at all?** Everything else — charts,
prescriptions, drills — is derived from those two answers.

## Layer A — which thinking step failed? (keys `1`–`4`)

Ask them in this order; pick the *first* one that applies.

| Key | Step | It's this when… |
|---|---|---|
| `1` | **Missed opponent's threat** | Their *previous* move created a threat (a capture, a mating idea, a trap) and your move ignored it. The tell: their reply executed something that was already on the board before you moved. |
| `2` | **Missed my forcing move** | You had a check, capture, or concrete threat that won material or mated — and played something quieter. The tell: the engine's best move is a tactic for *you*. |
| `3` | **Wrong plan in a quiet position** | No tactics for either side; you simply chose the wrong plan, piece, or square. The default when nothing forcing was in the air. |
| `4` | **Failed blunder check** | Your move *created* the problem — their best reply (often a check or capture) punishes the move you just played. The tell: the position was fine until you moved. |

Steps 1 and 4 are easily confused: **1 = you ignored a threat that already
existed; 4 = you invited a new one.** If their winning reply would not have
worked one move earlier, it's Step 4.

The app pre-selects a suggested step from engine heuristics. It's a starting
point, right roughly three times out of four — override it freely; your
judgment is the ground truth the stats are built on.

## Layer B — did you see it? (keys `G` / `D`)

- **`G` — Got it wrong.** The idea was in your candidate moves / calculation
  and you mis-evaluated it. A calculation or evaluation error.
- **`D` — Didn't see it.** Total blind spot; the idea never entered your head.
  A perception error.

Be honest — this is the introspective half only you can answer, and it's the
axis that most changes the training prescription: *got-it-wrong* patterns call
for deeper/more careful calculation; *didn't-see-it* patterns call for
scanning habits and pattern drills.

## Tags and notes

Auto-flagged chips (toggle if wrong): **Time pressure** (fast move or low
clock), **Endgame** (low material), **Transition** (queens just left / major
material change). Use the notes field (`N` to focus) for what you were
actually thinking — future-you reviewing a cluster of Step-3 mistakes will
thank present-you for "thought the knight was headed to d5, never asked what
it defended".

## The workflow

1. **Import → analyze** (Games page). Games without evals: *Request ↗*
   analysis on Lichess, then *Refresh*.
2. **Classify** (Mistakes page, unclassified-only by default). Rhythm:
   look at the board — *Review* shows your move (red) vs engine best (green) —
   press `1`–`4`, `G` or `D`, `Enter`. Ten mistakes take a few minutes.
   Use *Explore* mode to play out lines against the engine when you're not
   sure what the best move actually accomplished.
3. **Read the prescription** (Dashboard). The top cell of the Step × Awareness
   matrix is your highest-leverage training target; the Stats page shows the
   full distribution and trends.
4. **Re-tune occasionally** (Settings). If the queue fills with noise, raise
   the thresholds or tighten the still-winning suppression, then re-analyze —
   classifications survive.

## Reading the matrix

Eight cells, eight different medicines. The two most common for club players:

- **Step 4 / Didn't see it** — you don't run a blunder check. The fix is
  mechanical, not chess knowledge: before every move, name their best forcing
  reply out loud.
- **Step 2 / Didn't see it** — tactics exist but you don't look for them when
  it's "just a normal position". Fix: checks-captures-threats scan, every
  move, both sides.

The full text for each cell appears in the Dashboard's *Train this first*
panel once you've classified enough mistakes to rank them.
