"""The standard set of categories, and the words people actually use.

A category is only useful if the same thing lands in it every time. Left
to the model, it does not: one month's bus fares came back as
"Transport", the next month's as "ongkos", and the breakdown grew two
rows for one thing — with a budget on one of them blind to the money
booked against the other.

Telling the model to be consistent does not make it consistent. It
chooses the word the sentence used, and the sentence is the user's. So
the mapping lives here, in the backend, where it is a rule rather than a
hope: whatever word arrives, it is resolved to a group before an account
is touched. The prompt still lists the standard names, but as a nudge,
not as the guarantee.

Two deliberate limits:

* **Matching is on the whole phrase, folded** — never on a word inside
  it. "Beli tiket bioskop" is not transport, and a rule clever enough to
  catch "ongkos bus" would be clever enough to get that wrong. The
  listed spellings are the ones that actually turn up.
* **An unknown name passes through.** This is a seed list, not a closed
  taxonomy: somebody tracking "Kucing" should get "Kucing", not be
  argued into "Lain-lain".

Deliberately absent: "Biaya admin", "Lain-lain", "Saldo awal" and
"Pemasukan lain". Those are system account names fetched by exact string,
and folding them into a group would quietly move the ledger's own
plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Canonical name -> the spellings that mean it. Keys are what a fresh
#: category is created as; values are matched case-insensitively.
EXPENSE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Transportasi": (
        "transport",
        "transportasi",
        "ongkos",
        "ongkos jalan",
        "ojol",
        "ojek",
        "ojek online",
        "gojek",
        "goride",
        "gocar",
        "grab",
        "grabbike",
        "grabcar",
        "maxim",
        "taksi",
        "taxi",
        "tiket",
        "tiket kereta",
        "tiket pesawat",
        "kereta",
        "krl",
        "mrt",
        "lrt",
        "busway",
        "transjakarta",
        "aptb",
        "angkot",
        "bus",
        "travel",
        "bensin",
        "bbm",
        "pertalite",
        "pertamax",
        "solar",
        "parkir",
        "tol",
        "e-toll",
        "etoll",
        "perjalanan",
    ),
    "Makan": (
        "makan",
        "makanan",
        "makan siang",
        "makan malam",
        "sarapan",
        "jajan",
        "kuliner",
        "gofood",
        "grabfood",
        "shopeefood",
        "warung",
        "resto",
        "restoran",
        "kopi",
        "ngopi",
        "cemilan",
        "camilan",
        "snack",
        "minum",
        "minuman",
    ),
    "Belanja": (
        "belanja",
        "shopping",
        "grocery",
        "groceries",
        "sembako",
        "supermarket",
        "minimarket",
        "indomaret",
        "alfamart",
        "pasar",
        "baju",
        "pakaian",
        "skincare",
        "kosmetik",
        "elektronik",
    ),
    "Tagihan": (
        "tagihan",
        "listrik",
        "pln",
        "token listrik",
        "air",
        "pdam",
        "gas",
        "internet",
        "wifi",
        "indihome",
        "pulsa",
        "kuota",
        "paket data",
        "langganan",
        "subscription",
        "netflix",
        "spotify",
        "iuran",
    ),
    "Kesehatan": (
        "kesehatan",
        "obat",
        "obat-obatan",
        "dokter",
        "rumah sakit",
        "apotek",
        "apotik",
        "klinik",
        "bpjs",
        "vitamin",
        "medical",
    ),
    "Keluarga": (
        "keluarga",
        "orang tua",
        "ortu",
        "anak",
        "istri",
        "suami",
        "kiriman keluarga",
    ),
    "Pendidikan": (
        "pendidikan",
        "sekolah",
        "kuliah",
        "spp",
        "kursus",
        "les",
        "buku",
        "seminar",
        "pelatihan",
    ),
    "Hiburan": (
        "hiburan",
        "nonton",
        "bioskop",
        "film",
        "game",
        "games",
        "musik",
        "liburan",
        "jalan-jalan",
        "wisata",
        "hobi",
    ),
    "Rumah": (
        "rumah",
        "sewa",
        "sewa rumah",
        "kontrakan",
        "kos",
        "kost",
        "perabot",
        "perabotan",
        "kebersihan",
        "service rumah",
    ),
    "Sosial": (
        "sosial",
        "donasi",
        "sedekah",
        "zakat",
        "infaq",
        "amal",
        "kado",
        "hadiah",
        "sumbangan",
        "kondangan",
        "nikahan",
    ),
    "Pribadi": (
        "pribadi",
        "salon",
        "potong rambut",
        "barbershop",
        "laundry",
        "perawatan",
    ),
    "Pajak": (
        "pajak",
        "pbb",
        "stnk",
        "samsat",
    ),
}

INCOME_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Gaji": ("gaji", "salary", "upah", "payroll", "gajian"),
    "Bonus": ("bonus", "thr", "komisi", "insentif", "tunjangan"),
    "Usaha": ("usaha", "jualan", "dagang", "bisnis", "omzet", "freelance", "proyek", "honor"),
    "Investasi": ("investasi", "dividen", "bunga", "saham", "reksadana", "imbal hasil"),
    # "hadiah" sits in Sosial as an expense too; the two indexes are
    # separate, so giving a gift and receiving one stay apart.
    "Hadiah": ("hadiah", "angpao", "pemberian", "warisan"),
}


@dataclass(frozen=True, slots=True)
class CategoryGroup:
    """One category, with every spelling that resolves to it."""

    #: The name a fresh account is created under.
    canonical: str
    #: Folded spellings, including the canonical one. Used to find an
    #: account the user already has in this group, whatever it is called.
    aliases: frozenset[str]


def fold(name: str | None) -> str:
    """Collapse whitespace and case, so matching is on the words alone."""
    return " ".join((name or "").split()).lower()


def canonical_category(name: str | None) -> str:
    """Tidy a name that belongs to no group.

    Only the first letter is forced. Lower-casing the rest would turn
    "PDAM" into "Pdam" and "THR" into "Thr", which is a different kind of
    wrong.

    Returns "" for a blank name; the caller decides what the default is.
    """
    cleaned = " ".join((name or "").split())

    if not cleaned:
        return ""

    return cleaned[0].upper() + cleaned[1:]


def _build_index(table: dict[str, tuple[str, ...]]) -> dict[str, CategoryGroup]:
    index: dict[str, CategoryGroup] = {}

    for canonical, synonyms in table.items():
        aliases = frozenset({fold(canonical), *(fold(s) for s in synonyms)})
        group = CategoryGroup(canonical=canonical, aliases=aliases)

        for alias in aliases:
            if alias in index:
                raise ValueError(
                    f"Sinonim '{alias}' dipakai oleh dua kategori: "
                    f"{index[alias].canonical} dan {canonical}"
                )
            index[alias] = group

    return index


EXPENSE_INDEX = _build_index(EXPENSE_SYNONYMS)
INCOME_INDEX = _build_index(INCOME_SYNONYMS)


def _resolve(index: dict[str, CategoryGroup], name: str | None) -> CategoryGroup:
    folded = fold(name)
    known = index.get(folded)

    if known is not None:
        return known

    # Not in the seed list, and that is allowed. Its own group of one.
    return CategoryGroup(canonical=canonical_category(name), aliases=frozenset({folded}))


def resolve_expense(name: str | None) -> CategoryGroup:
    return _resolve(EXPENSE_INDEX, name)


def resolve_income(name: str | None) -> CategoryGroup:
    return _resolve(INCOME_INDEX, name)


#: A few spellings per category for the system prompt. The backend maps
#: the rest; this is only there so the model reaches for the right name
#: first and the user sees its own words come back as a standard one.
PROMPT_HINTS: dict[str, str] = {
    "Transportasi": "ongkos, ojol, tiket, bensin, parkir, tol",
    "Makan": "jajan, kopi, gofood, warung",
    "Belanja": "sembako, indomaret, baju",
    "Tagihan": "listrik, pulsa, wifi, langganan",
    "Kesehatan": "obat, dokter, apotek",
    "Keluarga": "orang tua, anak, istri, suami",
    "Pendidikan": "sekolah, kuliah, kursus, buku",
    "Hiburan": "nonton, game, liburan",
    "Rumah": "sewa, kos, perabot",
    "Sosial": "donasi, sedekah, kado, kondangan",
    "Pribadi": "salon, laundry, potong rambut",
    "Pajak": "pbb, stnk, samsat",
}
