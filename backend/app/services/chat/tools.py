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

from datetime import datetime
from typing import Any

from ...domain.periods import PERIOD_KEYWORDS

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
                "Posisi saat ini: saldo likuid, aset bersih, total utang, uang bebas "
                "pakai. Saldo adalah nilai sekarang, bukan per periode. Untuk "
                "pengeluaran dalam suatu periode, pakai get_spending."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending",
            "description": (
                "Total pengeluaran dan pemasukan untuk SATU PERIODE, dengan rincian "
                "per kategori. Pakai ini untuk pertanyaan seperti 'bulan ini makan "
                "berapa' atau 'pengeluaran minggu ini'. Transfer dan pembayaran kartu "
                "tidak dihitung sebagai belanja; refund sudah dikurangi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": list(PERIOD_KEYWORDS),
                        "description": "Default bulan_ini",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Opsional. Jika diisi, kembalikan total kategori itu saja."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_goals",
            "description": ("Daftar target tabungan beserta dana terkumpul dan kekurangannya."),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budgets",
            "description": (
                "Budget tiap kategori beserta realisasi dan sisanya untuk satu "
                "periode. Budget adalah rencana belanja, BUKAN saldo - tidak "
                "mengurangi uang bebas pakai."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": list(PERIOD_KEYWORDS),
                        "description": "Default bulan_ini",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_transactions",
            "description": (
                "Daftar transaksi TERBARU (bukan hasil pencarian per kata kunci "
                "atau periode). Gunakan untuk menjawab pertanyaan atau menemukan "
                "transaksi yang ingin dikoreksi."
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
                "Catat satu atau beberapa transaksi yang SUDAH terjadi. Ini pilihan "
                "default untuk pesan yang menceritakan belanja, pemasukan atau "
                "transfer, termasuk ketika kategori disebut ('makan 35rb'). "
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
            "name": "propose_goal",
            "description": (
                "Buat draft target tabungan baru. TIDAK menyimpan apa pun; "
                "pengguna harus mengonfirmasi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "target_amount": _AMOUNT,
                    "target_date": {
                        "type": "string",
                        "description": "Opsional, YYYY-MM-DD",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "0 paling penting; default 0",
                    },
                },
                "required": ["name", "target_amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_allocation",
            "description": (
                "Buat draft alokasi dana dari sebuah kantong ke sebuah target. "
                "Alokasi TIDAK memindahkan uang dan tidak menambah aset - hanya "
                "menandai saldo yang sudah ada. Tidak boleh melebihi saldo kantong."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string"},
                    "account": _ACCOUNT,
                    "amount": _AMOUNT,
                },
                "required": ["goal_name", "account", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_budget",
            "description": (
                "Atur BATAS belanja bulanan sebuah kategori. HANYA gunakan ketika "
                "pengguna meminta menetapkan batas, misalnya 'budget makan 1 juta', "
                "'batasi transport 500rb', 'maksimal jajan 300rb sebulan'. "
                "JANGAN gunakan untuk mencatat belanja yang sudah terjadi. "
                "'makan 850rb pakai BCA' adalah PENGELUARAN - pakai "
                "propose_transactions. Petunjuk kuat: kalau pesan menyebut kantong "
                "('pakai BCA', 'dari cash') itu transaksi, bukan budget, karena "
                "budget tidak punya kantong."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "amount": dict(_AMOUNT, description="Batas per bulan, rupiah bulat"),
                },
                "required": ["category", "amount"],
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


SYSTEM_PROMPT_TEMPLATE = """Kamu asisten keuangan pribadi berbahasa Indonesia.

Hari ini {today} ({weekday}), zona waktu {timezone}.
Gunakan tanggal itu untuk menafsirkan "hari ini", "kemarin", "tadi pagi",
"minggu lalu" dan sejenisnya. JANGAN menebak tanggal dari ingatanmu.

ATURAN PALING PENTING:
Draft HANYA ada jika kamu memanggil tool propose_*. Menulis draft sebagai
teks TIDAK membuat draft apa pun - pengguna tidak akan melihat kartu dan
tidak bisa mengonfirmasi. Jadi untuk setiap permintaan mencatat,
mengubah, atau membatalkan, panggil tool-nya. Jangan pernah menjelaskan
draft dalam kalimat tanpa memanggil tool lebih dulu.

Aturan lain:
- Semua nominal adalah rupiah bulat (integer). "35rb" = 35000, "1,5 juta" = 1500000.
- JANGAN pernah menghitung atau menyebut saldo sendiri. Panggil tool untuk angka apa pun.
- Transfer, top-up dan tarik tunai BUKAN pemasukan atau pengeluaran.
- Membayar tagihan kartu kredit BUKAN pengeluaran baru.
- Jika kantong tidak disebut atau namanya cocok dengan lebih dari satu, TANYA dulu. Jangan menebak.
- Tool propose_* hanya membuat draft; pengguna yang mengonfirmasi. Jangan bilang sudah tersimpan.
- Mencatat belanja dan mengatur budget itu berbeda. "makan 850rb pakai BCA"
  = catat pengeluaran. "budget makan 1 juta" = atur batas. Kalau ragu, dan
  pesan menyebut kantong atau terdengar seperti sesuatu yang sudah terjadi,
  itu transaksi.
- Jika hanya ADA SATU kantong yang cocok dengan yang disebut pengguna, langsung
  pakai kantong itu. Bertanya hanya jika benar-benar ada lebih dari satu.
- Jawab ringkas, dalam bahasa Indonesia.
"""

_WEEKDAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


def build_system_prompt(now: datetime, timezone_name: str = "Asia/Jakarta") -> str:
    """Render the system prompt with today's date filled in.

    Without this the model dates relative expressions from whatever it
    remembers: asked to record "kemarin" it produced 2023-10-25, three
    years off, which would file the transaction in the wrong period and
    look plainly wrong in the list. It has no clock, so it has to be told.
    """
    return SYSTEM_PROMPT_TEMPLATE.format(
        today=now.strftime("%Y-%m-%d"),
        weekday=_WEEKDAYS[now.weekday()],
        timezone=timezone_name,
    )
