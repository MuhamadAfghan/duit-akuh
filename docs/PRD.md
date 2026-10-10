<!-- Generated from PRD_Keuangan_AI_Web_v1.docx (v1.1, 10 Oktober 2026).
     The .docx at the repo root is the source of truth; this is a text
     mirror so the PRD is readable and greppable. Re-generate if the
     .docx changes. -->

PRD Aplikasi Keuangan Pribadi Berbasis AI
Product Requirements Document | Versi 1.1 | 10 Oktober 2026
Web/PWA dengan satu chat sebagai pusat kontrol seluruh fitur. Kantong uang, transaksi, target, budget dan simulasi dikelola melalui percakapan, dengan kartu dan grafik interaktif dari data yang sama. Nama produk ditentukan kemudian.

## 1 Tujuan produk

Membantu pengguna mencatat transaksi tanpa banyak mengisi form, mengetahui uang tersimpan di mana, dan menyusun target yang sesuai kemampuan. Pola interaksi terinspirasi Finvo; implementasi produk tidak mengharuskan penggunaan atau fork kode Finvo.

## Masalah yang diselesaikan

Uang tersebar di rekening, e-wallet, cash, dan kartu sehingga posisi saldo sulit dipahami.
Pencatatan manual mudah tertunda; transfer dan pembayaran tagihan berisiko dihitung sebagai pengeluaran ganda.
Target tabungan belum terhubung dengan pengeluaran, kewajiban, dan dana yang benar-benar tersedia.

## Pengguna dan prinsip pengalaman

Pengguna utama adalah individu di Indonesia yang menerima pemasukan, memakai beberapa sumber dana, dan menabung untuk kebutuhan tertentu. MVP menggunakan akun pribadi terisolasi, mata uang IDR, bahasa Indonesia, dan zona waktu Asia/Jakarta yang dapat diubah.
Chat adalah halaman utama: pengguna dapat menambah kantong, mencatat transaksi, membuat target, mengatur budget dan menjalankan simulasi. Kartu konfirmasi serta visual muncul dalam obrolan; dashboard menjadi tampilan pendamping. Backend menghitung dan memvalidasi seluruh perubahan.

## 2 Batas rilis yang diusulkan

[TABLE]
Tahap | Cakupan
MVP | Web/PWA, login, satu chat untuk seluruh fitur MVP, kantong dan kartu, transaksi, transfer, target, alokasi, budget, simulasi, ekspor CSV, serta kartu dan dashboard visual.
Tahap 2 | Suara, OCR struk, impor mutasi dan rekonsiliasi, transaksi rutin, pengingat, pencatatan deposito aktual dan jatuh tempo.
Tahap 3 | Ruang keluarga, akses bersama, multi-currency, konektor bank resmi, data produk simpanan yang diperbarui otomatis.
[/TABLE]
Di luar MVP: transfer uang sungguhan, pembukaan deposito, pengajuan kredit, perdagangan investasi, pembukuan perusahaan, dan rekomendasi produk bank berdasarkan data yang belum diverifikasi. Tahapan merupakan usulan prioritas untuk perencanaan backlog.

# 3 Satu chat sebagai pusat aplikasi

## Alur pertama kali menggunakan aplikasi

Setelah autentikasi, pengguna masuk ke satu obrolan utama yang berlanjut antar-sesi dan perangkat. AI memandu pengaturan zona waktu, pembuatan kantong, saldo awal, akun default opsional, transaksi pertama, dan target melalui chat serta kartu input di dalamnya.
Contoh: “Tambah BCA saldo 5 juta, cash 300 ribu, lalu bikin target laptop 15 juta dalam 6 bulan.” Sistem menyajikan rencana tindakan, meminta sumber dana awal target, dan menampilkan konfirmasi sebelum menyimpan.

## Permukaan utama dan visual pendamping

[TABLE]
Permukaan | Peran
Chat utama | Pusat semua tindakan dan pertanyaan. Tidak perlu pindah ke obrolan terpisah per kantong, target, atau modul.
Kartu dalam chat | Ringkasan akun, draft transaksi, form singkat, progres target, perbandingan skenario, tombol konfirmasi, edit, dan batal.
Dashboard visual | Saldo per kantong, pengeluaran, utang, uang bebas pakai, grafik dan target; seluruhnya memakai data yang sama dengan chat.
Detail dan daftar | Daftar transaksi, kantong dan target tetap dapat dibuka. Aksi “Bahas di chat” membawa objek serta periodenya ke obrolan utama.
Navigasi mobile | Chat sebagai tab default; Ringkasan dan Data sebagai akses pendamping. Panel detail tidak menghilangkan draft atau posisi percakapan.
[/TABLE]

## Alur perintah umum

Pesan → identifikasi tindakan dan objek → susun draft/rencana → klarifikasi data yang kurang → tampilkan dampak dalam kartu → konfirmasi → validasi backend dan simpan → perbarui visual → tampilkan hasil dalam chat yang sama.
Tindakan baca, filter, dan simulasi tidak memerlukan konfirmasi. Semua perubahan catatan finansial menampilkan dampak sebelum disimpan. Penghapusan, perubahan akses dan data sensitif selalu memakai konfirmasi eksplisit serta autentikasi ulang bila diperlukan.

## Hubungan chat dengan visual

“Tampilkan uang gua ada di mana” menghasilkan kartu saldo dan grafik distribusi. “Naikkan target laptop jadi 18 juta” menghasilkan preview kebutuhan setoran baru. Setelah disetujui, kartu target dan dashboard diperbarui dari hasil penyimpanan yang sama.

## Ketika data atau koneksi belum tersedia

Tanpa akun, AI membantu membuatnya. Data tidak cukup, AI meminta asumsi. AI gagal, input manual tetap tersedia sebagai alternatif. Offline tidak boleh menampilkan keberhasilan palsu; draft tidak hilang saat pindah layar. Saldo awal bukan pemasukan dan saldo tercatat bukan saldo bank real-time.

# 4 Kantong uang dan aturan transaksi

## FR01 Akun dan jenis tempat uang

Pengguna dapat membuat, mengubah nama, dan mengarsipkan akun. Field minimum: nama, jenis, IDR, saldo pembukaan, tanggal pembukaan, dan alias percakapan. Akun dengan riwayat tidak dihapus permanen melalui aksi biasa.

[TABLE]
Jenis | Aturan
Bank, e-wallet, cash | Masing-masing memiliki saldo dan riwayat sendiri. Saldo boleh negatif hanya setelah peringatan dan konfirmasi eksplisit untuk mencerminkan catatan aktual.
Kartu debit | Instrumen pembayaran yang tertaut ke satu rekening. Tidak mempunyai saldo tambahan.
Kartu kredit | Mencatat limit, utang awal, tanggal cetak tagihan dan jatuh tempo. Limit tersedia bukan aset atau uang bebas pakai.
Kantong tujuan | Alokasi virtual atas saldo rekening, bukan akun aset baru. Satu target dapat didanai dari beberapa akun.
[/TABLE]

## FR02 Jenis transaksi dan dampaknya

[TABLE]
Peristiwa | Perlakuan wajib
Pemasukan / pengeluaran | Menambah / mengurangi saldo sumber terkait dan masuk laporan kategori.
Transfer / tarik tunai / top-up | Dua sisi tercatat dalam satu transaksi atomik; tidak menjadi pendapatan atau pengeluaran. Biaya admin dicatat terpisah sebagai pengeluaran.
Belanja kartu kredit | Pengeluaran diakui saat belanja; utang kartu bertambah. Pembayaran utang mengurangi saldo bank dan utang tanpa mengulang pengeluaran.
Refund | Tautkan ke transaksi asal; kurangi pengeluaran kategori asal dan pulihkan saldo atau kurangi utang kartu.
Koreksi / pembatalan | Buat jejak revisi atau reversal yang dapat ditelusuri; hitung ulang saldo. Jangan menghilangkan riwayat diam-diam.
[/TABLE]

## FR03 Integritas catatan

Nominal disimpan sebagai integer rupiah atau decimal presisi tetap, bukan floating point. Setiap posting memiliki ID unik dan kunci idempotensi.
Perubahan terkait akun, transaksi, dan alokasi dilakukan atomik. Dua perangkat yang mengedit versi sama harus mendapat deteksi konflik.
Transfer dana yang telah dialokasikan harus menawarkan pemindahan alokasi. Pengeluaran yang mengurangi saldo di bawah alokasi memerlukan keputusan pelepasan alokasi sebelum posting.
Semua transaksi menyimpan pemilik, waktu kejadian, waktu dibuat, kategori, akun, catatan, sumber input, status, dan versi.

# 5 Pencatatan dan tanya jawab AI

## FR04 Percakapan untuk membuat transaksi

AI mendukung nominal informal Indonesia seperti “35 ribu”, “35rb”, dan “1,5 juta”, tanggal relatif seperti “kemarin”, serta beberapa transaksi dalam satu pesan. Tanggal relatif mengacu zona waktu pengguna saat pesan dikirim. Interpretasi ditampilkan dalam draft.
Perintah selain transaksi mengikuti pola draft, klarifikasi dan konfirmasi yang sama. Seluruh cakupan tindakan chat ditetapkan pada bagian 11.
Field draft: jenis transaksi, nominal, akun sumber/tujuan, kategori, tanggal, merchant opsional, catatan, dan referensi pesan. Sumber tidak disebutkan: tawarkan akun default yang terlihat atau tanyakan. Alias “BCA” yang cocok dengan dua akun wajib diklarifikasi.

## FR05 Konfirmasi dan koreksi

MVP mewajibkan konfirmasi sebelum semua perubahan finansial dari chat. Pengguna dapat mengedit field sebelum menyimpan.
Perintah “yang makan tadi 30 ribu” menampilkan transaksi kandidat. Bila ada beberapa kandidat, pengguna memilih; sistem tidak menebak transaksi sasaran.
Timeout saat konfirmasi diperiksa melalui ID operasi. Sistem mengembalikan hasil posting sebelumnya bila sudah berhasil.
Balasan sukses menyebut nominal, tanggal, akun, kategori, dan tautan detail. Draft gagal tidak mengubah saldo.

## FR06 Pertanyaan tentang data

[TABLE]
Contoh pertanyaan | Keluaran
Saldo BCA berapa | Saldo tercatat dan waktu pembaruan; minta pilihan bila akun ambigu.
Uang paling banyak di mana | Urutan akun aset; kartu debit tidak dihitung ulang dan limit kredit dikecualikan.
Bulan ini makan berapa | Total kategori makan dengan periode, refund, dan tautan transaksi pendukung.
Bisa nabung dua juta | Estimasi berdasarkan model kapasitas pada bagian 7, asumsi, dan alternatif.
Uang bebas pakai berapa | Rincian saldo likuid dikurangi alokasi dan cadangan kewajiban tanpa pengurangan ganda.
[/TABLE]

## Batas dan mekanisme AI

LLM mengusulkan tindakan terstruktur untuk seluruh modul melalui tool yang diizinkan. Backend memeriksa otorisasi, field, konsistensi dan konfirmasi. Kartu UI hanya merender skema komponen yang diizinkan. Saldo, bunga dan progres dihitung fungsi teruji, bukan angka karangan model.
Konteks percakapan memakai riwayat yang relevan. Preferensi yang disimpan dapat dilihat dan dihapus. Konten struk atau mutasi diperlakukan sebagai data, bukan instruksi yang dapat mengubah aturan sistem.
Provider pertama untuk MVP dipilih saat implementasi. Gunakan lapisan adapter agar dapat beralih ke model cloud atau lokal; dukungan keduanya tidak berarti kualitas bahasa dan kemampuan tool pasti sama.

# 6 Target keuangan dan budgeting

## FR07 Target dan alokasi dana

Field target: nama, nominal, tanggal tujuan, prioritas, dana awal, akun pendanaan, frekuensi setoran, dan status aktif, jeda, tercapai, atau dibatalkan. Dana awal harus ditautkan ke saldo yang sudah ada; tidak boleh menambah aset baru.
Satu target boleh memiliki alokasi di banyak akun. Jumlah semua alokasi aktif pada satu akun tidak boleh melebihi saldo positifnya. Memindahkan alokasi antar-target memerlukan konfirmasi dan tidak dianggap transfer bank.

## Perhitungan progres

Dana terkumpul = total alokasi yang masih valid untuk target tersebut.
Kekurangan = maksimum nol atau nominal target dikurangi dana terkumpul.
Kebutuhan per setoran = kekurangan dibagi jumlah tanggal setoran tersisa, dibulatkan ke atas dalam rupiah. Jadwal setoran pertama harus dipilih agar “6 bulan” tidak ambigu.
Progres = dana terkumpul dibagi nominal target. Tampilkan maksimum 100% di indikator dan nominal kelebihan secara terpisah.
Target dengan tenggat lewat diberi status perlu penyesuaian, bukan membagi dengan nol. Saat target dipakai untuk belanja, tampilkan opsi realisasi: lepas alokasi dan catat pengeluaran terkait dalam satu tindakan terkonfirmasi.

## FR08 Budget per kategori

Pengguna mengatur budget bulanan kategori, melihat realisasi dan sisa, serta mendapat indikator saat mendekati atau melewati batas. Realisasi mencakup belanja cash, bank, dan kartu kredit, dikurangi refund; transfer dan pembayaran pokok kartu tidak dihitung sebagai belanja baru.
Budget adalah batas rencana belanja, bukan saldo aset atau alokasi tabungan. Sistem tidak otomatis mengurangi saldo bebas pakai dengan seluruh budget; hanya cadangan pengeluaran yang secara eksplisit dipilih pengguna yang mengurangi estimasi tersebut.

## FR09 Dashboard yang tidak menggandakan uang

[TABLE]
Indikator | Definisi produk
Saldo likuid | Saldo bank, e-wallet, dan cash; tidak mencakup deposito terkunci atau limit kartu.
Aset bersih tercatat | Semua aset tercatat dikurangi seluruh kewajiban tercatat; cakupan ditampilkan.
Dana target | Jumlah alokasi valid, ditampilkan sebagai bagian dari aset.
Uang bebas pakai | Saldo likuid dikurangi gabungan alokasi pada aset likuid, cadangan kebutuhan, dan cadangan kewajiban. Pos dana yang sama dihitung sekali.
Kekurangan dana | Jika uang bebas pakai negatif, tampilkan nilainya sebagai kekurangan; jangan disembunyikan dengan angka nol.
[/TABLE]

# 7 Analisis kemampuan menabung

## FR10 Model kapasitas

Mesin analisis memakai proyeksi arus kas: pemasukan yang dapat diandalkan dikurangi pengeluaran kas, kewajiban yang akan dibayar, dan cadangan yang dipilih pengguna. Setoran target yang sudah disepakati lalu dikurangi untuk memperoleh kapasitas target baru.
Default analisis memakai tiga bulan kalender lengkap. Jika kurang, tampilkan jumlah bulan/hari yang tersedia dan minta konfirmasi estimasi manual. Transfer internal, saldo awal, dan pemasukan satu kali yang ditandai pengguna dikecualikan dari pemasukan rutin.
Model kapasitas berbeda dari laporan pengeluaran: untuk proyeksi cash flow, pembayaran tagihan kartu diperhitungkan pada tanggal pembayaran; belanja kredit yang membentuk tagihan tersebut tidak dikurangi lagi pada horizon yang sama. Simpan hubungan antara tagihan dan transaksi agar tidak ganda.

## Input dan keluaran analisis

[TABLE]
Input | Keluaran
Pemasukan rutin dan tanggalnya | Perkiraan pemasukan tiap periode beserta sumber data atau input pengguna.
Pengeluaran, tagihan, cadangan | Perkiraan kebutuhan kas; pengeluaran tetap dan variabel terlihat terpisah.
Target, tenggat, prioritas | Kebutuhan setoran dan selisih terhadap kapasitas tersedia.
Skenario perubahan | Dampak perubahan tenggat, target, setoran awal, dan pengeluaran terhadap rencana.
[/TABLE]

## FR11 Simulasi skenario

Contoh uji produk: target laptop Rp15 juta, dana awal Rp3 juta, enam setoran bulanan, tanpa bunga. Kekurangan Rp12 juta dan kebutuhan Rp2 juta per bulan. Jika kapasitas Rp1,5 juta per bulan, alternatifnya delapan setoran, tambahan dana awal Rp3 juta, atau tambahan kapasitas Rp500 ribu per bulan.
Pengguna dapat mengubah input dan melihat hasil langsung. Skenario tidak memindahkan saldo atau mengubah target aktif sebelum pengguna memilih “Terapkan rencana”. Rencana tersimpan mempertahankan input, waktu kalkulasi, dan versi formula.

## Prioritas banyak target

Dana cadangan dan kewajiban ditetapkan terlebih dahulu. Sistem menawarkan pembagian kapasitas sisa berdasarkan prioritas atau nominal setoran pilihan pengguna. Total rekomendasi semua target tidak boleh melebihi kapasitas yang sama.

## Evaluasi berkala

MVP memperbarui progres saat transaksi/alokasi berubah dan mengevaluasi jadwal ketika halaman dibuka. Tahap 2 menambahkan ringkasan berkala dan notifikasi. Target yang tertinggal menampilkan selisih terhadap jadwal serta pilihan perubahan; aplikasi tidak mengubah rencana otomatis.

# 8 Simulasi tabungan dan deposito

## FR12 Perbandingan berbasis asumsi pada MVP

Pengguna membandingkan penyimpanan dana dengan mempertimbangkan tenggat target, kebutuhan pencairan, dana darurat, tenor, minimum penempatan, biaya, pajak, dan hasil bersih. MVP memakai input pengguna; tidak mengklaim memiliki daftar bunga bank terbaru atau menjamin hasil.

[TABLE]
Input simulasi | Aturan
Pokok dan tenor | Nominal positif; satuan hari/bulan dinyatakan jelas; tanggal mulai dan selesai ditampilkan.
Bunga tahunan | Persentase input pengguna; tampilkan sumber dan tanggal bila menggunakan data produk.
Metode bunga | MVP bunga sederhana dengan basis hari yang dipilih 360/365 atau metode bulan/12. Metode produk yang berbeda diberi status belum didukung.
Pajak dan biaya | Input eksplisit; nol hanya jika dikonfirmasi. Jika belum diketahui, hasil bersih ditandai belum lengkap.
Pencairan dan penalti | Aturan input pengguna. Jika tidak diketahui, aplikasi tidak mengarang penalti.
Tanggal target | Peringatan jika jatuh tempo penempatan melewati waktu uang dibutuhkan.
[/TABLE]

## Formula dan contoh validasi

Bunga bruto = pokok × suku bunga tahunan × fraksi tahun. Pajak simulasi = bunga bruto × tarif input. Hasil bersih = bunga bruto − pajak − biaya. Nilai akhir = pokok + hasil bersih. Pembulatan akhir ke rupiah terdekat; presisi antara dipertahankan.
Contoh sintetis untuk pengujian, bukan tarif produk: pokok Rp10 juta, bunga 4% per tahun, tenor 6/12 tahun, tarif pajak input 20%, tanpa biaya. Bunga bruto Rp200.000, pajak Rp40.000, hasil bersih Rp160.000, nilai akhir Rp10.160.000.
Simulasi tabungan rutin MVP memakai bunga nol sebagai baseline. Perhitungan bunga bertingkat, saldo harian, dan bunga majemuk menjadi perluasan; jangan membandingkan hasil yang metodenya tidak sepadan tanpa label.

## FR13 Pencatatan deposito aktual pada tahap 2

Field: bank, pokok, rekening asal/penerima, tanggal mulai, tenor, jatuh tempo, rate, metode bunga, biaya/pajak, dan instruksi perpanjangan. Penempatan memindahkan aset likuid ke aset deposito. Pokok saat cair bukan pemasukan; bunga aktual dicatat sebagai pemasukan terpisah.
Estimasi bunga tidak menambah saldo aktual. Perpanjangan otomatis pada bank dicatat hanya setelah dikonfirmasi atau ada bukti transaksi. Pengingat tersedia sebelum jatuh tempo, dan alokasi target tetap mengikuti aset yang mendanainya.

# 9 Data dan persyaratan sistem

## Model data konseptual

[TABLE]
Entitas | Data dan hubungan utama
User dan Preferences | Identitas, zona waktu, bahasa, preferensi AI; seluruh data terikat owner; satu obrolan utama per pengguna.
Account dan Payment Instrument | Jenis, currency, opening balance/date, versi; kartu debit menunjuk rekening, kartu kredit menunjuk akun kewajiban.
Transaction dan Entry | Jenis, waktu, kategori, merchant, status; entry menghubungkan akun dan delta saldo. Transfer menyimpan dua sisi.
Goal dan Allocation | Target, tanggal, prioritas, jadwal; allocation menghubungkan target dengan akun atau deposito.
Budget dan Obligation | Batas kategori; kewajiban dan cadangan mempunyai ID agar tidak dihitung dua kali.
Conversation dan Draft | Thread utama, pesan, entity ID, versi objek, rencana tindakan, klarifikasi, konfirmasi dan operation ID; berlaku untuk semua modul.
Scenario dan Deposit | Asumsi, formula version, hasil; record deposito aktual tersedia pada tahap 2.
Audit Event | Pelaku, objek, waktu, versi sebelum/sesudah, alasan perubahan dan korelasi operasi.
[/TABLE]

## Arsitektur yang disarankan

Chat dan dashboard → API domain yang sama → layanan akun, transaksi, target dan kalkulasi → PostgreSQL. Orkestrator chat menyimpan rencana tindakan dan memanggil adapter AI; visual memakai objek dan versi hasil API. Worker terpisah menangani OCR, notifikasi, dan impor pada tahap 2. Rekomendasi stack: Next.js, FastAPI, PostgreSQL, Docker Compose; keputusan framework tetap terbuka.

## Privasi dan pengoperasian

HTTPS, session aman, pembatasan percobaan login, otorisasi per pemilik pada seluruh API, serta larangan akses lintas akun pengguna.
API key provider disimpan di server dan dienkripsi saat tersimpan. Jangan kirim nomor kartu lengkap, PIN, OTP bank, atau kredensial internet banking ke model.
Pengguna diberi tahu saat data dikirim ke AI cloud; self-host aplikasi tidak otomatis berarti inferensi lokal. Log aplikasi menyamarkan data sensitif.
Ekspor transaksi CSV tersedia di MVP. Penghapusan akun mencakup transaksi, lampiran dan chat; retensi backup serta waktu penghapusan dijelaskan sebelum konfirmasi.

## Target nonfungsional yang harus diuji

Uji pada viewport 375 px dan desktop, Safari iOS serta Chrome Android/desktop versi stabil saat rilis. Target usulan: dashboard p95 ≤2 detik pada 10.000 transaksi per pengguna; respons draft AI p95 ≤10 detik pada provider yang disepakati. Uji dengan 20 sesi aktif pada konfigurasi pilot yang dicatat. Backup harian; target RPO 24 jam dan RTO 4 jam dengan satu uji pemulihan sebelum pilot.

# 10 Kriteria penerimaan dan rencana rilis

[TABLE]
ID | Skenario penerimaan wajib
AC01 | Saldo awal bank Rp1 juta dan e-wallet Rp100 ribu menghasilkan aset Rp1,1 juta; pemasukan periode tetap nol.
AC02 | Top-up Rp100 ribu dengan admin Rp1.000: bank turun Rp101 ribu, e-wallet naik Rp100 ribu, pengeluaran Rp1.000.
AC03 | Belanja kartu Rp800 ribu lalu bayar penuh: pengeluaran tetap Rp800 ribu, utang nol; pembayaran tidak menggandakan belanja.
AC04 | Pesan akun ambigu tidak diposting. Konfirmasi yang dikirim dua kali membuat tepat satu transaksi.
AC05 | Alokasi target Rp2 juta dari saldo Rp5 juta tidak menaikkan aset. Alokasi melebihi saldo ditolak.
AC06 | Target 15 juta, dana 3 juta, enam setoran: hasil 2 juta per setoran; kapasitas 1,5 juta memberi alternatif delapan setoran.
AC07 | Contoh deposito bagian 8 menghasilkan bruto 200 ribu dan neto 160 ribu. Simulasi tidak mengubah saldo aktual.
AC08 | Koreksi 35 ribu menjadi 30 ribu memulihkan saldo 5 ribu dan menyimpan audit. Pengguna lain tidak dapat melihat objek tersebut.
AC09 | Provider AI mati: input manual berfungsi. Rekap kartu dan cash tidak menghitung ulang pembayaran kartu atau transfer.
AC10 | Ekspor sesuai filter dan jumlah transaksi; restore backup memulihkan saldo, target, alokasi, dan audit secara konsisten.
[/TABLE]

## Ukuran keberhasilan pilot yang diusulkan

Pada pilot empat minggu: ≥70% pengguna menyelesaikan onboarding dan transaksi pertama; ≥90% draft pada benchmark minimal 100 pesan Indonesia mempunyai nominal, akun, tanggal, dan jenis yang tepat sebelum koreksi; ≥50% pengguna aktif membuat satu target. Definisikan pengguna aktif sebagai pengguna dengan setidaknya satu transaksi terkonfirmasi per minggu.
Syarat mutlak rilis: nol selisih pada skenario saldo, transfer, kartu, dan alokasi; nol akses lintas pengguna pada pengujian; semua AC MVP lulus. Pantau waktu pencatatan, tingkat koreksi, kegagalan provider dan biaya AI per transaksi. Target pilot merupakan usulan, bukan hasil pengujian.

## Urutan pengerjaan dan keputusan terbuka

Urutan: fondasi akun dan ledger → orkestrator chat dan kartu tindakan → kendali chat semua modul MVP → target dan kalkulator → visual, ekspor, QA dan pilot. Deposit aktual, OCR dan voice menyusul setelah fondasi lolos; estimasi jadwal dibuat setelah kapasitas tim ditentukan.
Keputusan berikutnya: nama produk; provider AI dan anggaran; lokasi hosting; kanal login; persetujuan batas MVP; metode bunga tambahan; kanal notifikasi; kebijakan retensi. Kualitas bahasa Indonesia, Safari iOS, dan ketepatan nominal menjadi fokus validasi awal.

# 11 Cakupan kontrol chat dan visual

FR14 Seluruh fitur yang tersedia pada suatu tahap rilis wajib dapat dimulai dan diselesaikan dari chat utama, termasuk melalui tombol atau form inline. Login, izin perangkat dan autentikasi ulang boleh membuka dialog sistem; aplikasi tidak meminta password atau API key dalam pesan biasa.

[TABLE]
Area | Contoh kontrol melalui chat | Visual respons
Kantong dan kartu | Tambah, ubah nama, atur akun default, tautkan kartu debit, atur limit kredit, arsipkan. | Kartu akun dan preview perubahan.
Transaksi | Catat, transfer, cari, filter, koreksi, refund dan batalkan catatan. | Draft, daftar hasil, bukti simpan.
Target | Buat, ubah nominal/tenggat/prioritas, jeda, batalkan, realisasikan. | Progres dan kebutuhan setoran.
Alokasi dan budget | Alokasikan, pindahkan atau lepas dana; buat dan ubah budget kategori. | Saldo tersedia dan indikator budget.
Analisis | Tanya saldo, distribusi uang, pengeluaran, kemampuan menabung dan banding periode. | Angka, grafik dan sumber transaksi.
Simulasi | Ubah asumsi tabungan/deposito, bandingkan skenario, terapkan rencana. | Tabel perbandingan dan proyeksi.
Pengaturan dan data | Ubah preferensi, kategori, ekspor, hapus memori atau akun dengan konfirmasi aman. | Kontrol inline dan tautan unduhan.
Fitur tahap 2 | Kirim suara/struk/file, atur transaksi rutin, reminder dan deposito aktual melalui chat. | Upload, hasil ekstraksi, jadwal dan jatuh tempo.
[/TABLE]

## FR15 Konteks tindakan dan sinkronisasi

Referensi “kantong tadi” atau “target itu” diselesaikan ke ID objek yang jelas; bila ambigu, AI meminta pilihan. Riwayat boleh diringkas untuk konteks, tetapi keputusan memakai data terbaru dari backend. Kartu historis diberi waktu; kartu interaktif memeriksa versi sebelum aksi.
Satu pesan berisi beberapa perubahan menampilkan rencana dan dependensi. Semua aksi yang dikonfirmasi sebagai satu paket disimpan atomik atau seluruhnya gagal. Tindakan yang belum jelas tetap draft. Pembaruan di dashboard juga terlihat pada chat; jangan menyimpan saldo kedua di riwayat percakapan.

## Kriteria penerimaan tambahan

AC11: Dari chat kosong, pengguna membuat BCA bersaldo Rp5 juta dan target dengan alokasi Rp2 juta tanpa membuka modul lain; aset tetap Rp5 juta. AC12: Perubahan target melalui chat langsung terlihat di visual, dan perubahan dari visual dibaca benar oleh chat.
AC13: Paket aksi gagal di tengah tidak meninggalkan perubahan sebagian; retry dan tombol kartu lama tidak membuat duplikat. AC14: Setelah login ulang, obrolan berlanjut dengan objek yang sama; jika referensi ambigu atau versinya berubah, sistem meminta klarifikasi atau konfirmasi ulang.
