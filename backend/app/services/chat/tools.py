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
            "name": "run_simulation",
            "description": (
                "Hitung simulasi. TIDAK mengubah data apa pun, jadi tidak perlu "
                "konfirmasi. Tiga jenis: 'deposit' untuk bunga deposito, 'saving' "
                "untuk menabung rutin tanpa bunga, 'capacity' untuk memperkirakan "
                "kemampuan menabung per bulan dari riwayat pengguna."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["deposit", "saving", "capacity"]},
                    "principal": dict(_AMOUNT, description="Pokok, untuk deposit"),
                    "annual_rate_percent": {
                        "type": "string",
                        "description": "Bunga per tahun, contoh '4' atau '4.25'",
                    },
                    "months": {"type": "integer", "description": "Tenor dalam bulan"},
                    "tax_percent": {
                        "type": "string",
                        "description": (
                            "Tarif pajak. Kosongkan jika pengguna tidak menyebut - "
                            "hasilnya akan ditandai belum lengkap, jangan diklaim pasti."
                        ),
                    },
                    "fees": dict(_AMOUNT, description="Biaya, 0 jika tidak ada"),
                    "target": dict(_AMOUNT, description="Target, untuk saving"),
                    "initial": dict(_AMOUNT, description="Dana awal, untuk saving"),
                    "periods": {
                        "type": "integer",
                        "description": "Jumlah setoran untuk saving (boleh juga pakai 'months')",
                    },
                },
                "required": ["kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_transactions",
            "description": (
                "Daftar transaksi TERBARU, lengkap dengan kategori, merchant dan "
                "catatannya. Gunakan untuk menjawab pertanyaan atau menemukan "
                "transaksi yang ingin dikoreksi atau dipindah kategorinya. "
                "Isi 'category' untuk menyaring satu kategori saja - itu cara "
                "menemukan transaksi yang mau dipindah, jangan menanyakan "
                "nominalnya ke pengguna."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maksimal 50", "default": 20},
                    "category": {
                        "type": "string",
                        "description": "Opsional. Hanya transaksi dengan kategori ini.",
                    },
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
                "Jika HANYA ADA SATU transaksi dan kantongnya ambigu atau tidak "
                "disebut, tanyakan dulu, jangan menebak. Kalau transaksinya "
                "BEBERAPA, kosongkan saja from_account/to_account yang tidak "
                "disebut - penggunanya yang memilih di kartu konfirmasi, dan "
                "bertanya akan membuang rincian lain yang sudah benar."
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
                                        "'transfer' HANYA untuk memindahkan uang "
                                        "antar kantong pengguna SENDIRI - top-up "
                                        "e-wallet, tarik tunai, pindah antar "
                                        "rekening. Mengirim uang ke ORANG LAIN "
                                        "('tf ke ibu', 'bayar ke teman', 'kirim ke "
                                        "penjual') adalah 'expense' dari kantong "
                                        "sumber, dengan nama orangnya di 'merchant'. "
                                        "PENTING - belanja PAKAI kartu kredit adalah "
                                        "'expense' dengan from_account = kartunya, "
                                        "BUKAN card_payment. Pakai 'card_payment' hanya "
                                        "ketika pengguna MEMBAYAR TAGIHAN kartu "
                                        "('bayar tagihan', 'lunasi kartu'); di situ "
                                        "from_account adalah rekening yang membayar dan "
                                        "to_account adalah kartunya."
                                    ),
                                },
                                "amount": _AMOUNT,
                                "from_account": dict(
                                    _ACCOUNT,
                                    description=(
                                        "Kantong sumber. Untuk card_payment ini "
                                        "rekening yang MEMBAYAR, bukan kartunya."
                                    ),
                                ),
                                "to_account": dict(
                                    _ACCOUNT,
                                    description=(
                                        "Kantong tujuan. Untuk card_payment isi "
                                        "dengan KARTU yang tagihannya dibayar."
                                    ),
                                ),
                                "category": {
                                    "type": "string",
                                    "description": (
                                        "Jenis transaksinya, satu-dua kata: Makan, "
                                        "Transport, Belanja, Tagihan, Kesehatan, "
                                        "Keluarga. Bukan kalimat. PAKAI ULANG "
                                        "kategori yang sudah ada kalau artinya "
                                        "sama - 'ongkos' masuk ke 'Transport', "
                                        "bukan kategori sendiri."
                                    ),
                                },
                                "fee": dict(_AMOUNT, description="Biaya admin, jika ada"),
                                "occurred_on": {
                                    "type": "string",
                                    "description": "Tanggal YYYY-MM-DD, kosongkan jika hari ini",
                                },
                                "merchant": {
                                    "type": "string",
                                    "description": (
                                        "Ke SIAPA atau di MANA uangnya pergi: nama "
                                        "orang, toko, atau layanan. 'Ibu', 'APTB', "
                                        "'Indomaret'. Kosongkan kalau tidak disebut."
                                    ),
                                },
                                "note": {
                                    "type": "string",
                                    "description": (
                                        "Ringkasan SATU KALIMAT tentang UNTUK APA "
                                        "uangnya, pakai kata-kata penggunanya sendiri. "
                                        "ISI SETIAP KALI pesannya menyebut alasan atau "
                                        "konteks. Contoh: 'tf ke ibu buat top up "
                                        "pulsa', 'ongkos bus APTB berangkat kerja'. "
                                        "Jangan ulang nominal atau nama kantong - itu "
                                        "sudah disimpan terpisah."
                                    ),
                                },
                            },
                            "required": ["type", "amount"],
                        },
                    },
                    "stated_total": {
                        "type": "integer",
                        "description": (
                            "Isi HANYA kalau pengguna menyebut total keseluruhan di "
                            "samping rinciannya, misal 'ngeluarin 150rb: obat 50rb, "
                            "makan 70rb, minum 30rb' -> stated_total 150000. "
                            "JANGAN pernah memasukkan angka total itu sebagai "
                            "transaksi tambahan di 'transactions'; itu bikin "
                            "pengeluarannya kehitung dua kali. Backend yang "
                            "mencocokkan total dengan rinciannya."
                        ),
                    },
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
                "Buat draft PEMBATALAN sebuah transaksi: catatannya dibalik dan "
                "saldo kantongnya kembali seperti semula. Pakai hanya kalau "
                "transaksinya memang tidak terjadi atau salah catat. "
                "JANGAN pakai untuk sekadar mengganti kategori - itu "
                "propose_recategorise. Gunakan find_transactions lebih dulu untuk "
                "mendapatkan id-nya. Jika ada beberapa kandidat, minta pengguna "
                "memilih, jangan menebak."
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
    {
        "type": "function",
        "function": {
            "name": "propose_recategorise",
            "description": (
                "Buat draft PEMINDAHAN KATEGORI. Transaksinya tetap ada, nominalnya "
                "tetap, saldo kantong TIDAK berubah - yang pindah cuma kategorinya. "
                "Dipakai untuk 'ubah kategori jadi X', 'ongkos itu masuk transport', "
                "'gabung kategori A ke B'. "
                "Sebut 'transaction_id' untuk satu transaksi saja, atau "
                "'from_category' untuk memindahkan SEMUA transaksi di kategori itu "
                "sekaligus (menggabungkan dua kategori). Pilih salah satu, jangan "
                "dua-duanya."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "UUID satu transaksi, dari find_transactions",
                    },
                    "from_category": {
                        "type": "string",
                        "description": (
                            "Nama kategori asal, untuk memindahkan semua isinya"
                        ),
                    },
                    "to_category": {
                        "type": "string",
                        "description": "Nama kategori tujuan, satu-dua kata",
                    },
                },
                "required": ["to_category"],
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
Gunakan tanggal itu untuk menafsirkan waktu relatif. JANGAN menebak
tanggal dari ingatanmu.

Arti kata waktu:
- "tadi", "tadi pagi", "tadi siang", "barusan" = HARI INI, bukan kemarin.
- "tadi malam", "semalam" = malam kemarin, jadi KEMARIN.
- "kemarin" = kemarin. "kemarin lusa" = dua hari lalu.

ATURAN PALING PENTING:
Draft HANYA ada jika kamu memanggil tool propose_*. Menulis draft sebagai
teks TIDAK membuat draft apa pun - pengguna tidak akan melihat kartu dan
tidak bisa mengonfirmasi. Jadi untuk setiap permintaan mencatat,
mengubah, atau membatalkan, panggil tool-nya. Jangan pernah menjelaskan
draft dalam kalimat tanpa memanggil tool lebih dulu.

JANGAN MINTA KONFIRMASI LEWAT TEKS.
Jangan pernah menulis daftar transaksi lalu bertanya "apakah ini sudah
benar?" atau "beri tahu saya kalau ada yang salah". KARTU yang bertanya,
bukan kamu: pengguna memeriksa angkanya di kartu lalu menggeser untuk
menyimpan. Kalau kamu bertanya lewat teks, pengguna menjawab "ok" dan
TIDAK ADA APA PUN yang terjadi - dia terjebak mengulang hal yang sama.
Begitu kamu tahu nominal dan jenisnya, langsung panggil tool-nya.

Kalau pengguna menyebut BEBERAPA transaksi dalam satu pesan, panggil
propose_transactions SEKALI dengan semua item di dalam array
'transactions'. Jangan dipecah jadi beberapa panggilan, dan jangan
menuliskannya sebagai daftar bernomor di teks.

Aturan lain:
- Semua nominal adalah rupiah bulat (integer). "35rb" = 35000, "1,5 juta" = 1500000.
- JANGAN pernah menghitung atau menyebut saldo sendiri. Panggil tool untuk angka apa pun.
- "Transfer" di sini berarti uang pindah ANTAR KANTONG PENGGUNA SENDIRI
  (top-up e-wallet, tarik tunai, pindah antar rekening). Itu bukan
  pemasukan dan bukan pengeluaran, karena totalnya tidak berubah.
- Tapi "transfer" dalam bahasa sehari-hari sering berarti MENGIRIM UANG
  KE ORANG LAIN: "tf ke ibu 300rb", "bayar ke temen", "kirim ke penjual".
  Itu PENGELUARAN - uangnya benar-benar keluar. Pakai 'expense' dari
  kantong sumber, dan taruh nama penerimanya di 'merchant'. Orang bukan
  kantong, jadi jangan cari kantong bernama "Ibu".
- Membayar tagihan kartu kredit BUKAN pengeluaran baru.
- Jika kantong tidak disebut atau namanya cocok dengan lebih dari satu, TANYA dulu. Jangan menebak.
- Tool propose_* hanya membuat draft; pengguna yang mengonfirmasi. Jangan bilang sudah tersimpan.
- Mencatat belanja dan mengatur budget itu berbeda. "makan 850rb pakai BCA"
  = catat pengeluaran. "budget makan 1 juta" = atur batas. Kalau ragu, dan
  pesan menyebut kantong atau terdengar seperti sesuatu yang sudah terjadi,
  itu transaksi.
- Jika hanya ADA SATU kantong yang cocok dengan yang disebut pengguna, langsung
  pakai kantong itu. Bertanya hanya jika benar-benar ada lebih dari satu.
- Setiap transaksi punya tiga keterangan, dan ketiganya beda:
  'category' = jenisnya (Makan, Transport, Keluarga) - satu-dua kata;
  'merchant' = ke siapa atau di mana (Ibu, APTB, Indomaret);
  'note' = untuk apa uangnya, satu kalimat pakai kata-kata penggunanya.
  Kalau pesannya menyebut alasan atau konteks, SELALU tulis 'note'.
  "abis tf 300rb ke ibu buat topup saldo pulsa, pake bank jago"
  -> expense 300000, from_account "bank jago", merchant "Ibu",
     category "Keluarga", note "tf ke ibu buat top up saldo pulsa".
  "spend 25rb buat ongkos bus APTB berangkat kerja"
  -> expense 25000, merchant "APTB", category "Transport",
     note "ongkos bus APTB berangkat kerja".
- PAKAI ULANG kategori yang sudah ada. Kalau pengguna bilang "ongkos"
  sedangkan dia sudah punya kategori "Transport", pakai "Transport" -
  kata yang dia ucapkan masuk ke 'note', bukan jadi kategori baru.
  Kategori baru hanya untuk sesuatu yang benar-benar belum ada
  padanannya. Satu hal dengan dua nama akan muncul sebagai dua baris di
  laporan dan membuat budgetnya meleset.
- Mengubah kategori sebuah transaksi atau menggabungkan dua kategori
  BUKAN membatalkan transaksi. Pakai propose_recategorise; uangnya tidak
  bergerak dan saldo tidak berubah. propose_correction itu untuk
  MENGHAPUS transaksi yang salah catat, dan saldonya ikut kembali.
- Jawab ringkas, dalam bahasa Indonesia.
"""

_WEEKDAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


def build_system_prompt(
    now: datetime,
    timezone_name: str = "Asia/Jakarta",
    wallets: list[tuple[str, str, str | None]] | None = None,
    categories: list[str] | None = None,
) -> str:
    """Render the system prompt with today's date, wallets and categories.

    The date matters because the model has no clock: asked to record
    "kemarin" without it, it produced 2023-10-25, three years off.

    The wallet list matters because otherwise the model invents names.
    Asked to spend "pakai cc" it sent the account name "credit_card" -
    substituting the type for the name - and the lookup failed. Listing
    what actually exists turns naming from a guess into a choice, and
    costs a handful of tokens.

    The category list is there for the same reason, and was learned the
    same way: unprompted, the model named one month's bus fares
    "Transport" and the next one's "ongkos", and the breakdown grew two
    rows for one thing. Nothing in the schema could have stopped that -
    the categories are the user's own words, so the only way to reuse
    one is to have seen it.

    ``wallets`` is ``(name, type, alias)``.
    """
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        today=now.strftime("%Y-%m-%d"),
        weekday=_WEEKDAYS[now.weekday()],
        timezone=timezone_name,
    )

    if wallets:
        listed = "\n".join(
            f"- {name} ({kind}" + (f", alias: {alias}" if alias else "") + ")"
            for name, kind, alias in wallets
        )
        prompt += (
            "\n\nKantong yang dimiliki pengguna saat ini:\n"
            + listed
            + "\n\nGunakan PERSIS nama di daftar itu saat memanggil tool. "
            "Jangan mengarang nama lain dan jangan memakai jenis kantong "
            "sebagai nama. Kalau yang disebut pengguna tidak ada di daftar, "
            "katakan kantong itu belum ada."
        )

    if categories:
        prompt += (
            "\n\nKategori yang sudah dipakai pengguna:\n"
            + "\n".join(f"- {name}" for name in categories)
            + "\n\nPilih dari daftar itu kalau ada yang artinya sama, "
            "walaupun pengguna memakai kata lain. Bikin kategori baru "
            "hanya kalau benar-benar tidak ada padanannya."
        )

    return prompt
