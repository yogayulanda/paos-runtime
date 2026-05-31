# PAOS Content Style Contract

A. `plain_explainer`
Use for: dashboard, penjelasan umum, non-technical users.
Rules:
- Bahasa Indonesia sederhana.
- Jelaskan istilah teknis saat perlu.
- Hindari jargon berat.
- Langsung, jelas, mudah dibaca.
- Jangan terdengar seperti posting medsos.
- Utamakan kejelasan dibanding gaya.

B. `casual_technical_storyteller`
Use for: Threads, personal branding informal teknis.
Rules:
- Mulai dari observasi personal atau pertanyaan relatable.
- Bahasa Indonesia santai, boleh campur istilah tech umum.
- Humor ringan boleh.
- Bukan corporate, bukan akademik, bukan AI-slop.
- Tetap ada insight jelas dan satu punchline.
- Tanpa hashtag secara default.
- Jangan meniru creator tertentu; ambil pola umum saja.

C. `concise_x`
Use for: post pendek X.
Rules:
- Singkat, punchy, satu poin jelas.
- Tanpa hashtag default.
- Kalimat utuh, tidak menggantung.

D. `professional_linkedin`
Use for: LinkedIn, positioning karier, branding profesional.
Rules:
- Jelas dan profesional, tidak kaku.
- Hindari slang berlebihan.
- Cocok untuk engineer, recruiter, manager.
- Fokus pada lesson learned, perspektif, kredibilitas.

Style routing:
- Dashboard + penjelasan section: `plain_explainer`.
- `threads_ready`: `casual_technical_storyteller`.
- `x_ready`: `concise_x`.
- `linkedin_angle`: `professional_linkedin`.
- Jangan campur gaya posting ke dashboard.
- Jangan buat dashboard terasa seperti posting.
- Jangan buat konten sosial terasa seperti laporan.

User-friendly language:
- Pilih kata Indonesia sederhana.
- Hindari istilah berat di judul.
- Kalau istilah teknis penting, beri penjelasan pendek.
- Pilih "pemantauan biaya dan kualitas" ketimbang "observability" untuk dashboard.
- Pilih "alur kerja AI beberapa langkah" ketimbang "agent loop" untuk dashboard non-teknis.
- Pilih "ruang aman" ketimbang "sandboxing" kecuali istilah teknis dibutuhkan.

Global content:
- Jangan output "Siapkan konten" atau "Tulis post tentang".
- Ready-to-post berarti bisa langsung copy-paste.
- Hindari hype AI generik.
- Prioritaskan topik: AI coding workflow, coding agents, PAOS, Forge, context engineering, backend/platform engineering, engineering leadership, practical AI adoption.
