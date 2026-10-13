# Indonesian chat benchmark

Measures the two things the PRD gates the pilot on:

- **Accuracy** — "≥90% draft pada benchmark minimal 100 pesan Indonesia
  mempunyai nominal, akun, tanggal, dan jenis yang tepat sebelum
  koreksi" (section 10). Those four fields are what each case asserts.
- **Latency** — draft response p95 ≤ 10 seconds (section 9).

```sh
.venv/Scripts/python -m benchmarks.run                      # all 128 cases
.venv/Scripts/python -m benchmarks.run --tags amount date   # a slice
.venv/Scripts/python -m benchmarks.run --ids amt-01 acc-06  # named cases
.venv/Scripts/python -m benchmarks.run --fake               # harness self-check, no GPU
```

Exits non-zero when either gate fails, so it can run in CI once there is
a model endpoint CI can reach.

## Why it exists

Every ad-hoc session against the real model turned up a defect that the
unit suite could not: a date three years wrong, a reply claiming a draft
that was never created, a budget set when a purchase was meant, a tool
refused because the model used a synonym for an argument. Those are
behaviours, not logic errors, and the only way to catch them before a
user does is to measure them on a corpus.

Writing the corpus found one before the first run. The fixture wallets
include both `BCA` and `CC BCA`, which is an ordinary pairing for an
Indonesian user — and it made "pakai BCA" permanently ambiguous, because
the card's name contains the bank's. Account resolution now prefers an
exact match over a substring one.

## Shape of a case

```python
Case("amt-01", "makan 35rb pakai BCA", "draft", "expense", 35_000, "BCA", date="today")
```

`expect` is one of:

| Value    | Meaning                                                            |
| -------- | ------------------------------------------------------------------ |
| `draft`  | A draft must be raised, with the stated fields                     |
| `none`   | No draft — questions, simulations, greetings                       |
| `refuse` | No draft, and guessing would be wrong: ambiguous wallet, no amount |

Fields left `None` are not checked, so a case can pin the amount without
pinning a category the PRD never specified.

## What a case can assert

The PRD's four fields are the gate, not the whole of what goes wrong.
Every defect found against the real model after the first run was
invisible to them, so a case can pin these too:

| Field                            | Asserts                                                             |
| -------------------------------- | ------------------------------------------------------------------- |
| `draft_kind`                     | The Draft row's kind — `batch`, `recategorise`, `reversal`, `goal`  |
| `items`, `amounts`               | A batch's entry count, and their amounts in any order               |
| `stated_total`                   | The total the message claimed, carried but never posted             |
| `category_group`                 | The group the category **resolves** to, per `domain/categories.py`  |
| `category`, `merchant`, `note`   | The keepsakes: exact (folded), substring, and required substrings   |
| `has_category`/`merchant`/`note` | Only that the field was filled at all                               |
| `from_category`, `to_category`   | A recategorise's two category accounts                              |
| `no_wallet_impact`               | No impact row names a wallet — moving a label moves no money        |

`draft_kind` is the one that cannot be read off the payload: it is
*which act* the model reached for. A relabel offered as a reversal has
the right amount, wallet, date and type, and is still the wrong answer.

`category_group` and not `category`, because the spelling stopped being
the model's to get wrong: `EXPENSE_SYNONYMS` folds "ongkos", "bensin"
and thirty more into `Transportasi` before an account is touched. What
is still the model's mistake is filing a bus fare under `Tagihan`.

A case may also carry `seed` transactions, posted through
`POST /transactions` before the measured message and outside the timing.
Category reuse and recategorise are only questions once the user has a
past — a seeded category is listed to the model in the system prompt,
which is the whole mechanism being tested.

The scorer itself is covered by `tests/test_benchmark_check.py`, which
needs neither a model nor a database. It is there because this harness
had already gone stale once: the batch draft shape landed, two `multi`
cases started failing on the harness rather than on the model, and
nothing could say which of the two was wrong.

## Fixture

Every case runs against a **fresh user** with the same five wallets, so
no case can affect the next, and all of them are deleted at the end:

| Wallet  | Type        | Alias     | Balance          |
| ------- | ----------- | --------- | ---------------- |
| BCA     | bank        | `bca`     | 5,000,000        |
| Mandiri | bank        | `mandiri` | 2,000,000        |
| GoPay   | e-wallet    | `gopay`   | 200,000          |
| Cash    | cash        | `cash`    | 150,000          |
| CC BCA  | credit card | `cc`      | limit 10,000,000 |

## Reading the output

Failures are grouped by field (`nominal`, `akun`, `tanggal`, `jenis`,
and the rest of the table above), because that is how the PRD states its
gate, and by tag, so a weak area is visible rather than averaged away.

Note what this means for the headline figure: because the corpus asserts
more than section 10 asks for, the accuracy percentage is **stricter**
than the PRD's gate, and is meant to be. A run that clears 90% here has
cleared more than the pilot requires.

Latency is timed around the chat turn alone. Registration and wallet
setup are excluded — including them inflated every figure by three to
four seconds and would have made the gate look harder to pass than it is.

Percentiles use nearest rank with rounding **up**. Truncating lands
below the median on small samples, which would understate exactly the
figure the gate is read from.

## Not a test

This costs GPU time on a shared box and needs a working `LLM_API_KEY`,
so it is deliberately outside `pytest`. The suite must stay runnable
without a model.
