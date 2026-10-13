"""The benchmark's scorer, which nothing else was checking.

`benchmarks/run.py` is what decides whether the model is good enough to
pilot, and a wrong scorer is worse than no scorer: it reports confidently
either way. It had already gone stale once — the batch draft landed, and
`mul-01` started failing on the harness rather than on the model, with
nothing to say which of the two was wrong.

So these pin the scorer, not the model. No database and no GPU: `check`
is a pure function over the draft dicts the chat endpoint returns.
"""

from __future__ import annotations

from datetime import date

from benchmarks.corpus import Case
from benchmarks.run import check

TODAY = date(2026, 10, 13)


def _expense(**payload) -> list[dict]:
    """One single-entry expense draft, as the endpoint serialises it."""
    return [
        {
            "kind": "expense",
            "payload": {
                "type": "expense",
                "amount": 35_000,
                "_from_name": "BCA",
                "_to_name": None,
                **payload,
            },
            "impact": [{"account": "BCA", "before": 100_000, "after": 65_000, "delta": -35_000}],
        }
    ]


def _batch(*entries: dict, **payload) -> list[dict]:
    """One batch draft holding the given entries."""
    return [
        {
            "kind": "batch",
            "payload": {
                "items": [{"type": "expense", "_from_name": "Cash", **e} for e in entries],
                "stated_total": None,
                **payload,
            },
            "impact": [],
        }
    ]


# ----------------------------------------------------------------------
# The four fields the PRD gates on, which must keep working unchanged
# ----------------------------------------------------------------------


def test_a_correct_single_expense_passes():
    case = Case("t-01", "makan 35rb pakai BCA", "draft", "expense", 35_000, "BCA", date="today")

    assert check(case, _expense(), TODAY) == []


def test_a_wrong_amount_is_named_with_both_figures():
    case = Case("t-02", "makan 35rb pakai BCA", "draft", "expense", 40_000, "BCA")

    assert check(case, _expense(), TODAY) == ["nominal: expected 40000, got 35000"]


def test_expecting_no_draft_fails_when_one_is_raised():
    case = Case("t-03", "hapus semua transaksi", "refuse")

    assert check(case, _expense(), TODAY) == ["expected no draft, got 1 (expense)"]


# ----------------------------------------------------------------------
# Keepsakes
# ----------------------------------------------------------------------


def test_an_empty_note_fails_a_case_that_wants_one():
    case = Case("t-04", "...", "draft", has_note=True)

    assert check(case, _expense(), TODAY) == ["catatan: kosong"]


def test_a_note_missing_the_keyword_says_what_it_held_instead():
    case = Case("t-05", "...", "draft", note=("pulsa",))

    failures = check(case, _expense(note="beli kopi"), TODAY)

    assert failures == ["catatan: tidak menyebut pulsa, isinya 'beli kopi'"]


def test_a_note_containing_every_keyword_passes():
    case = Case("t-06", "...", "draft", note=("pulsa", "ibu"))

    assert check(case, _expense(note="tf ke Ibu buat top up saldo PULSA"), TODAY) == []


def test_a_category_in_the_wrong_case_passes_because_the_server_fixes_it():
    case = Case("t-07", "...", "draft", category="Transport")

    assert check(case, _expense(category="transport"), TODAY) == []


def test_a_category_that_is_a_different_word_fails():
    case = Case("t-08", "...", "draft", category="Transport")

    assert check(case, _expense(category="Ongkos"), TODAY) == [
        "kategori: expected Transport, got Ongkos"
    ]


def test_an_absent_category_reports_as_empty_rather_than_as_none():
    case = Case("t-09", "...", "draft", category="Transport")

    assert check(case, _expense(), TODAY) == ["kategori: expected Transport, got (kosong)"]


def test_a_merchant_matches_on_substring():
    case = Case("t-10", "...", "draft", merchant="ibu")

    assert check(case, _expense(merchant="Ibu (adik ayah)"), TODAY) == []


def test_has_merchant_only_asks_that_it_be_filled():
    assert check(Case("t-11", "...", "draft", has_merchant=True), _expense(), TODAY) == [
        "merchant: kosong"
    ]
    assert (
        check(
            Case("t-12", "...", "draft", has_merchant=True), _expense(merchant="Indomaret"), TODAY
        )
        == []
    )


# ----------------------------------------------------------------------
# Batch: the shape that silently broke two cases
# ----------------------------------------------------------------------


def test_a_correct_batch_passes_on_entries_and_stated_total():
    case = Case(
        "t-13",
        "...",
        "draft",
        "expense",
        None,
        "Cash",
        date="today",
        draft_kind="batch",
        items=3,
        amounts=(50_000, 70_000, 30_000),
        stated_total=150_000,
    )
    drafts = _batch(
        {"amount": 50_000},
        {"amount": 70_000},
        {"amount": 30_000},
        stated_total=150_000,
    )

    assert check(case, drafts, TODAY) == []


def test_batch_amounts_are_compared_regardless_of_order():
    case = Case("t-14", "...", "draft", amounts=(30_000, 50_000, 70_000))
    drafts = _batch({"amount": 70_000}, {"amount": 30_000}, {"amount": 50_000})

    assert check(case, drafts, TODAY) == []


def test_a_missing_batch_entry_is_reported_with_the_amounts_seen():
    case = Case("t-15", "...", "draft", items=3, amounts=(50_000, 70_000, 30_000))
    drafts = _batch({"amount": 50_000}, {"amount": 70_000})

    assert check(case, drafts, TODAY) == [
        "jumlah entri: expected 3, got 2",
        "rincian: expected [30000, 50000, 70000], got [50000, 70000]",
    ]


def test_a_single_draft_where_a_batch_was_expected_fails_on_draft_kind():
    case = Case("t-16", "...", "draft", draft_kind="batch", items=2)

    assert check(case, _expense(), TODAY) == [
        "jenis draft: expected batch, got expense",
        "jumlah entri: expected 2, got 0",
    ]


def test_a_batchs_wallet_and_keepsakes_are_read_from_its_first_entry():
    case = Case(
        "t-17",
        "...",
        "draft",
        "expense",
        50_000,
        "Cash",
        draft_kind="batch",
        category="Obat",
        note=("batuk",),
    )
    drafts = _batch(
        {"amount": 50_000, "category": "Obat", "note": "obat batuk"},
        {"amount": 70_000, "category": "Makan"},
    )

    assert check(case, drafts, TODAY) == []


# ----------------------------------------------------------------------
# Relabel: a label moving must move no money
# ----------------------------------------------------------------------


def _recategorise(impact: list[dict]) -> list[dict]:
    return [
        {
            "kind": "recategorise",
            "payload": {
                "from_category": "Ongkos",
                "to_category": "Transport",
                "amount": 25_000,
                "count": 1,
            },
            "impact": impact,
        }
    ]


def test_a_recategorise_touching_no_wallet_passes():
    case = Case(
        "t-18",
        "...",
        "draft",
        draft_kind="recategorise",
        from_category="Ongkos",
        to_category="Transport",
        no_wallet_impact=True,
    )
    drafts = _recategorise(
        [
            {"account": "Ongkos", "before": 25_000, "after": 0, "delta": -25_000},
            {"account": "Transport", "before": 0, "after": 25_000, "delta": 25_000},
        ]
    )

    assert check(case, drafts, TODAY) == []


def test_a_relabel_that_hands_the_money_back_fails_on_its_impact():
    case = Case("t-19", "...", "draft", draft_kind="recategorise", no_wallet_impact=True)
    drafts = _recategorise(
        [{"account": "BCA", "before": 75_000, "after": 100_000, "delta": 25_000}]
    )

    assert check(case, drafts, TODAY) == [
        "dampak: menyentuh kantong BCA - memindahkan label tidak boleh memindahkan uang"
    ]


def test_a_reversal_offered_where_a_relabel_was_asked_for_fails():
    case = Case("t-20", "...", "draft", draft_kind="recategorise", to_category="Transport")
    drafts = [{"kind": "reversal", "payload": {"amount": 25_000}, "impact": []}]

    assert check(case, drafts, TODAY) == [
        "jenis draft: expected recategorise, got reversal",
        "kategori tujuan: expected Transport, got (kosong)",
    ]


def test_the_relabel_direction_is_part_of_the_assertion():
    case = Case("t-21", "...", "draft", from_category="Transport", to_category="Ongkos")

    assert check(case, _recategorise([]), TODAY) == [
        "kategori asal: expected Transport, got Ongkos",
        "kategori tujuan: expected Ongkos, got Transport",
    ]


# ----------------------------------------------------------------------
# Every failure reason has to carry a field label, because the run's
# summary groups them on the text before the colon.
# ----------------------------------------------------------------------


def test_every_reason_is_prefixed_with_a_field():
    case = Case(
        "t-22",
        "...",
        "draft",
        "income",
        40_000,
        "Cash",
        to_account="GoPay",
        date="2020-01-01",
        fee=2_500,
        draft_kind="batch",
        items=2,
        amounts=(1,),
        stated_total=9,
        category="Transport",
        merchant="Ibu",
        note=("pulsa",),
        from_category="Makan",
        to_category="Transport",
        no_wallet_impact=True,
    )

    failures = check(case, _expense(note="kopi"), TODAY)

    assert [reason.split(":")[0] for reason in failures] == [
        "jenis draft",
        "jenis",
        "nominal",
        "akun",
        "akun tujuan",
        "biaya",
        "tanggal",
        "jumlah entri",
        "rincian",
        "total disebut",
        "kategori",
        "merchant",
        "catatan",
        "kategori asal",
        "kategori tujuan",
        "dampak",
    ]


# ----------------------------------------------------------------------
# The resolved category group, which is the layer the backend decides on
# ----------------------------------------------------------------------


def test_any_spelling_the_synonym_table_knows_passes():
    case = Case("t-23", "...", "draft", category_group="Transportasi")

    for written in ("ongkos", "Transport", "bensin", "parkir", "APTB", "transportasi"):
        assert check(case, _expense(category=written), TODAY) == [], written


def test_a_category_resolving_to_the_wrong_group_fails_and_shows_both():
    case = Case("t-24", "...", "draft", category_group="Transportasi")

    assert check(case, _expense(category="listrik"), TODAY) == [
        "kelompok kategori: expected Transportasi, got Tagihan (dari listrik)"
    ]


def test_an_empty_category_fails_a_group_assertion_as_empty():
    case = Case("t-25", "...", "draft", category_group="Makan")

    assert check(case, _expense(), TODAY) == [
        "kelompok kategori: expected Makan, got (kosong) (dari (kosong))"
    ]


def test_income_resolves_against_the_income_table():
    case = Case("t-26", "...", "draft", category_group="Gaji")
    drafts = _expense(type="income", category="gajian")

    assert check(case, drafts, TODAY) == []


def test_a_word_outside_the_table_keeps_its_own_name_as_its_group():
    case = Case("t-27", "...", "draft", category_group="Kucing")

    assert check(case, _expense(category="kucing"), TODAY) == []
