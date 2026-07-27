# Papan Pantau Indikator Pasar Indonesia

Dashboard otomatis (100% gratis, tanpa API key berbayar) yang memantau:

- USD/IDR
- CDS Indonesia 5Y
- Bond Indonesia 1Y
- Bond Indonesia 5Y
- IHSG
- Crude Oil (WTI)

Data diperbarui otomatis **5× sehari (08.00, 10.00, 12.00, 14.00, 16.00 WIB)** lewat GitHub Actions, lalu ditampilkan di halaman GitHub Pages (`index.html`).

## Cara pakai

1. Buat repository baru di GitHub (public — GitHub Pages gratis butuh repo public, kecuali kamu punya GitHub Pro/Team/Enterprise).
2. Upload semua file ini (`index.html`, `data.json`, `update.py`, `requirements.txt`, folder `.github/workflows/update.yml`) ke root repo.
3. Buka tab **Settings → Pages** di repo → pada "Build and deployment", pilih source **Deploy from a branch**, branch **main**, folder **/ (root)** → Save.
4. Buka tab **Settings → Actions → General** → pastikan di bagian "Workflow permissions" dipilih **Read and write permissions** (supaya workflow bisa commit `data.json` balik ke repo).
5. Buka tab **Actions**, pilih workflow **Update Market Data**, klik **Run workflow** untuk trigger manual pertama kali (tidak perlu menunggu jadwal cron).
6. Setelah workflow selesai (biasanya < 1 menit), `data.json` akan ter-update dan halaman GitHub Pages kamu (`https://<username>.github.io/<repo>/`) akan menampilkan data terbaru.

## Catatan penting soal sumber data

- **USDIDR**: dari Frankfurter API — stabil, gratis, tanpa key.
- **IHSG & Crude Oil (WTI)**: dari Yahoo Finance (unofficial endpoint) — umumnya stabil tapi bisa saja rate-limit sesekali. Kalau gagal, data lama tetap dipertahankan di `data.json`, tidak menghentikan workflow.
- **CDS Indonesia 5Y & Bond 1Y/5Y**: **tidak ada API resmi gratis** untuk data ini, jadi saya scrape halaman publik worldgovernmentbonds.com. Ini paling rapuh — jika mereka mengubah struktur HTML halaman, scraper bisa gagal ambil data (tapi tidak akan bikin workflow crash — cek field `last_run_status` di `data.json` untuk tahu sumber mana yang gagal).
- Kalau suatu saat scraping CDS/Bond berhenti berfungsi, cara termudah memperbaikinya: buka halaman sumbernya di browser, lihat struktur HTML terbaru (klik kanan → Inspect), lalu sesuaikan fungsi `fetch_cds_5y()` / `fetch_bond_yields()` di `update.py`.

## Jadwal cron

Workflow diatur jalan jam **01:00, 03:00, 05:00, 07:00, 09:00 UTC**, yang setara **08:00, 10:00, 12:00, 14:00, 16:00 WIB**. GitHub Actions cron kadang meleset beberapa menit dari jadwal karena antrian server GitHub (ini normal, bukan bug).

Kalau mau ubah jam, edit baris `cron:` di `.github/workflows/update.yml` (format cron pakai UTC, bukan WIB).
