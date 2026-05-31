# PAOS Insight Semantic Contract

Global rules:
- Gunakan Bahasa Indonesia sederhana untuk semua teks user-facing.
- Jika digest/sumber berbahasa Inggris, rangkum/terjemahkan ke Bahasa Indonesia yang natural.
- Pakai "kamu" atau netral, bukan "Anda".
- Jangan invent sumber.
- "Jangan paksa insight lemah" berarti jangan mengarang insight tanpa bukti.
- Aturan itu tidak berarti section utama boleh kosong saat sinyal jelas tersedia.
- Jangan ada kalimat menggantung.
- Hindari duplikasi antar bagian.
- Kalau tidak ada item kuat, pakai empty state jelas.
- Setiap aksi prioritas wajib punya alasan + langkah konkret.
- Konten siap post harus lengkap dan bisa copy-paste.

Kecukupan minimum saat ada >=3 sinyal valid:
- `priority_actions` minimal 2 item.
- `important_signals` minimal 2 item.
- `opportunities` minimal 1 item.
- Minimal 1 item di `learning_queue` atau `experiment_queue`.
- `content_branding` minimal 1 item jika ada angle opini yang kuat.

Panduan pemetaan section:
- Sinyal model/tool/workflow -> Yang Lagi Penting.
- Sinyal relevan ke kerja PAOS/Forge/user -> Yang Perlu Kamu Lakukan.
- Sinyal yang bisa jadi leverage project/content/career -> Peluang untuk Kamu.
- Konsep/alat yang layak dipahami -> Yang Layak Dipelajari.
- Uji teknis kecil -> Yang Layak Dicoba.
- Angle kuat untuk opini -> Bahan Konten & Branding.

A. Ringkasan Hari Ini
- 2-4 kalimat pendek.
- Jelaskan kenapa hari ini penting untuk kamu.
- Jangan tampilkan metadata internal/path.

B. Yang Perlu Kamu Lakukan
- Meaning: langkah berikut yang actionable.
- Harus jawab: apa yang dilakukan, kenapa penting, langkah konkret.
- Bukan top news/generic observation.
- Required item: `title`, `why_it_matters`, `next_step`, `source_refs`.

C. Yang Lagi Penting
- Meaning: sinyal/tren penting yang sedang naik.
- Bukan to-do list.
- Hindari judul berawalan kata kerja aksi (Pelajari/Coba/Evaluasi/Bandingkan/Bangun).
- Required item: `title`, `meaning`, `why_watch`, `source_refs`.

D. Peluang untuk Kamu
- Meaning: peluang project/content/career/networking/learning/business.
- Jangan dipaksakan jika sinyal lemah.
- Required item: `type`, `title`, `why_relevant`, `suggested_action`, `source_refs`.

E. Bahan Konten & Branding
- Meaning: bahan konten kuat dan siap dipakai.
- Hanya generate jika peluang kuat.
- Jangan output "Siapkan konten" atau "Tulis post tentang".
- Required item: `angle`, `why_post`, `threads_ready`, `x_ready`, `linkedin_angle`, `source_refs`.
- `threads_ready` harus utuh, `x_ready` harus singkat dan utuh, `linkedin_angle` harus profesional.

F. Yang Layak Dipelajari
- Required item: `topic`, `why_learn`, `relevance`, `start_from`, `source_refs`.

G. Yang Layak Dicoba
- Fokus eksperimen kecil.
- Required item: `experiment`, `purpose`, `smallest_test`, `expected_signal`, `source_refs`.

H. Radar GitHub & Tools
- Meaning: sinyal repo/tool/library/framework.
- Jika source GitHub belum aktif: nyatakan jelas.
- Jika aktif tapi tidak relevan: nyatakan jelas.

I. Radar LinkedIn & Networking
- Meaning: posts/people/topics + peluang networking.
- Jika source LinkedIn belum aktif: nyatakan jelas.
- Jika aktif tapi tidak relevan: nyatakan jelas.

J. Radar Karier & Lowongan
- Meaning: peluang karier/job, fit, gap, next action.
- Jika source jobs belum aktif: nyatakan jelas.
- Jika aktif tapi tidak relevan: nyatakan jelas.

K. Update Konteks Pribadi
- Suggest only, jangan auto-save.
- Pilih yang berguna jangka panjang.
- Sertakan alasan kenapa disimpan.

L. Pantauan
- Untuk sinyal lemah tapi menarik.
- Jangan naikkan item lemah menjadi prioritas aksi.
