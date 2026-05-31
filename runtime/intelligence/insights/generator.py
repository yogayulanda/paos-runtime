import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
import yaml


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from digest.loader import load_signals
from digest.loader import resolve_date
from digest.loader import signal_path
from insights.models import INSIGHT_VERSION
from insights.models import InsightBuildResult
from insights.models import SUPPORTED_INSIGHT_TYPES
from insights.models import SUPPORTED_LANGUAGES
from insights.models import SUPPORTED_PRIORITIES
from insights.renderer import render_insights
from signals.ai_generator import ai_available
from signals.ai_generator import env_config
from signals.ai_generator import parse_response_content
from signals.ai_generator import resolve_endpoint


ROOT = INTELLIGENCE_DIR.parents[1]
CONFIG_PATH = ROOT / "runtime" / "intelligence" / "config.yaml"
INSIGHTS_DIR = ROOT / "intelligence" / "insights"
DIGESTS_DIR = ROOT / "intelligence" / "digests"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_AI_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_AI_READ_TIMEOUT_SECONDS = 180
CONTRACTS_DIR = INTELLIGENCE_DIR / "contracts"
PROMPTS_DIR = INTELLIGENCE_DIR / "prompts"


COPY = {
    "en": {
        "header": "Daily Insights",
        "reason": "Why this deserves attention today",
        "fallback_reason": "This insight is derived from a strong signal cluster and should be reviewed today.",
    },
    "id": {
        "header": "Insight Harian",
        "reason": "Alasan insight ini perlu diperhatikan hari ini",
        "fallback_reason": "Insight ini berasal dari klaster sinyal yang kuat dan layak ditinjau hari ini.",
    },
}


class InsightFreshnessError(RuntimeError):
    pass


def _timeout_from_env(name, default_value):
    raw = compact_text(os.environ.get(name))
    if not raw:
        return default_value
    try:
        value = float(raw)
    except Exception:
        return default_value
    if value <= 0:
        return default_value
    return value


def resolve_ai_timeout():
    connect_timeout = _timeout_from_env(
        "PAOS_INSIGHT_AI_CONNECT_TIMEOUT_SECONDS",
        DEFAULT_AI_CONNECT_TIMEOUT_SECONDS,
    )
    read_timeout = _timeout_from_env(
        "PAOS_INSIGHT_AI_READ_TIMEOUT_SECONDS",
        DEFAULT_AI_READ_TIMEOUT_SECONDS,
    )
    return (connect_timeout, read_timeout)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build PAOS daily insights from intelligence signals."
    )
    parser.add_argument("--category", required=True)
    parser.add_argument("--date", default="today")
    parser.add_argument(
        "--mode",
        choices=["auto", "ai", "heuristic"],
        default="auto",
    )
    return parser.parse_args()


def compact_text(value):
    return " ".join(str(value or "").split())


ACTION_PREFIXES_ID = (
    "pelajari",
    "coba",
    "bangun",
    "evaluasi",
    "bandingkan",
    "uji",
    "baca",
    "catat",
    "siapkan",
    "tulis",
)


DANGLING_ENDINGS_ID = (
    "pada tiga hal",
    "seperti",
    "yaitu",
    "antara lain",
    "dengan",
    "untuk",
)


def has_action_hint(text, language):
    blob = compact_text(text).lower()
    if language == "id":
        hints = (
            "aksi:",
            "uji",
            "tes",
            "bandingkan",
            "pelajari",
            "coba",
            "bangun",
            "buat",
            "tulis",
            "posting",
            "follow up",
            "lanjutkan",
        )
    else:
        hints = (
            "action:",
            "test",
            "compare",
            "learn",
            "build",
            "post",
            "follow up",
            "evaluate",
        )
    return any(hint in blob for hint in hints)


def normalize_tone_id(text):
    value = compact_text(text)
    return (
        value.replace("Anda ", "kamu ")
        .replace("anda ", "kamu ")
        .replace("Anda,", "kamu,")
        .replace("Anda.", "kamu.")
        .replace("Anda", "kamu")
    )


def fix_dangling_ending(text, language):
    value = compact_text(text)
    if not value:
        return value

    lowered = value.lower().rstrip(" .,:;")
    if language == "id":
        for ending in DANGLING_ENDINGS_ID:
            if lowered.endswith(ending):
                if ending == "pada tiga hal":
                    return f"{value}: kualitas hasil, kejujuran saat ragu, dan biaya loop panjang."
                if ending == "seperti":
                    return f"{value} evaluasi kualitas output, stabilitas, dan biaya."
                if ending == "yaitu":
                    return f"{value} evaluasi kualitas output, stabilitas, dan biaya."
                if ending == "antara lain":
                    return f"{value} kualitas output, stabilitas, dan biaya."
                if ending == "dengan":
                    return f"{value} pendekatan yang bisa diuji hari ini."
                if ending == "untuk":
                    return f"{value} eksperimen yang relevan hari ini."
    return value


def ensure_complete_sentence(text, language):
    value = compact_text(text)
    if not value:
        return value
    value = fix_dangling_ending(value, language)
    if value[-1] not in ".!?":
        value = f"{value}."
    return value


def normalize_title_semantics(title, insight_type, reason, language):
    value = compact_text(title)
    if language == "id":
        value = normalize_tone_id(value)
    if not value:
        return value

    lowered = value.lower()
    action_start = any(lowered.startswith(f"{prefix} ") for prefix in ACTION_PREFIXES_ID)
    if insight_type in {"project", "career", "market"} and action_start:
        reason_first = compact_text(str(reason or "").split(".")[0])
        if reason_first:
            reason_first = normalize_tone_id(reason_first) if language == "id" else reason_first
            if any(reason_first.lower().startswith(f"{prefix} ") for prefix in ACTION_PREFIXES_ID):
                return "Sinyal saat ini bergeser ke workflow agent yang lebih siap produksi"
            return ensure_complete_sentence(reason_first, language).rstrip(".")
        return "Sinyal saat ini bergeser ke workflow agent yang lebih siap produksi"
    return fix_dangling_ending(value, language)


def default_action_line(title, insight_type, language):
    title_text = compact_text(title)
    if language == "id":
        mapping = {
            "learning": f"Langkah hari ini: pilih satu bacaan utama tentang '{title_text}', lalu tulis 3 poin yang langsung bisa dipakai di workflow PAOS/Forge.",
            "tool": f"Langkah hari ini: uji '{title_text}' di satu task nyata PAOS/Forge dan catat trade-off kualitas, biaya, dan stabilitas.",
            "project": f"Langkah hari ini: turunkan '{title_text}' jadi satu eksperimen kecil yang bisa dijalankan hari ini di PAOS/Forge.",
            "content": f"Langkah hari ini: ubah '{title_text}' jadi draft posting singkat (Threads/X) dengan satu opini yang jelas dan satu contoh nyata.",
            "career": f"Langkah hari ini: catat dampak '{title_text}' ke skill prioritas minggu ini dan tentukan satu langkah follow-up yang konkret.",
            "market": f"Langkah hari ini: pantau '{title_text}' selama 3-7 hari lalu putuskan dampaknya ke pilihan model/workflow yang dipakai.",
        }
    else:
        mapping = {
            "learning": f"Action: pick one core reading on '{title_text}' and extract 3 ideas you can apply in your workflow today.",
            "tool": f"Action: test '{title_text}' on one real PAOS/Forge task and record quality, cost, and stability trade-offs.",
            "project": f"Action: turn '{title_text}' into one small experiment you can run today in PAOS/Forge.",
            "content": f"Action: convert '{title_text}' into a short Threads/X draft with one clear opinion and one concrete example.",
            "career": f"Action: map '{title_text}' to this week's priority skills and define one concrete follow-up step.",
            "market": f"Action: monitor '{title_text}' for 3-7 days and decide whether it changes your model/workflow choices.",
        }
    return mapping.get(insight_type, mapping.get("project"))


def normalize_reason(reason, title, insight_type, language):
    value = compact_text(reason)
    if language == "id":
        value = normalize_tone_id(value)
    if not value:
        return value
    value = ensure_complete_sentence(value, language)
    if has_action_hint(value, language):
        return value
    with_action = f"{value} {default_action_line(title, insight_type, language)}".strip()
    return ensure_complete_sentence(with_action, language)


def ensure_important_coverage(insights, language):
    if not insights:
        return insights

    important = [item for item in insights if item.get("insight_type") in {"project", "career"}]
    needed = 2 - len(important)
    if needed <= 0:
        return insights

    for item in insights:
        if needed <= 0:
            break
        if item.get("insight_type") in {"project", "career"}:
            continue
        forced_type = "project" if needed == 2 else "career"
        item["insight_type"] = forced_type
        item["reason"] = normalize_reason(
            reason=item.get("reason"),
            title=item.get("title"),
            insight_type=forced_type,
            language=language,
        )
        needed -= 1

    return insights


def digest_path(date, category):
    return DIGESTS_DIR / resolve_date(date) / f"{category}.md"


def output_jsonl_path(date, category):
    return INSIGHTS_DIR / date / f"{category}.jsonl"


def output_markdown_path(date, category):
    return INSIGHTS_DIR / date / f"{category}.md"


def load_runtime_config():
    if not CONFIG_PATH.exists():
        return {}
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def resolve_language(config=None):
    config = config or load_runtime_config()
    language = compact_text(((config.get("insights") or {}).get("language"))).lower()
    if language in SUPPORTED_LANGUAGES:
        return language
    return "id"


def validate_digest_freshness(date, category):
    signal_file = signal_path(date=date, category=category)
    rendered_digest = digest_path(date=date, category=category)

    if not signal_file.exists():
        raise InsightFreshnessError(
            "Signal output is missing. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )

    if not rendered_digest.exists():
        raise InsightFreshnessError(
            "Digest output is missing. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_digest.py --category {category}"
        )

    if rendered_digest.stat().st_mtime < signal_file.stat().st_mtime:
        raise InsightFreshnessError(
            "Digest output is stale relative to signals. "
            f"digest={rendered_digest} signal={signal_file}. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_digest.py --category {category}"
        )

    return signal_file, rendered_digest


def write_jsonl(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")


def write_markdown(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_text_template(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def detect_source_status(signals):
    threads_account_active = False
    threads_keyword_active = False
    rss_feed_active = False
    github_active = False
    linkedin_active = False
    jobs_active = False
    for signal in signals or []:
        for source in (signal.get("sources") or []):
            platform = compact_text(source.get("platform")).lower()
            source_type = compact_text(source.get("source_type")).lower()
            source_name = compact_text(source.get("source_name")).lower()
            url = compact_text(source.get("url")).lower()
            if platform == "threads" and source_type == "account":
                threads_account_active = True
            if platform == "threads" and source_type == "keyword":
                threads_keyword_active = True
            if platform == "rss" and source_type == "feed":
                rss_feed_active = True
            if any(token in f"{platform} {source_type} {source_name} {url}" for token in ("github", "gitlab", "bitbucket")):
                github_active = True
            if any(token in f"{platform} {source_type} {source_name} {url}" for token in ("linkedin", "networking")):
                linkedin_active = True
            if any(token in f"{platform} {source_type} {source_name} {url}" for token in ("job", "lowongan", "careers", "greenhouse", "lever")):
                jobs_active = True
    inferred = {
        "threads_account": "active" if threads_account_active else "inactive",
        "threads_keyword": "active" if threads_keyword_active else "inactive",
        "rss_feed": "active" if rss_feed_active else "inactive",
        "github": "active" if github_active else "inactive",
        "linkedin": "active" if linkedin_active else "inactive",
        "jobs": "active" if jobs_active else "inactive",
    }
    return _merge_runtime_source_status(inferred)


def _read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _enabled_sources_for_category(category="ai"):
    try:
        payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    categories = ((payload.get("intelligence") or {}).get("categories") or {})
    details = (categories.get(category) or {})
    enabled_sources = details.get("enabled_sources") or []
    if not isinstance(enabled_sources, list):
        return set()
    return {compact_text(value).lower() for value in enabled_sources if compact_text(value)}


def _runtime_job_is_active(job_name):
    status = _read_json(ROOT / ".runtime" / "runs" / job_name / "latest.json") or {}
    value = compact_text(status.get("status")).lower()
    return value in {"success", "success_with_warnings"}


def _merge_runtime_source_status(source_status, category="ai"):
    merged = dict(source_status or {})
    enabled_sources = _enabled_sources_for_category(category=category)

    if "threads" in enabled_sources and _runtime_job_is_active("threads-account"):
        merged["threads_account"] = "active"
    if "keyword" in enabled_sources and _runtime_job_is_active("threads-keyword"):
        merged["threads_keyword"] = "active"
    if "rss" in enabled_sources and _runtime_job_is_active("rss-collector"):
        merged["rss_feed"] = "active"

    return merged


def build_source_coverage(source_status):
    active = []
    inactive = []
    missing = []
    mapping = {
        "threads_account": "Threads Account",
        "threads_keyword": "Threads Keyword",
        "rss_feed": "RSS Feed",
        "github": "GitHub",
        "linkedin": "LinkedIn",
        "jobs": "Lowongan",
    }
    for key, label in mapping.items():
        status = compact_text((source_status or {}).get(key)).lower()
        if status == "active":
            active.append(label)
        elif status == "inactive":
            inactive.append(label)
        else:
            missing.append(label)
    notes = "Status source dipisah per family agar mode pengumpulan lebih jelas."
    if not active:
        notes = "Belum ada source aktif yang terdeteksi."
    return {
        "active_sources": active,
        "inactive_sources": inactive,
        "missing_sources": missing,
        "notes": notes,
    }


def looks_actionable(signal):
    blob = " ".join(
        [
            compact_text(signal.get("title")).lower(),
            compact_text(signal.get("summary")).lower(),
            compact_text(signal.get("why_it_matters")).lower(),
            compact_text(signal.get("theme")).lower(),
        ]
    )
    tokens = ("tool", "workflow", "agent", "evalu", "benchmark", "reliab", "prompt", "model", "code", "platform")
    return any(token in blob for token in tokens)


def looks_english(text):
    lowered = compact_text(text).lower()
    if not lowered:
        return False
    markers = (
        " the ",
        " and ",
        " with ",
        " for ",
        " this ",
        " that ",
        " is ",
        " are ",
        " can ",
        " should ",
        "today",
    )
    padded = f" {lowered} "
    return sum(1 for marker in markers if marker in padded) >= 2


def signal_blob(signal):
    return " ".join(
        [
            compact_text(signal.get("title")).lower(),
            compact_text(signal.get("summary")).lower(),
            compact_text(signal.get("why_it_matters")).lower(),
            compact_text(signal.get("theme")).lower(),
        ]
    )


def signal_theme(signal):
    blob = signal_blob(signal)
    if "claude opus 4.8" in blob or ("uncertainty" in blob and "autonomous work" in blob):
        return "claude_reliability"
    if any(token in blob for token in ("usage visibility", "sandboxing", "harness", "/usage", "skills, agents, mcps", "agent tooling")):
        return "agent_observability"
    if any(token in blob for token in ("gpt-5.5", "codex", "braintrust", "endava", "enterprise engineering")):
        return "codex_enterprise"
    if any(token in blob for token in ("open-model", "open model", "open-source", "china", "ecosystem", "distillation")):
        return "open_model_ecosystem"
    if any(token in blob for token in ("governance", "third-party evaluations", "healthcare", "biodefense", "regulated-sector")):
        return "ai_governance"
    if any(token in blob for token in ("runtime", "pyodide", "datasette", "browser", "tool extension", "prototyping")):
        return "runtime_experimentation"
    if any(token in blob for token in ("burnout", "offline", "culture", "team health", "sustainable adoption")):
        return "ai_work_culture"
    if any(token in blob for token in ("revenue", "demand signal", "budget lines", "developer ux")):
        return "market_demand"
    return "general_ai_workflow"


def simplified_signal(signal):
    theme = signal_theme(signal)
    mapping = {
        "claude_reliability": {
            "summary": "Hari ini kelihatan jelas bahwa model makin dinilai bukan cuma dari kecerdasan, tapi dari kejujuran saat ragu dan kemampuan bertahan di task panjang.",
            "priority_title": "Uji Claude di task coding yang panjang dan mudah salah",
            "important_title": "Claude mulai menonjol di kejujuran saat ragu dan kerja panjang",
            "why": "Kalau model lebih jujur saat tidak yakin, workflow coding panjang jadi lebih aman dipakai di task yang butuh banyak langkah.",
            "next_step": "Pilih satu task PAOS yang panjang, lalu bandingkan apakah Claude lebih stabil saat diminta menjelaskan keraguan dan progresnya.",
            "opportunity_type": "project",
            "opportunity_title": "PAOS bisa punya checklist evaluasi untuk task coding panjang",
            "opportunity_action": "Tambahkan checklist sederhana untuk melihat kualitas hasil, kejujuran saat ragu, dan kestabilan di task multi-langkah.",
            "learning_topic": "Evaluasi kejujuran model saat ragu",
            "experiment_name": "Bandingkan Claude di task coding panjang",
            "content_angle": "Model yang bagus bukan cuma yang pintar, tapi yang tahu kapan harus ragu",
        },
        "agent_observability": {
            "summary": "Tooling agent mulai bergerak ke hal yang lebih operasional: pemantauan biaya, ruang aman, dan eksperimen harness yang rapi.",
            "priority_title": "Catat metrik biaya dan kualitas untuk setiap langkah pipeline PAOS",
            "important_title": "Pemantauan biaya dan ruang aman mulai jadi bagian penting dari agent production",
            "why": "Workflow agent akan sulit di-scale kalau biaya, batas eksekusi, dan kualitas per langkah masih gelap.",
            "next_step": "Tambahkan pencatatan biaya, waktu, dan hasil per langkah di satu pipeline PAOS yang paling sering dipakai.",
            "opportunity_type": "project",
            "opportunity_title": "PAOS bisa dirapikan dengan observability per langkah",
            "opportunity_action": "Mulai dari satu pipeline utama, lalu tampilkan biaya, durasi, dan kualitas setiap langkah dalam log yang mudah dibaca.",
            "learning_topic": "Pemantauan biaya dan kualitas per langkah",
            "experiment_name": "Tambah logging biaya per langkah agent",
            "content_angle": "Biaya AI sering bocor bukan di model, tapi di workflow yang tidak kelihatan",
        },
        "codex_enterprise": {
            "summary": "OpenAI makin mendorong model coding ke alur kerja software tim, bukan cuma ke penggunaan personal seperti copilot.",
            "priority_title": "Uji Claude dan Codex di satu task PAOS yang sama",
            "important_title": "AI coding mulai bergeser dari copilot individu ke workflow kerja tim",
            "why": "Kalau model mulai dikemas untuk delivery tim, keputusan model tidak cukup dilihat dari demo atau benchmark cepat saja.",
            "next_step": "Pilih satu task coding berulang di PAOS, lalu bandingkan kualitas hasil, biaya, dan kebutuhan revisi antara Claude dan Codex.",
            "opportunity_type": "content",
            "opportunity_title": "Ada angle kuat untuk membandingkan Claude dan Codex di workflow coding berulang",
            "opportunity_action": "Tulis hasil perbandingan yang fokus ke stabilitas, biaya, dan beban review, bukan sekadar siapa yang lebih pintar.",
            "learning_topic": "Cara menilai model coding untuk workflow tim",
            "experiment_name": "Adu Claude vs Codex di task pipeline yang sama",
            "content_angle": "Perbandingan model coding paling berguna kalau diuji di workflow nyata, bukan di benchmark pendek",
        },
        "open_model_ecosystem": {
            "summary": "Persaingan model makin ditentukan oleh ekosistem terbuka, bukan cuma siapa yang menang benchmark pekanan.",
            "priority_title": "Pantau dampak ekosistem open model ke pilihan tool jangka menengah",
            "important_title": "Ekosistem open model mulai jadi faktor strategis, bukan sekadar alternatif murah",
            "why": "Pilihan model ke depan akan dipengaruhi ketersediaan tooling, komunitas, dan kecepatan ekosistem bergerak.",
            "next_step": "Catat tool atau workflow yang mulai lebih mudah dibangun di atas model terbuka, lalu bandingkan dengan stack tertutup yang sekarang dipakai.",
            "opportunity_type": "career",
            "opportunity_title": "Literasi open model bisa jadi pembeda positioning teknis kamu",
            "opportunity_action": "Ambil satu topik open model yang relevan, lalu jadikan bahan catatan atau opini teknis yang menunjukkan sudut pandangmu.",
            "learning_topic": "Dinamika ekosistem open model",
            "experiment_name": "Petakan trade-off model terbuka vs tertutup",
            "content_angle": "Yang susah dikejar dari open model bukan satu modelnya, tapi kecepatan ekosistemnya",
        },
        "ai_governance": {
            "summary": "AI di area sensitif makin menuntut evaluasi, batas akses, dan governance yang rapi sebelum dipakai luas.",
            "priority_title": "Buat checklist evaluasi model untuk workflow yang berisiko tinggi",
            "important_title": "Governance dan evaluasi mulai jadi syarat masuk AI ke area sensitif",
            "why": "Semakin besar dampak workflow AI, semakin penting pembatasan akses dan cara evaluasi yang bisa diaudit.",
            "next_step": "Susun checklist kecil untuk validasi hasil, batas akses, dan review manual sebelum model dipakai di alur yang lebih sensitif.",
            "opportunity_type": "project",
            "opportunity_title": "PAOS bisa lebih siap produksi dengan guardrail evaluasi yang jelas",
            "opportunity_action": "Definisikan kapan output perlu dicek ulang, kapan akses harus dibatasi, dan metrik apa yang harus dipantau.",
            "learning_topic": "Evaluasi pihak ketiga dan guardrail AI",
            "experiment_name": "Tambah guardrail evaluasi untuk satu workflow",
            "content_angle": "AI production tidak berhenti di model choice; yang menentukan sering justru guardrail dan evaluasinya",
        },
        "runtime_experimentation": {
            "summary": "AI makin berguna bukan hanya untuk boilerplate, tapi untuk eksplorasi runtime, arsitektur, dan tooling yang belum jelas jalannya.",
            "priority_title": "Gunakan AI untuk memecah eksperimen teknis yang belum punya jalur jelas",
            "important_title": "AI mulai dipakai sebagai partner eksplorasi runtime dan tooling",
            "why": "Nilai model terasa lebih besar saat dipakai untuk mencari jalur eksperimen, bukan hanya menulis kode rutin.",
            "next_step": "Ambil satu eksperimen teknis yang menggantung di PAOS atau Forge, lalu pakai AI untuk memetakan opsi, risiko, dan langkah uji terkecilnya.",
            "opportunity_type": "project",
            "opportunity_title": "PAOS bisa memanfaatkan AI untuk eksperimen teknis yang masih abu-abu",
            "opportunity_action": "Pilih satu ide runtime atau tooling yang belum jalan, lalu gunakan AI sebagai partner eksplorasi terarah selama satu sesi kerja.",
            "learning_topic": "AI untuk eksplorasi runtime dan arsitektur",
            "experiment_name": "Pakai AI untuk membedah satu eksperimen runtime",
            "content_angle": "Nilai AI terbesar kadang bukan di coding cepat, tapi di membantu menjelajah ruang solusi yang belum jelas",
        },
        "ai_work_culture": {
            "summary": "Adopsi AI tidak cuma soal tool baru, tapi juga mulai memengaruhi ritme kerja, ekspektasi, dan kesehatan tim.",
            "priority_title": "Tentukan batas penggunaan AI yang tetap sehat untuk kerja tim",
            "important_title": "Diskusi soal burnout dan ritme kerja mulai ikut masuk ke adopsi AI",
            "why": "Kalau ekspektasi naik tanpa batas yang jelas, tim bisa cepat lelah meski tooling makin kuat.",
            "next_step": "Tulis aturan ringkas kapan AI dipakai, kapan perlu review manual, dan kapan tim harus melambat supaya kualitas tetap terjaga.",
            "opportunity_type": "career",
            "opportunity_title": "Sudut pandang realistis soal adopsi AI bisa menguatkan positioning kepemimpinan teknis kamu",
            "opportunity_action": "Buat catatan singkat tentang cara menjaga kualitas dan ritme kerja saat tim mulai makin bergantung pada AI.",
            "learning_topic": "Adopsi AI yang tetap sehat untuk tim engineering",
            "experiment_name": "Uji aturan kerja AI yang lebih sehat di satu sprint",
            "content_angle": "Adopsi AI yang matang bukan cuma soal cepat, tapi juga soal ritme kerja yang masih masuk akal",
        },
        "market_demand": {
            "summary": "Permintaan besar untuk AI coding mulai terlihat bukan cuma dari hype, tapi dari anggaran, lisensi, dan tooling yang ikut tumbuh.",
            "priority_title": "Petakan skill AI coding yang paling relevan untuk posisi teknis kamu",
            "important_title": "Permintaan enterprise untuk AI coding makin terlihat sebagai pasar yang nyata",
            "why": "Kalau belanja AI coding makin besar, skill evaluasi model, workflow, dan guardrail akan makin dicari.",
            "next_step": "Tulis daftar skill yang sekarang paling dekat dengan tren ini, lalu pilih satu yang bisa kamu latih minggu ini.",
            "opportunity_type": "career",
            "opportunity_title": "Positioning di AI coding workflow makin relevan untuk karier teknis",
            "opportunity_action": "Tonjolkan pengalamanmu di evaluasi model, automation workflow, atau guardrail dalam portofolio dan percakapan profesional.",
            "learning_topic": "Peta skill untuk AI coding workflow",
            "experiment_name": "Audit gap skill untuk AI coding workflow",
            "content_angle": "AI coding mulai jadi budget line nyata, bukan sekadar eksperimen kecil tim",
        },
        "general_ai_workflow": {
            "summary": "Ada beberapa sinyal baru yang sama-sama mengarah ke workflow AI yang lebih operasional, terukur, dan dekat ke kerja tim.",
            "priority_title": "Pilih satu sinyal workflow AI yang paling dekat dengan kebutuhan PAOS",
            "important_title": "Workflow AI terus bergerak ke arah yang lebih operasional",
            "why": "Perubahan kecil di model atau tooling bisa jadi penting kalau langsung memengaruhi kualitas kerja harian.",
            "next_step": "Ambil satu sinyal yang paling dekat dengan kebutuhanmu hari ini, lalu turunkan jadi eksperimen kecil yang bisa selesai dalam satu sesi kerja.",
            "opportunity_type": "project",
            "opportunity_title": "Ada peluang merapikan workflow AI yang sudah dipakai sekarang",
            "opportunity_action": "Fokus ke satu bottleneck utama, lalu ukur apakah perubahan kecil di model, evaluasi, atau observability memberi dampak nyata.",
            "learning_topic": "Dasar evaluasi workflow AI",
            "experiment_name": "Uji satu perubahan kecil di workflow AI",
            "content_angle": "Leverage AI sering datang dari workflow yang rapi, bukan dari ganti model setiap minggu",
        },
    }
    return mapping[theme]


def to_indonesian_sentence(text, fallback_title):
    value = compact_text(text)
    if not value:
        return ensure_complete_sentence(f"Sinyal ini relevan untuk workflow AI kamu: {fallback_title}", "id")
    if looks_english(value):
        return ensure_complete_sentence(
            f"Sinyal ini menunjukkan perubahan penting untuk workflow AI kamu: {fallback_title}",
            "id",
        )
    return ensure_complete_sentence(normalize_tone_id(value), "id")


def strip_forbidden_phrases(text):
    value = compact_text(text)
    replacements = (
        ("Tindaklanjuti:", ""),
        ("berdasarkan '", ""),
        ("Jadikan '", ""),
        ("Sinyal ini menunjukkan", "Terlihat"),
        (" ships ", " "),
        (" expands around ", " "),
        (" pushes ", " "),
        ("enterprise engineering playbooks", "workflow software tim"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    value = value.replace("''", "").replace("'", "")
    return compact_text(value)


def clean_user_facing_text(text):
    value = strip_forbidden_phrases(text)
    if looks_english(value):
        return ""
    return ensure_complete_sentence(normalize_tone_id(value), "id").rstrip(".")


def sanitize_summary_lines(lines):
    result = []
    for line in lines or []:
        cleaned = strip_forbidden_phrases(line)
        if looks_english(cleaned):
            continue
        cleaned = ensure_complete_sentence(normalize_tone_id(cleaned), "id")
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:4]


def normalize_dedupe_text(text):
    value = compact_text(text).lower()
    if not value:
        return value
    while value.startswith("#"):
        value = value[1:].strip()
    if ". " in value[:4]:
        prefix, rest = value.split(". ", 1)
        if prefix.isdigit():
            value = rest.strip()
    prefixes = (
        "angle:",
        "project:",
        "konten:",
        "karier:",
        "career:",
        "job:",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return compact_text(value)


def dedupe_section_items(items, title_field):
    deduped = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title_key = normalize_dedupe_text(item.get(title_field))
        if not title_key:
            continue
        refs_key = tuple(sorted(normalize_dedupe_text(ref) for ref in (item.get("source_refs") or []) if normalize_dedupe_text(ref)))
        key = (title_key, refs_key[:2])
        if key in seen or title_key in seen:
            continue
        seen.add(key)
        seen.add(title_key)
        deduped.append(item)
    return deduped


def dedupe_dashboard_payload(dashboard):
    payload = dict(dashboard or {})
    config = (
        ("priority_actions", "title"),
        ("important_signals", "title"),
        ("opportunities", "title"),
        ("content_branding", "angle"),
        ("learning_queue", "topic"),
        ("experiment_queue", "experiment"),
        ("watchlist", "item"),
    )
    for section, title_field in config:
        payload[section] = dedupe_section_items(payload.get(section) or [], title_field)
    payload["daily_summary"] = sanitize_summary_lines(payload.get("daily_summary") or [])
    return payload


def title_needs_rewrite(text):
    value = compact_text(text)
    if not value:
        return True
    lowered = value.lower()
    bad_markers = (
        "tindaklanjuti:",
        "ships",
        "expands around",
        "pushes",
        "enterprise engineering playbooks",
        "berdasarkan '",
        "jadikan '",
    )
    if any(marker in lowered for marker in bad_markers):
        return True
    return looks_english(value)


def signal_by_ref(signal_map, refs):
    for ref in refs or []:
        key = compact_text(ref)
        if key and key in signal_map:
            return signal_map[key]
    return None


def synthesize_dashboard_from_signals(signals, source_status):
    relevant = [s for s in signals if looks_actionable(s)]
    if not relevant:
        relevant = signals[:]

    def refs(signal):
        title = compact_text(signal.get("title"))
        return [title] if title else []

    simplified = [simplified_signal(signal) for signal in relevant[:4]]

    summary = []
    if simplified:
        lead = simplified[0]
        lead_title = compact_text(lead.get("important_title") or lead.get("priority_title"))
        summary = [
            "Hari ini sinyal AI coding makin condong ke workflow yang bisa dipakai di kerja nyata, bukan sekadar demo model baru.",
            "Yang paling menonjol: model dan tooling mulai dinilai dari kejujuran saat ragu, kestabilan task panjang, serta observability biaya dan sandboxing agent.",
            "Artinya buat PAOS: evaluasi tidak cukup dari output akhir. Kamu perlu cek apakah prosesnya stabil, terukur, dan bisa diulang di runtime kamu.",
            f"Takeaway praktis: pakai sinyal `{lead_title or 'utama hari ini'}` sebagai acuan untuk uji checklist kecil pada task coding panjang minggu ini.",
        ]
    if not summary:
        summary = [
            "Hari ini ada beberapa sinyal AI workflow yang relevan untuk kerja kamu.",
            "Fokus utamanya bukan hanya model baru, tapi kualitas proses kerja saat model dipakai di task nyata.",
            "Takeaway: lanjutkan evaluasi kecil yang bisa diulang agar keputusan tooling tetap berbasis hasil, bukan hype.",
        ]

    priority_actions = []
    for signal, item in zip(relevant[:3], simplified[:3]):
        priority_actions.append(
            {
                "title": item["priority_title"],
                "why_it_matters": ensure_complete_sentence(item["why"], "id"),
                "next_step": ensure_complete_sentence(item["next_step"], "id"),
                "source_refs": refs(signal),
            }
        )

    important_signals = []
    for signal, item in zip(relevant[:3], simplified[:3]):
        important_signals.append(
            {
                "title": item["important_title"],
                "meaning": ensure_complete_sentence(item["summary"], "id"),
                "why_watch": ensure_complete_sentence(item["why"], "id"),
                "source_refs": refs(signal),
            }
        )

    opportunities = []
    if relevant and simplified:
        top = relevant[0]
        top_item = simplified[0]
        opportunities.append(
            {
                "type": top_item["opportunity_type"],
                "title": top_item["opportunity_title"],
                "why_relevant": ensure_complete_sentence(top_item["why"], "id"),
                "suggested_action": ensure_complete_sentence(top_item["opportunity_action"], "id"),
                "source_refs": refs(top),
            }
        )

    learning_queue = []
    experiment_queue = []
    if relevant and simplified:
        first = relevant[0]
        first_item = simplified[0]
        learning_queue.append(
            {
                "topic": first_item["learning_topic"],
                "why_learn": ensure_complete_sentence(first_item["why"], "id"),
                "relevance": "Topik ini berhubungan langsung dengan kualitas workflow AI yang kamu pakai sehari-hari.",
                "start_from": "Mulai dari ringkasan sinyal dan satu sumber paling jelas, lalu tulis 3 catatan yang bisa dipraktikkan.",
                "source_refs": refs(first),
            }
        )
        experiment_queue.append(
            {
                "experiment": first_item["experiment_name"],
                "purpose": "Melihat dampak nyata ke kualitas dan biaya sebelum adopsi lebih luas.",
                "smallest_test": ensure_complete_sentence(first_item["next_step"], "id"),
                "expected_signal": "Ada perbaikan yang konsisten pada kualitas output atau efisiensi token/waktu.",
                "source_refs": refs(first),
            }
        )

    content_branding = []
    if relevant and simplified:
        first_item = simplified[0]
        content_branding.append(
            {
                "angle": first_item["content_angle"],
                "why_post": "Angle ini dekat dengan pengalaman engineer yang sedang mencari workflow AI yang lebih stabil, terukur, dan masuk akal dipakai setiap hari.",
                "threads_ready": "Kita sering sibuk membandingkan model paling pintar. Padahal di kerjaan nyata, yang makin terasa nilainya justru workflow yang rapi: model lebih jujur saat ragu, biaya per langkah kelihatan, dan eksperimen bisa diulang dengan hasil yang konsisten. Menurutku, leverage berikutnya bukan cuma di prompt atau benchmark. Leverage berikutnya ada di cara kita mendesain kerja dengan AI.",
                "x_ready": "Leverage AI sekarang bukan cuma model yang lebih pintar. Workflow yang rapi, biaya yang kelihatan, dan evaluasi yang jelas biasanya jauh lebih menentukan hasil.",
                "linkedin_angle": "Pelajaran penting dari perkembangan AI coding terbaru: nilai terbesar sering datang dari workflow design, observability, dan evaluasi yang rapi, bukan hanya dari memilih model paling baru.",
                "source_refs": refs(relevant[0]),
            }
        )

    summary = sanitize_summary_lines(summary)
    for collection, fields in (
        (priority_actions, ("title", "why_it_matters", "next_step")),
        (important_signals, ("title", "meaning", "why_watch")),
        (opportunities, ("title", "why_relevant", "suggested_action")),
        (learning_queue, ("topic", "why_learn", "relevance", "start_from")),
        (experiment_queue, ("experiment", "purpose", "smallest_test", "expected_signal")),
        (content_branding, ("angle", "why_post", "threads_ready", "x_ready", "linkedin_angle")),
    ):
        for item in collection:
            for field in fields:
                item[field] = clean_user_facing_text(item.get(field) or "") or strip_forbidden_phrases(item.get(field) or "")

    return {
        "daily_summary": summary[:4],
        "priority_actions": priority_actions[:3],
        "important_signals": important_signals[:3],
        "opportunities": opportunities[:3],
        "content_branding": content_branding[:1],
        "learning_queue": learning_queue[:2],
        "experiment_queue": experiment_queue[:2],
        "github_tools": {"status": "inactive", "items": []} if source_status.get("github") != "active" else {"status": "active", "items": []},
        "linkedin_network": {"status": "inactive", "items": []} if source_status.get("linkedin") != "active" else {"status": "active", "items": []},
        "career_jobs": {"status": "inactive", "items": []} if source_status.get("jobs") != "active" else {"status": "active", "items": []},
        "personal_context_updates": [],
        "watchlist": [],
        "source_coverage": build_source_coverage(source_status),
    }


def localize_dashboard_payload(dashboard, signals):
    payload = dict(dashboard or {})
    signal_map = {compact_text(signal.get("title")): signal for signal in signals or [] if compact_text(signal.get("title"))}
    top_title = compact_text((signals[0] or {}).get("title")) if signals else "workflow AI hari ini"
    summary = [compact_text(x) for x in (payload.get("daily_summary") or []) if compact_text(x)]
    fixed_summary = []
    for line in summary[:4]:
        fixed_summary.append(to_indonesian_sentence(line, top_title))
    if not fixed_summary:
        fixed_summary = [ensure_complete_sentence(f"Hari ini ada sinyal AI yang relevan untuk kerja kamu, terutama di area {top_title}.", "id")]
    payload["daily_summary"] = sanitize_summary_lines(fixed_summary)

    for item in payload.get("priority_actions") or []:
        signal = signal_by_ref(signal_map, item.get("source_refs"))
        if signal and title_needs_rewrite(item.get("title")):
            simplified = simplified_signal(signal)
            item["title"] = simplified["priority_title"]
            item["why_it_matters"] = simplified["why"]
            item["next_step"] = simplified["next_step"]

    for item in payload.get("important_signals") or []:
        signal = signal_by_ref(signal_map, item.get("source_refs"))
        if signal and title_needs_rewrite(item.get("title")):
            simplified = simplified_signal(signal)
            item["title"] = simplified["important_title"]
            item["meaning"] = simplified["summary"]
            item["why_watch"] = simplified["why"]

    for item in payload.get("opportunities") or []:
        signal = signal_by_ref(signal_map, item.get("source_refs"))
        if signal and title_needs_rewrite(item.get("title")):
            simplified = simplified_signal(signal)
            item["type"] = simplified["opportunity_type"]
            item["title"] = simplified["opportunity_title"]
            item["why_relevant"] = simplified["why"]
            item["suggested_action"] = simplified["opportunity_action"]

    for item in payload.get("learning_queue") or []:
        signal = signal_by_ref(signal_map, item.get("source_refs"))
        if signal and title_needs_rewrite(item.get("topic")):
            simplified = simplified_signal(signal)
            item["topic"] = simplified["learning_topic"]
            item["why_learn"] = simplified["why"]

    for item in payload.get("experiment_queue") or []:
        signal = signal_by_ref(signal_map, item.get("source_refs"))
        if signal and title_needs_rewrite(item.get("experiment")):
            simplified = simplified_signal(signal)
            item["experiment"] = simplified["experiment_name"]
            item["purpose"] = "Melihat dampak nyata ke kualitas dan biaya sebelum adopsi lebih luas."
            item["smallest_test"] = simplified["next_step"]

    for item in payload.get("content_branding") or []:
        signal = signal_by_ref(signal_map, item.get("source_refs"))
        if signal and title_needs_rewrite(item.get("angle")):
            simplified = simplified_signal(signal)
            item["angle"] = simplified["content_angle"]
            item["why_post"] = "Angle ini kuat karena dekat dengan keputusan kerja engineer yang sedang memilih workflow AI yang lebih matang."
            item["threads_ready"] = "Kita sering terpaku pada model terbaru. Tapi sinyal belakangan justru menunjukkan bahwa yang paling menentukan hasil adalah workflow: seberapa jujur model saat ragu, seberapa kelihatan biaya per langkah, dan seberapa rapi eksperimen bisa diulang. Buatku, itu tanda bahwa desain kerja AI sekarang lebih penting dari sekadar koleksi prompt."
            item["x_ready"] = "Model baru penting. Tapi workflow yang rapi, evaluasi yang jelas, dan biaya yang kelihatan biasanya lebih menentukan hasil akhir."

    for key_group in (
        ("priority_actions", ("title", "why_it_matters", "next_step")),
        ("important_signals", ("title", "meaning", "why_watch")),
        ("opportunities", ("title", "why_relevant", "suggested_action")),
        ("learning_queue", ("topic", "why_learn", "relevance", "start_from")),
        ("experiment_queue", ("experiment", "purpose", "smallest_test", "expected_signal")),
        ("content_branding", ("angle", "why_post", "threads_ready", "x_ready", "linkedin_angle")),
    ):
        section, fields = key_group
        for item in payload.get(section) or []:
            for field in fields:
                value = item.get(field)
                if isinstance(value, str):
                    cleaned = clean_user_facing_text(value)
                    item[field] = cleaned or strip_forbidden_phrases(value)
    return dedupe_dashboard_payload(payload)


def enforce_source_status_sections(dashboard, source_status):
    payload = dict(dashboard or {})
    for key, section in (
        ("github", "github_tools"),
        ("linkedin", "linkedin_network"),
        ("jobs", "career_jobs"),
    ):
        section_value = payload.get(section)
        if not isinstance(section_value, dict):
            section_value = {"status": "inactive", "items": []}
        if source_status.get(key) != "active":
            section_value["status"] = "inactive"
            section_value["items"] = []
        else:
            section_value["status"] = compact_text(section_value.get("status")) or "active"
            section_value["items"] = section_value.get("items") or []
        payload[section] = section_value
    payload["source_coverage"] = build_source_coverage(source_status)
    return payload


def dashboard_needs_backfill(dashboard, signals):
    if not isinstance(dashboard, dict):
        return True
    if not signals:
        return False
    signal_count = len(signals)
    if signal_count < 3:
        return False
    return (
        len(dashboard.get("priority_actions") or []) < 2
        or len(dashboard.get("important_signals") or []) < 2
        or len(dashboard.get("opportunities") or []) < 1
        or (
            len(dashboard.get("learning_queue") or []) < 1
            and len(dashboard.get("experiment_queue") or []) < 1
        )
    )


def merge_dashboard_with_fallback(dashboard, fallback):
    result = dict(fallback)
    if not isinstance(dashboard, dict):
        return result
    for key, value in dashboard.items():
        if key not in result:
            result[key] = value
            continue
        if isinstance(result[key], list):
            if value:
                result[key] = value
        elif isinstance(result[key], dict):
            merged = dict(result[key])
            if isinstance(value, dict):
                merged.update({k: v for k, v in value.items() if v not in (None, "", [], {})})
            result[key] = merged
        elif value not in (None, ""):
            result[key] = value
    return result


def render_user_prompt(signals, source_status):
    template = load_text_template(PROMPTS_DIR / "insight-user.md")
    digest_blob = json.dumps({"signals": signals}, ensure_ascii=False, indent=2)
    return (
        template.replace("{{ personal_context }}", "Tidak ada konteks personal tambahan.")
        .replace("{{ insight_contract }}", load_text_template(CONTRACTS_DIR / "insight.md"))
        .replace("{{ content_style_contract }}", load_text_template(CONTRACTS_DIR / "content-style.md"))
        .replace("{{ digest }}", digest_blob)
        .replace("{{ source_status }}", json.dumps(source_status, ensure_ascii=False))
    )


def build_messages(category, language, signals):
    source_status = detect_source_status(signals)
    system = load_text_template(PROMPTS_DIR / "insight-system.md")
    user = render_user_prompt(signals=signals, source_status=source_status)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_signal_reference(signal):
    return {
        "title": compact_text(signal.get("title")),
        "theme": compact_text(signal.get("theme")) or "Other",
        "summary": compact_text(signal.get("summary")),
        "why_it_matters": compact_text(signal.get("why_it_matters")),
        "source_urls": [compact_text(url) for url in (signal.get("source_urls") or []) if compact_text(url)],
        "source_accounts": [
            compact_text(account)
            for account in (signal.get("source_accounts") or [])
            if compact_text(account)
        ],
        "sources": [
            {
                "platform": compact_text(source.get("platform")),
                "source_type": compact_text(source.get("source_type")),
                "source_name": compact_text(source.get("source_name")),
                "url": compact_text(source.get("url")),
            }
            for source in (signal.get("sources") or [])
            if isinstance(source, dict)
        ],
    }


def validate_insight(raw_insight, signal_map, category, language, generation_mode):
    original_title = compact_text(raw_insight.get("title"))
    insight_type = compact_text(raw_insight.get("insight_type")).lower()
    priority = compact_text(raw_insight.get("priority")).lower()
    reason = normalize_reason(
        reason=raw_insight.get("reason"),
        title=original_title,
        insight_type=insight_type,
        language=language,
    )
    title = normalize_title_semantics(
        title=original_title,
        insight_type=insight_type,
        reason=reason,
        language=language,
    )
    metadata = raw_insight.get("insight_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    source_signal_titles = []
    seen_titles = set()
    for value in raw_insight.get("source_signal_titles") or []:
        normalized = compact_text(value)
        if not normalized or normalized not in signal_map or normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        source_signal_titles.append(normalized)

    if (
        not title
        or insight_type not in SUPPORTED_INSIGHT_TYPES
        or priority not in SUPPORTED_PRIORITIES
        or not reason
        or not source_signal_titles
    ):
        return None

    return {
        "title": title,
        "insight_type": insight_type,
        "priority": priority,
        "reason": reason,
        "source_signals": [build_signal_reference(signal_map[title]) for title in source_signal_titles],
        "generated_at": datetime.now().astimezone().isoformat(),
        "insight_metadata": {
            "insight_version": INSIGHT_VERSION,
            "generation_mode": generation_mode,
            "category": category,
            "language": language,
            "source_signal_count": len(source_signal_titles),
            **metadata,
        },
    }


def build_insights_from_dashboard(dashboard, signals, category, language, generation_mode):
    signal_map = {
        compact_text(signal.get("title")): signal
        for signal in signals
        if compact_text(signal.get("title"))
    }
    raw_insights = []
    for item in (dashboard.get("priority_actions") or []):
        raw_insights.append(
            {
                "title": item.get("title"),
                "insight_type": "project",
                "priority": "high",
                "reason": f"{compact_text(item.get('why_it_matters'))} {compact_text(item.get('next_step'))}",
                "source_signal_titles": item.get("source_refs") or [],
                "insight_metadata": {"section": "priority_actions"},
            }
        )
    for item in (dashboard.get("important_signals") or []):
        raw_insights.append(
            {
                "title": item.get("title"),
                "insight_type": "market",
                "priority": "medium",
                "reason": f"{compact_text(item.get('meaning'))} {compact_text(item.get('why_watch'))}",
                "source_signal_titles": item.get("source_refs") or [],
                "insight_metadata": {"section": "important_signals"},
            }
        )
    for item in (dashboard.get("learning_queue") or []):
        raw_insights.append(
            {
                "title": item.get("topic"),
                "insight_type": "learning",
                "priority": "medium",
                "reason": f"{compact_text(item.get('why_learn'))} {compact_text(item.get('start_from'))}",
                "source_signal_titles": item.get("source_refs") or [],
                "insight_metadata": {"section": "learning_queue"},
            }
        )
    for item in (dashboard.get("experiment_queue") or []):
        raw_insights.append(
            {
                "title": item.get("experiment"),
                "insight_type": "tool",
                "priority": "medium",
                "reason": f"{compact_text(item.get('purpose'))} {compact_text(item.get('smallest_test'))}",
                "source_signal_titles": item.get("source_refs") or [],
                "insight_metadata": {"section": "experiment_queue"},
            }
        )
    for item in (dashboard.get("content_branding") or []):
        raw_insights.append(
            {
                "title": item.get("angle"),
                "insight_type": "content",
                "priority": "medium",
                "reason": compact_text(item.get("why_post")),
                "source_signal_titles": item.get("source_refs") or [],
                "insight_metadata": {"section": "content_branding"},
            }
        )
    if not raw_insights:
        raise ValueError("Insight dashboard produced no insight candidates.")

    insights = []
    seen_keys = set()
    for raw_insight in raw_insights:
        normalized = validate_insight(
            raw_insight=raw_insight,
            signal_map=signal_map,
            category=category,
            language=language,
            generation_mode=generation_mode,
        )
        if not normalized:
            continue
        key = (
            normalized["title"].lower(),
            normalized["insight_type"],
            tuple(signal["title"] for signal in normalized["source_signals"]),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        insights.append(normalized)
    if insights:
        insights[0]["insight_metadata"]["dashboard_payload"] = dashboard
    if not insights:
        raise ValueError("Insight dashboard produced no valid insights after validation.")
    return ensure_important_coverage(insights, language)


def build_fallback_artifact(category, language, signals, generation_mode, ai_error=None, timeout_info=None):
    source_status = detect_source_status(signals)
    dashboard = synthesize_dashboard_from_signals(signals=signals, source_status=source_status)
    dashboard = enforce_source_status_sections(dashboard, source_status)
    dashboard = localize_dashboard_payload(dashboard, signals)
    dashboard = dedupe_dashboard_payload(dashboard)
    insights = build_insights_from_dashboard(
        dashboard=dashboard,
        signals=signals,
        category=category,
        language=language,
        generation_mode=generation_mode,
    )
    diagnostics = {
        "generation_mode": generation_mode,
        "fallback_used": True,
        "ai_failed": bool(ai_error),
        "ai_error_type": type(ai_error).__name__ if ai_error else None,
        "ai_error_message": compact_text(str(ai_error)) if ai_error else None,
    }
    if timeout_info:
        diagnostics.update(timeout_info)
    return insights, diagnostics


def generate_ai_insights(category, language, signals, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    config = env_config()
    if not ai_available():
        raise RuntimeError("AI configuration is incomplete.")

    started = time.time()
    endpoint = resolve_endpoint(config)
    timeout_tuple = resolve_ai_timeout()
    payload = {
        "model": config["model"],
        "messages": build_messages(category=category, language=language, signals=signals),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout_tuple,
    )
    response.raise_for_status()
    content = parse_response_content(response.json())
    parsed = json.loads(content)
    dashboard = parsed if isinstance(parsed, dict) else {}
    source_status = detect_source_status(signals)
    fallback_dashboard = synthesize_dashboard_from_signals(signals=signals, source_status=source_status)
    if dashboard_needs_backfill(dashboard, signals):
        dashboard = merge_dashboard_with_fallback(dashboard, fallback_dashboard)
    if not compact_text(" ".join(dashboard.get("daily_summary") or [])).strip():
        dashboard["daily_summary"] = fallback_dashboard.get("daily_summary") or []
    dashboard["source_coverage"] = dashboard.get("source_coverage") or fallback_dashboard.get("source_coverage")
    dashboard["github_tools"] = dashboard.get("github_tools") or fallback_dashboard.get("github_tools")
    dashboard["linkedin_network"] = dashboard.get("linkedin_network") or fallback_dashboard.get("linkedin_network")
    dashboard["career_jobs"] = dashboard.get("career_jobs") or fallback_dashboard.get("career_jobs")
    dashboard = enforce_source_status_sections(dashboard, source_status)
    dashboard = localize_dashboard_payload(dashboard, signals)
    dashboard = dedupe_dashboard_payload(dashboard)
    insights = build_insights_from_dashboard(
        dashboard=dashboard,
        signals=signals,
        category=category,
        language=language,
        generation_mode="ai",
    )

    diagnostics = {
        "generation_mode": "ai",
        "ai_provider": config["provider"],
        "ai_model": config["model"],
        "ai_endpoint": endpoint,
        "config_source": config["config_source"],
        "ai_connect_timeout_seconds": timeout_tuple[0],
        "ai_read_timeout_seconds": timeout_tuple[1],
        "ai_timeout_seconds": timeout_tuple[1],
        "ai_failed": False,
        "fallback_used": False,
        "ai_duration_seconds": round(time.time() - started, 2),
    }
    return insights, diagnostics


def infer_insight_type(signal):
    theme = compact_text(signal.get("theme")).lower()
    title = compact_text(signal.get("title")).lower()
    summary = compact_text(signal.get("summary")).lower()
    corpus = " ".join([theme, title, summary])

    if any(token in corpus for token in ("education", "prompt", "research", "learn")):
        return "learning"
    if any(token in corpus for token in ("tool", "workflow", "usage", "plugin", "code", "agent")):
        return "tool"
    if any(token in corpus for token in ("paos", "memory", "orchestration", "delivery", "review", "mnemosyne")):
        return "project"
    if any(token in corpus for token in ("content", "guide", "publishing", "education", "prompting")):
        return "content"
    if any(token in corpus for token in ("career", "talent", "developer", "operator")):
        return "career"
    return "market"


def infer_priority(signal):
    count = int(((signal.get("signal_metadata") or {}).get("candidate_count")) or 0)
    if count >= 4:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def build_heuristic_insight(signal, language):
    copy = COPY[language]
    insight_type = infer_insight_type(signal)
    reason = compact_text(signal.get("why_it_matters")) or copy["fallback_reason"]
    title = compact_text(signal.get("title")) or copy["header"]
    return {
        "title": title,
        "insight_type": insight_type,
        "priority": infer_priority(signal),
        "reason": reason,
        "source_signals": [build_signal_reference(signal)],
        "generated_at": datetime.now().astimezone().isoformat(),
        "insight_metadata": {
            "insight_version": INSIGHT_VERSION,
            "generation_mode": "heuristic",
            "language": language,
            "source_signal_count": 1,
        },
    }


def generate_heuristic_insights(signals, language):
    insights = [build_heuristic_insight(signal, language) for signal in signals[:10]]
    diagnostics = {
        "generation_mode": "heuristic",
        "heuristic_reason": COPY[language]["reason"],
    }
    return insights, diagnostics


def type_distribution(insights):
    counter = Counter(item.get("insight_type") or "unknown" for item in insights)
    return {key: counter.get(key, 0) for key in SUPPORTED_INSIGHT_TYPES}


def build_insight_layer(category, date, mode="auto"):
    resolved_date = resolve_date(date)
    signal_file, rendered_digest = validate_digest_freshness(
        date=resolved_date,
        category=category,
    )
    _input_path, signals = load_signals(date=resolved_date, category=category)
    if not signals:
        raise InsightFreshnessError(
            "Signal output is empty or incomplete. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )

    config = load_runtime_config()
    language = resolve_language(config)
    generation_mode = "heuristic"
    fallback_used = False
    diagnostics = {
        "input_path": str(signal_file),
        "digest_path": str(rendered_digest),
        "generation_mode": "heuristic",
        "fallback_used": False,
        "language": language,
        "ai_provider": env_config().get("provider") or None,
        "ai_model": env_config().get("model") or None,
        "ai_endpoint": resolve_endpoint(env_config()) if env_config().get("provider") and env_config().get("api_key") else None,
    }
    timeout_tuple = resolve_ai_timeout()
    diagnostics["ai_connect_timeout_seconds"] = timeout_tuple[0]
    diagnostics["ai_read_timeout_seconds"] = timeout_tuple[1]
    diagnostics["ai_timeout_seconds"] = timeout_tuple[1]
    diagnostics["ai_failed"] = False
    diagnostics["ai_error_type"] = None
    diagnostics["ai_error_message"] = None

    if mode == "heuristic":
        insights, extra_diagnostics = generate_heuristic_insights(signals=signals, language=language)
        diagnostics.update(extra_diagnostics)
    else:
        try:
            if mode == "ai" and not ai_available():
                raise RuntimeError("AI mode requested but AI configuration is unavailable.")
            insights, extra_diagnostics = generate_ai_insights(
                category=category,
                language=language,
                signals=signals,
            )
            generation_mode = "ai"
            diagnostics.update(extra_diagnostics)
            diagnostics["generation_mode"] = "ai"
        except Exception as exc:
            fallback_used = True
            diagnostics["fallback_used"] = True
            diagnostics["ai_failed"] = True
            diagnostics["ai_error"] = str(exc)
            diagnostics["ai_error_type"] = type(exc).__name__
            diagnostics["ai_error_message"] = compact_text(str(exc))
            fallback_generation_mode = "fallback_ai" if mode == "ai" else "heuristic"
            insights, extra_diagnostics = build_fallback_artifact(
                category=category,
                language=language,
                signals=signals,
                generation_mode=fallback_generation_mode,
                ai_error=exc,
                timeout_info={
                    "ai_provider": env_config().get("provider") or None,
                    "ai_model": env_config().get("model") or None,
                    "ai_endpoint": resolve_endpoint(env_config()) if env_config().get("provider") and env_config().get("api_key") else None,
                    "ai_connect_timeout_seconds": timeout_tuple[0],
                    "ai_read_timeout_seconds": timeout_tuple[1],
                    "ai_timeout_seconds": timeout_tuple[1],
                },
            )
            diagnostics.update(extra_diagnostics)
            diagnostics["generation_mode"] = fallback_generation_mode
            generation_mode = fallback_generation_mode

    jsonl_path = output_jsonl_path(resolved_date, category)
    markdown_path = output_markdown_path(resolved_date, category)
    write_jsonl(jsonl_path, insights)
    dashboard_payload = None
    if insights:
        dashboard_payload = (insights[0].get("insight_metadata") or {}).get("dashboard_payload")
    if not dashboard_payload:
        dashboard_payload = synthesize_dashboard_from_signals(signals=signals, source_status=detect_source_status(signals))
    dashboard_payload = enforce_source_status_sections(dashboard_payload, detect_source_status(signals))
    dashboard_payload = localize_dashboard_payload(dashboard_payload, signals)
    dashboard_payload = dedupe_dashboard_payload(dashboard_payload)
    write_markdown(markdown_path, render_insights(language=language, insights=insights, dashboard=dashboard_payload, signals=signals))
    diagnostics["output_path"] = str(markdown_path)

    return InsightBuildResult(
        category=category,
        date=resolved_date,
        language=language,
        signals_loaded=len(signals),
        insights_generated=len(insights),
        jsonl_path=jsonl_path,
        markdown_path=markdown_path,
        digest_path=rendered_digest,
        generation_mode=generation_mode,
        fallback_used=fallback_used,
        type_distribution=type_distribution(insights),
        diagnostics=diagnostics,
    )


def print_result(result):
    print("Insight Build")
    print(f"date: {result.date}")
    print(f"category: {result.category}")
    print(f"language: {result.language}")
    print(f"signals_loaded: {result.signals_loaded}")
    print(f"insights_generated: {result.insights_generated}")
    print(f"generation_mode: {result.generation_mode}")
    print(f"fallback_used: {result.fallback_used}")
    print(f"jsonl_path: {result.jsonl_path}")
    print(f"markdown_path: {result.markdown_path}")
    print("type_distribution:")
    for key, value in result.type_distribution.items():
        print(f"  {key}: {value}")
    print("diagnostics:")
    for key, value in result.diagnostics.items():
        print(f"  {key}: {value}")


def main():
    args = parse_args()
    result = build_insight_layer(category=args.category, date=args.date, mode=args.mode)
    print_result(result)


if __name__ == "__main__":
    main()
