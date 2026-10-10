"""The tool contract offered to the model (PRD section 13).

Only tools with a working backend are exposed. A tool the model can call
but the server cannot fulfil teaches it to promise things that then fail
— so `run_simulation`, `propose_goal`, `propose_allocation` and
`propose_budget` from the PRD's table are deliberately absent until the
services behind them exist.

Two classes of tool, and the split is the whole safety model:

* **Read tools** run immediately. They change nothing, so the PRD needs
  no confirmation for them.
* **Propose tools** never write. They produce a validated draft plus its
  computed impact, which the user confirms separately. Posting happens
  only through the confirmation endpoint, keyed by the draft's operation
  id (FR05).

Schemas are kept terse on purpose: the model has a 24,576-token budget
shared with the conversation history, and verbose schemas eat it.
"""

from __future__ import annotations

from typing import Any

#: Amounts are integers of rupiah everywhere. Said explicitly in each
#: description because a model will otherwise emit 35.5 for "35 ribu
#: setengah" and the backend will reject it.
_AMOUNT = {"type": "integer", "description": "Nominal dalam rupiah bulat, tanpa desimal"}
_ACCOUNT = {"type": "string", "description": "Nama atau alias kantong, contoh 'BCA'"}

READ_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_accounts",
            "description": "Daftar kantong pengguna beserta saldonya.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": (
                "Ringkasan: saldo likuid, aset bersih, total utang, "
                "uang bebas pakai, total pengeluaran dan pemasukan."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_transactions",
            "description": (
                "Cari transaksi terbaru. Gunakan untuk menjawab pertanyaan "
                "atau menemukan transaksi yang ingin dikoreksi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maksimal 50", "default": 20},
                },
            },
        },
    },
]

PROPOSE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "propose_transactions",
            "description": (
                "Buat draft satu atau beberapa transaksi dari pesan pengguna. "
                "TIDAK menyimpan apa pun; pengguna harus mengonfirmasi. "
                "Jika nama kantong ambigu atau tidak disebut, tanyakan dulu, jangan menebak."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transactions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "expense",
                                        "income",
                                        "transfer",
                                        "card_payment",
                                        "refund",
                                    ],
                                    "description": (
                                        "transfer mencakup top-up dan tarik tunai; "
                                        "card_payment untuk membayar tagihan kartu kredit"
                                    ),
                                },
                                "amount": _AMOUNT,
                                "from_account": _ACCOUNT,
                                "to_account": _ACCOUNT,
                                "category": {"type": "string"},
                                "fee": dict(_AMOUNT, description="Biaya admin, jika ada"),
                                "occurred_on": {
                                    "type": "string",
                                    "description": "Tanggal YYYY-MM-DD, kosongkan jika hari ini",
                                },
                                "merchant": {"type": "string"},
                                "note": {"type": "string"},
                            },
                            "required": ["type", "amount"],
                        },
                    }
                },
                "required": ["transactions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_account_change",
            "description": (
                "Buat draft penambahan kantong baru. TIDAK menyimpan apa pun; "
                "pengguna harus mengonfirmasi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "account_type": {
                        "type": "string",
                        "enum": ["bank", "ewallet", "cash", "credit_card"],
                    },
                    "opening_balance": dict(
                        _AMOUNT, description="Saldo awal, 0 jika tidak disebut"
                    ),
                    "credit_limit": dict(_AMOUNT, description="Khusus kartu kredit"),
                },
                "required": ["name", "account_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_correction",
            "description": (
                "Buat draft pembatalan sebuah transaksi. Gunakan find_transactions "
                "lebih dulu untuk mendapatkan id-nya. Jika ada beberapa kandidat, "
                "minta pengguna memilih, jangan menebak."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string", "description": "UUID transaksi"},
                },
                "required": ["transaction_id"],
            },
        },
    },
]

ALL_TOOLS: list[dict[str, Any]] = READ_TOOLS + PROPOSE_TOOLS

#: Names that write nothing, so they can run without asking the user.
READ_TOOL_NAMES = frozenset(t["function"]["name"] for t in READ_TOOLS)
PROPOSE_TOOL_NAMES = frozenset(t["function"]["name"] for t in PROPOSE_TOOLS)


SYSTEM_PROMPT = """Kamu asisten keuangan pribadi berbahasa Indonesia.

Aturan:
- Semua nominal adalah rupiah bulat (integer). "35rb" = 35000, "1,5 juta" = 1500000.
- JANGAN pernah menghitung atau menyebut saldo sendiri. Panggil tool untuk angka apa pun.
- Transfer, top-up dan tarik tunai BUKAN pemasukan atau pengeluaran.
- Membayar tagihan kartu kredit BUKAN pengeluaran baru.
- Jika kantong tidak disebut atau namanya cocok dengan lebih dari satu, TANYA dulu. Jangan menebak.
- Tool propose_* hanya membuat draft; pengguna yang mengonfirmasi. Jangan bilang sudah tersimpan.
- Jawab ringkas, dalam bahasa Indonesia.
"""
