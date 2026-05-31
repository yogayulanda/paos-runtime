Gunakan konteks berikut untuk menghasilkan PAOS Daily Intelligence.

Personal Context:
{{ personal_context }}

Insight Contract:
{{ insight_contract }}

Content Style Contract:
{{ content_style_contract }}

Source Status:
{{ source_status }}

Digest:
{{ digest }}

Keluaran wajib berupa JSON valid saja, tanpa markdown, tanpa komentar di luar JSON.
Semua teks user-facing wajib berbahasa Indonesia natural.
Jika digest berbahasa Inggris, ubah menjadi ringkasan Bahasa Indonesia.

Gunakan schema berikut:
{
  "daily_summary": ["string"],
  "priority_actions": [{"title":"string","why_it_matters":"string","next_step":"string","source_refs":["string"]}],
  "important_signals": [{"title":"string","meaning":"string","why_watch":"string","source_refs":["string"]}],
  "opportunities": [{"type":"string","title":"string","why_relevant":"string","suggested_action":"string","source_refs":["string"]}],
  "content_branding": [{"angle":"string","why_post":"string","threads_ready":"string","x_ready":"string","linkedin_angle":"string","source_refs":["string"]}],
  "learning_queue": [{"topic":"string","why_learn":"string","relevance":"string","start_from":"string","source_refs":["string"]}],
  "experiment_queue": [{"experiment":"string","purpose":"string","smallest_test":"string","expected_signal":"string","source_refs":["string"]}],
  "github_tools": {"status":"string","items":[]},
  "linkedin_network": {"status":"string","items":[]},
  "career_jobs": {"status":"string","items":[]},
  "personal_context_updates": [{"suggestion":"string","why":"string","action":"string"}],
  "watchlist": [{"item":"string","status":"string","watch_reason":"string","source_refs":["string"]}],
  "source_coverage": {"active_sources":[],"inactive_sources":[],"missing_sources":[],"notes":"string"}
}

Aturan penting:
- JSON valid only.
- Pakai array kosong `[]` hanya jika benar-benar tidak ada item kuat.
- Jika ada >=3 sinyal valid di digest, isi minimal:
  - `priority_actions` >=2 item
  - `important_signals` >=2 item
  - `opportunities` >=1 item
  - `learning_queue` atau `experiment_queue` >=1 item
  - `content_branding` >=1 item jika ada angle opini kuat
- Gunakan status jelas untuk source inactive/no relevant signal.
- Jangan invent data GitHub/LinkedIn/jobs jika source inactive/absent.
- Jangan halusinasi URL sumber.
- `source_refs` hanya boleh dari digest/source input.
- Empty state untuk section utama hanya jika sinyal memang tidak cukup relevan.
- Hindari kalimat menggantung.
- Preview harus utuh dan jelas. Jangan potong judul/frasa/kalimat.
- Jika ragu, tampilkan kalimat utuh atau pindahkan detail ke section detail.
- `daily_summary` target: 3-5 line pendek, mudah dipahami, tidak padat seperti headline.
- `daily_summary` wajib memuat: apa yang terjadi, kenapa penting, artinya untuk PAOS/kamu, dan takeaway praktis.
- Untuk kategori `ai`, hubungkan summary ke workflow coding AI, tooling agent/runtime, evaluasi model, dan pemakaian engineering nyata.
- `priority_actions.title` harus spesifik dan actionable.
- `important_signals.meaning` harus menjelaskan tren, bukan hanya mengulang judul.
- `opportunities.why_relevant` harus jelas kenapa penting untuk kondisi kerja saat ini.
