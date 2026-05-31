# PAOS Dashboard Contract

Dashboard name: **PAOS Daily Intelligence**

Main dashboard is a preview/briefing layer. It must be concise and easy to read. Full detail belongs in section detail view. Long/detail content must go behind detail buttons.

Preview/detail rules:
- If a section item is too long, show only its complete title in main dashboard.
- Do not show half explanations.
- Do not cut title, sentence, or phrase.
- If preview text becomes unclear after shortening, omit the preview and move explanation to detail.
- Prioritize readability over completeness in main dashboard.
- Detail view may be longer and must contain complete explanations.
- Detail view must not cut content mid-sentence.
- Explain technical terms simply when needed.
- Do not show raw digest markdown.
- Do not show internal paths.
- Do not show `Generated At`, `Category`, or `Date` metadata.
- Do not force insights when source is weak.

## Section Definitions

### 1) Ringkasan Hari Ini
- section_id: `daily_summary`
- user_facing_label: `Ringkasan Hari Ini`
- purpose: Briefing singkat tentang hari ini.
- what belongs here: 2-4 kalimat kenapa hari ini penting untuk kamu.
- what does not belong here: metadata internal, daftar panjang, jargon tanpa konteks.
- main_preview_format: 2-4 kalimat pendek.
- detail_view_format: versi penjelasan penuh.
- button_label: `Kenapa ini penting`
- max_preview_items: 1
- empty_state: `Belum ada ringkasan kuat hari ini.`

### 2) Yang Perlu Kamu Lakukan
- section_id: `priority_actions`
- user_facing_label: `Yang Perlu Kamu Lakukan`
- purpose: Aksi konkret yang sebaiknya kamu kerjakan.
- what belongs here: action title + alasan + next step.
- what does not belong here: opini umum tanpa aksi.
- main_preview_format: daftar nomor judul aksi lengkap.
- detail_view_format: title + why_it_matters + next_step + source refs.
- button_label: `Apa yang perlu dilakukan`
- max_preview_items: 3
- empty_state: `Tidak ada prioritas baru yang cukup kuat hari ini.`

### 3) Yang Lagi Penting
- section_id: `important_signals`
- user_facing_label: `Yang Lagi Penting`
- purpose: Sinyal/tren penting saat ini.
- what belongs here: sinyal tren + makna + alasan dipantau.
- what does not belong here: instruksi aksi langsung.
- main_preview_format: daftar nomor judul sinyal lengkap.
- detail_view_format: title + meaning + why_watch + source refs.
- button_label: `Kenapa ini penting`
- max_preview_items: 3
- empty_state: `Belum ada sinyal penting baru yang cukup kuat hari ini.`

### 4) Peluang untuk Kamu
- section_id: `opportunities`
- user_facing_label: `Peluang untuk Kamu`
- purpose: Peluang yang relevan untuk dimanfaatkan.
- what belongs here: project/content/career/networking/learning/business opportunities.
- what does not belong here: peluang dipaksakan tanpa sinyal kuat.
- main_preview_format: ringkasan pendek per tipe peluang.
- detail_view_format: type + title + why_relevant + suggested_action + source refs.
- button_label: `Peluang`
- max_preview_items: 4
- empty_state: `Belum ada peluang yang cukup kuat hari ini.`
- note_semantics:
  - `Peluang untuk Kamu` = peluang tindakan berikutnya yang actionable.
  - Jika `Bahan Konten & Branding` ada, line `Konten` di preview gunakan framing ringan (mis. `Ada bahan ringan untuk post pendek ...`), bukan empty state.
  - `Belum ada peluang konten kuat hari ini.` hanya dipakai jika benar-benar tidak ada bahan konten.

### 5) Bahan Konten & Branding
- section_id: `content_branding`
- user_facing_label: `Bahan Konten & Branding`
- purpose: Materi siap-post dan angle branding.
- what belongs here: angle, why_post, threads_ready, x_ready, linkedin_angle.
- what does not belong here: instruksi seperti “Siapkan konten”.
- main_preview_format: angle terbaik atau empty state.
- detail_view_format: format lengkap copy-paste ready.
- button_label: `Bahan post`
- max_preview_items: 1
- empty_state: `Belum ada bahan post yang cukup kuat hari ini.`

### 6) Yang Layak Dipelajari
- section_id: `learning_queue`
- user_facing_label: `Yang Layak Dipelajari`
- purpose: Topik belajar yang punya dampak nyata.
- what belongs here: topic + why_learn + relevance + start_from.
- what does not belong here: topik umum tanpa arah mulai.
- main_preview_format: daftar topik lengkap.
- detail_view_format: struktur lengkap per item.
- button_label: `Yang perlu dipelajari`
- max_preview_items: 3
- empty_state: `Belum ada topik belajar prioritas hari ini.`

### 7) Yang Layak Dicoba
- section_id: `experiment_queue`
- user_facing_label: `Yang Layak Dicoba`
- purpose: Eksperimen teknis kecil.
- what belongs here: experiment + purpose + smallest_test + expected_signal.
- what does not belong here: proyek besar tanpa uji kecil.
- main_preview_format: daftar eksperimen.
- detail_view_format: struktur lengkap per item.
- button_label: `Yang bisa dicoba`
- max_preview_items: 3
- empty_state: `Belum ada eksperimen kecil yang cukup kuat hari ini.`

### 8) Radar GitHub & Tools
- section_id: `github_tools`
- user_facing_label: `Radar GitHub & Tools`
- purpose: Sinyal repo/tool/library/framework.
- what belongs here: status sumber GitHub + item relevan.
- what does not belong here: data non-GitHub tanpa konteks tools.
- main_preview_format: status + 1-3 item judul.
- detail_view_format: status + rincian item.
- button_label: `GitHub & Tools`
- max_preview_items: 3
- empty_state: `Belum ada sinyal GitHub karena source GitHub belum aktif.`

### 9) Radar LinkedIn & Networking
- section_id: `linkedin_network`
- user_facing_label: `Radar LinkedIn & Networking`
- purpose: Sinyal networking profesional.
- what belongs here: status LinkedIn + peluang networking relevan.
- what does not belong here: konten non-networking acak.
- main_preview_format: status + item singkat.
- detail_view_format: status + detail peluang.
- button_label: `LinkedIn`
- max_preview_items: 3
- empty_state: `Belum ada sinyal LinkedIn karena source LinkedIn belum aktif.`

### 10) Radar Karier & Lowongan
- section_id: `career_jobs`
- user_facing_label: `Radar Karier & Lowongan`
- purpose: Peluang kerja dan langkah lanjut.
- what belongs here: status jobs + peluang dan gap.
- what does not belong here: sinyal pasar umum.
- main_preview_format: status + item singkat.
- detail_view_format: status + detail fit/gap/action.
- button_label: `Lowongan`
- max_preview_items: 3
- empty_state: `Belum ada sinyal lowongan karena source job belum aktif.`

### 11) Update Konteks Pribadi
- section_id: `personal_context_updates`
- user_facing_label: `Update Konteks Pribadi`
- purpose: Saran update konteks jangka panjang.
- what belongs here: suggestion + why + action (suggest only).
- what does not belong here: auto-save/otomasi langsung.
- main_preview_format: daftar saran pendek.
- detail_view_format: alasan lengkap dan tindakan lanjut.
- button_label: `Update konteks`
- max_preview_items: 3
- empty_state: `Belum ada update konteks pribadi yang cukup kuat hari ini.`

### 12) Pantauan
- section_id: `watchlist`
- user_facing_label: `Pantauan`
- purpose: Sinyal menarik tapi belum actionable.
- what belongs here: weak-but-interesting watch items.
- what does not belong here: prioritas aksi utama.
- main_preview_format: daftar item pantauan.
- detail_view_format: item + status + watch_reason + source refs.
- button_label: `Pantauan`
- max_preview_items: 5
- empty_state: `Belum ada item pantauan baru yang relevan hari ini.`

## Empty State Rules
Gunakan empty state jelas untuk:
- source not active
- source active but no new data
- source active but no relevant data
- no strong insight
- no strong content opportunity

Contoh:
- `Belum ada sinyal GitHub karena source GitHub belum aktif.`
- `Source GitHub aktif, tapi belum ada repo/tool yang cukup relevan hari ini.`
- `Belum ada bahan post yang cukup kuat hari ini.`
- `Tidak ada prioritas baru yang cukup kuat hari ini.`

## Main Dashboard Target Layout

🧠 PAOS Daily Intelligence

📝 Ringkasan Hari Ini
<2–4 short sentences>

✅ Yang Perlu Kamu Lakukan
1. <complete action title>
2. <complete action title>
3. <complete action title>

🔥 Yang Lagi Penting
1. <complete signal title>
2. <complete signal title>
3. <complete signal title>

🎯 Peluang untuk Kamu
- Project: <short / empty state>
- Konten: <short / empty state>
- Karier: <short / empty state>

✍️ Bahan Konten
<best content angle / empty state>

📡 Status Source
- Threads Account: aktif/belum aktif
- Threads Keyword: aktif/belum aktif
- RSS Feed: aktif/belum aktif
- GitHub: aktif/belum aktif
- LinkedIn: aktif/belum aktif
- Lowongan: aktif/belum aktif

Pilih detail di bawah.

Recommended button labels:
- Apa yang perlu dilakukan
- Kenapa ini penting
- Peluang
- Bahan post
- Yang perlu dipelajari
- Yang bisa dicoba
- GitHub & Tools
- LinkedIn
- Lowongan
- Update konteks
- Pantauan
