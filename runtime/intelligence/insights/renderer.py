from collections import Counter
import re


COPY = {
    "en": {
        "title": "Daily Briefing",
        "empty": "No insights today.",
        "summary": "Summary",
        "signals": "Signals",
        "displayed": "Displayed",
        "separator": "━━━━━━━━━━",
        "sections": {
            "priority": "🔥 Today's Priority",
            "important": "🔥 What Matters Now",
            "learning": "🧠 Worth Learning",
            "tool": "🛠 Worth Trying",
            "content": "✍️ Ready to Post",
            "market": "👀 Worth Watching",
        },
        "threads_label": "Threads-ready",
        "x_label": "X-ready",
    },
    "id": {
        "title": "Insight Hari Ini",
        "empty": "Tidak ada insight hari ini.",
        "summary": "Ringkasan",
        "signals": "Sinyal diproses",
        "displayed": "Ditampilkan",
        "separator": "━━━━━━━━━━",
        "sections": {
            "priority": "🔥 Prioritas Hari Ini",
            "important": "🔥 Yang Lagi Penting",
            "learning": "🧠 Yang Layak Dipelajari",
            "tool": "🛠 Yang Layak Dicoba",
            "content": "✍️ Siap Diposting",
            "market": "👀 Yang Perlu Dipantau",
        },
        "threads_label": "Threads-ready",
        "x_label": "X-ready",
    },
}

SECTION_ORDER = ("important", "learning", "tool", "content", "market")
SENTENCE_BOUNDARY = re.compile(r"(?<!\d)[.!?](?!\d)")


def compact_text(value):
    return " ".join(str(value or "").split())


def trim_text(text, max_chars=128):
    normalized = compact_text(text)
    if len(normalized) <= max_chars:
        return normalized
    boundary_match = None
    for match in SENTENCE_BOUNDARY.finditer(normalized[:max_chars]):
        boundary_match = match
    if boundary_match:
        return normalized[: boundary_match.end()].rstrip(" ,;:")
    forward_boundary = SENTENCE_BOUNDARY.search(normalized[max_chars : max_chars + 120])
    if forward_boundary:
        end = max_chars + forward_boundary.start() + 1
        return normalized[:end].rstrip(" ,;:")
    shortened = normalized[:max_chars].rstrip(" ,;:")
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0].rstrip(" ,;:")
    return ""


def split_sentences(text):
    normalized = compact_text(text)
    if not normalized:
        return []
    chunks = []
    for piece in normalized.split(". "):
        piece = piece.strip(" .")
        if piece:
            chunks.append(piece)
    return chunks


def strip_instruction_prefix(text):
    value = compact_text(text)
    lowered = value.lower()
    prefixes = (
        "siapkan konten:",
        "siapkan konten",
        "tulis post tentang",
        "tulis posting tentang",
        "jadikan konten tentang",
        "buat posting tentang",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            value = value[len(prefix):].lstrip(" :;,-")
            break
    return value


def starts_with_action_verb_id(text):
    lowered = compact_text(text).lower()
    verbs = ("pelajari", "coba", "bangun", "evaluasi", "bandingkan", "uji", "baca", "catat", "jadikan")
    return any(lowered.startswith(f"{verb} ") for verb in verbs)


def is_action_line_id(text):
    lowered = compact_text(text).lower()
    if lowered.startswith("hari ini,"):
        return True
    if lowered.startswith("langkah hari ini:"):
        return True
    return starts_with_action_verb_id(lowered)


def to_observation_line(text):
    value = strip_instruction_prefix(text)
    if starts_with_action_verb_id(value):
        if "dengan " in value:
            value = value.split("dengan ", 1)[1]
        value = f"Sinyal saat ini menonjol: {value[0].lower() + value[1:] if value else 'pergeseran workflow AI makin nyata'}"
    return value


def source_titles(insight):
    return [compact_text(item.get("title")) for item in (insight.get("source_signals") or []) if compact_text(item.get("title"))]


def lower_blob(insight):
    fields = [insight.get("title"), insight.get("reason")]
    fields.extend(source_titles(insight))
    return compact_text(" ".join(str(value or "") for value in fields)).lower()


def _normalized_for_similarity(value):
    text = compact_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return compact_text(text)


def insight_identity(insight):
    title = _normalized_for_similarity(insight.get("title"))
    reason = _normalized_for_similarity(insight.get("reason"))
    return f"{title}|{reason}"


def insight_tokens(insight):
    token_set = set()
    for field in (insight.get("title"), insight.get("reason")):
        for token in _normalized_for_similarity(field).split():
            if len(token) >= 4:
                token_set.add(token)
    return token_set


def similar_insight(a, b):
    if insight_identity(a) == insight_identity(b):
        return True
    a_title = _normalized_for_similarity(a.get("title"))
    b_title = _normalized_for_similarity(b.get("title"))
    if a_title and b_title and (a_title in b_title or b_title in a_title):
        return True
    a_tokens = insight_tokens(a)
    b_tokens = insight_tokens(b)
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens)
    baseline = max(1, min(len(a_tokens), len(b_tokens)))
    return (overlap / baseline) >= 0.75


def similar_text(a, b):
    a_norm = _normalized_for_similarity(a)
    b_norm = _normalized_for_similarity(b)
    if not a_norm or not b_norm:
        return False
    if a_norm in b_norm or b_norm in a_norm:
        return True
    a_tokens = {token for token in a_norm.split() if len(token) >= 4}
    b_tokens = {token for token in b_norm.split() if len(token) >= 4}
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens)
    baseline = max(1, min(len(a_tokens), len(b_tokens)))
    return (overlap / baseline) >= 0.75


def personalize_phrase(text):
    value = compact_text(text)
    lowered = value.lower()
    if "signal builder" in lowered or "paos" in lowered or "forge" in lowered:
        return value
    if "opus 4.8" in lowered or "claude opus" in lowered:
        return f"{value} untuk Signal Builder PAOS"
    if "workflow" in lowered or "agent" in lowered:
        return f"{value} untuk workflow PAOS dan Forge"
    if "token" in lowered or "observability" in lowered:
        return f"{value} untuk PAOS"
    return value


def social_headline(insight, language):
    title = compact_text(insight.get("title"))
    return title or ("Insight worth attention today" if language == "en" else "Insight yang layak diperhatikan")


def social_body(insight, language):
    parts = split_sentences(insight.get("reason"))
    if not parts:
        return []
    return [trim_text(part, 132) for part in parts[:5] if trim_text(part, 132)]


def normalize_lines(lines, max_lines=6):
    result = []
    for line in lines:
        value = trim_text(line, 132).rstrip()
        value = re.sub(r"(\.{3}|…)+$", "", value).rstrip(" ,;:")
        if value and value not in result:
            result.append(value)
        if len(result) >= max_lines:
            break
    return result


def section_key_for_insight(insight):
    insight_type = insight.get("insight_type")
    blob = lower_blob(insight)
    if "open model" in blob or "china" in blob or "open-source" in blob:
        return "market"
    if "rwanda" in blob or "alx africa" in blob or "ai tutor" in blob:
        return "market"
    if insight_type in {"project", "career"}:
        return "important"
    if insight_type == "learning":
        return "learning"
    if insight_type == "tool":
        return "tool"
    if insight_type == "content":
        return "content"
    return "market"


def is_weak_telegram_item(insight):
    blob = lower_blob(insight)
    if "rwanda" in blob or "alx africa" in blob or "ai tutor" in blob:
        return True
    if "public-sector" in blob and "paos" not in blob and "forge" not in blob:
        return True
    return False


def is_strong_watch_item(insight):
    blob = lower_blob(insight)
    if insight_priority_score(insight) < 30:
        return False
    if "open model" in blob or "china" in blob or "open-source" in blob:
        return True
    if "openai" in blob and ("health" in blob or "hospital" in blob or "sector" in blob):
        return False
    return False


def build_statistics(signals, insights):
    distribution = Counter(item.get("insight_type") or "unknown" for item in insights)
    return {
        "signals": len(signals),
        "insights": len(insights),
        "distribution": dict(distribution),
    }


def count_displayed_insights(lines):
    return sum(
        1
        for line in lines
        if line.startswith(("1. ", "2. ", "3. ", "• "))
        and not line.startswith(("• Threads-ready:", "• X-ready:"))
    )


def render_feed_item(insight, language):
    lines = [f"• {social_headline(insight, language)}"]
    lines.extend(normalize_lines(social_body(insight, language), max_lines=6))
    return lines


def render_important_item(insight, language):
    headline = social_headline(insight, language)
    body = []
    for line in social_body(insight, language):
        if language == "id" and is_action_line_id(line):
            continue
        body.append(line)
    if not body:
        body = social_body(insight, language)
    lines = [f"• {headline}"]
    lines.extend(normalize_lines(body, max_lines=5))
    return lines


def insight_display_signature(insight, language):
    rendered = render_feed_item(insight, language)
    if not rendered:
        return ""
    headline = compact_text(rendered[0].lstrip("• ").strip()).lower()
    body = " ".join(compact_text(line).lower() for line in rendered[1:3])
    return compact_text(f"{headline} {body}")


def insight_headline_key(insight, language):
    return compact_text(social_headline(insight, language)).lower()


def post_from_insight(insight, language):
    blob = lower_blob(insight)
    if language == "id":
        if "workflow" in blob and "prompt" in blob:
            return [
                "Lucu juga ya.",
                "",
                "Kita masih sering debat prompt mana yang paling ampuh.",
                "",
                "Sementara vendor AI mulai geser fokus ke hal yang lebih membosankan, tapi mungkin lebih penting: workflow.",
                "",
                "Claude sekarang didorong supaya bisa bikin rencana, pecah kerjaan, jalan paralel, lalu ngecek hasilnya sendiri.",
                "",
                "Jadi bukan cuma \"jawab pertanyaan ini\".",
                "",
                "Lebih kayak: \"urusi kerjaan ini sampai masuk akal\".",
                "",
                "Prompt masih penting sih.",
                "",
                "Tapi makin kelihatan kalau leverage berikutnya bukan koleksi template prompt.",
                "",
                "Leverage berikutnya ada di cara kita mendesain kerja.",
            ]
        if "reliabil" in blob or "evaluasi" in blob or "jujur" in blob:
            return [
                "Makin lama, benchmark AI rasanya makin kurang bikin tenang.",
                "",
                "Hampir semua vendor bisa datang bawa skor bagus.",
                "",
                "Tapi di kerjaan nyata, yang sering bikin capek bukan model yang kurang pintar.",
                "",
                "Yang bikin capek itu model yang terlalu pede waktu salah.",
                "",
                "Makanya menurutku nilai baru yang perlu dilihat bukan cuma \"seberapa pintar\".",
                "",
                "Tapi: dia tahu kapan harus ragu nggak?",
                "",
                "Karena output yang jujur bilang \"ini belum yakin\" kadang jauh lebih berguna daripada jawaban rapi yang ternyata ngawur.",
            ]
        if "token" in blob or "observability" in blob:
            return [
                "Lucu juga ya.",
                "",
                "Dulu orang mikir AI mahal karena modelnya.",
                "",
                "Sekarang mulai kelihatan, yang sering bikin mahal itu bukan cuma model, tapi workflow yang bocor.",
                "",
                "Agent disuruh ngerjain task panjang. Dia baca file, manggil tool, bikin sub-task, revisi output, jalan lagi.",
                "",
                "Keliatannya produktif.",
                "",
                "Tapi kalau nggak ada usage per step, kita nggak tahu token habisnya di mana.",
                "",
                "Akhirnya yang disalahin modelnya.",
                "",
                "Padahal bisa jadi workflow kita sendiri yang berantakan.",
                "",
                "Makanya token observability bakal jadi penting. Bukan cuma buat finance, tapi buat engineer yang capek nebak-nebak biaya AI.",
            ]
        if "open model" in blob or "china" in blob or "open-source" in blob:
            return [
                "Open-source AI itu menarik bukan karena satu model tiba-tiba paling jago.",
                "",
                "Menurutku yang lebih bahaya justru ekosistemnya.",
                "",
                "Model bisa disalin. Benchmark bisa dikejar.",
                "",
                "Tapi kalau ribuan orang terus bikin tools, dataset, eval, wrapper, dan workflow di atasnya, itu beda cerita.",
                "",
                "Itu yang susah dilawan.",
                "",
                "Efeknya mirip Linux dulu.",
                "",
                "Awalnya kelihatan kalah rapi.",
                "",
                "Lalu pelan-pelan jadi fondasi banyak hal.",
            ]
    else:
        if "workflow" in blob and "prompt" in blob:
            return [
                "A lot of engineers are still optimizing prompts.",
                "",
                "Vendors are optimizing workflows.",
                "",
                "That is the shift worth watching.",
            ]
    reason_parts = [strip_instruction_prefix(part) for part in split_sentences(insight.get("reason"))]
    title = compact_text(insight.get("title"))
    if reason_parts:
        lines = []
        if title and not starts_with_action_verb_id(title):
            lines.extend([title, ""])
        lines.extend([trim_text(part, 180) for part in reason_parts[:5] if trim_text(part, 180)])
        if len(lines) < 4 and language == "id":
            lines.extend(
                [
                    "",
                    "Kalau kamu lagi bangun workflow AI, ini layak dicoba sekarang.",
                ]
            )
        return lines
    return None


def x_post_from_insight(insight, language):
    blob = lower_blob(insight)
    if language == "id":
        if "token" in blob or "observability" in blob:
            return [
                "AI agent mahal belum tentu karena modelnya. Kadang workflow kita sendiri yang bocor.",
                "",
                "Agent baca file, panggil tool, bikin sub-task, revisi output, jalan lagi. Kelihatan produktif.",
                "",
                "Tapi kalau nggak ada usage per step, kita cuma nebak token habis di mana.",
            ]
        if "reliabil" in blob or "evaluasi" in blob or "jujur" in blob:
            return [
                "Benchmark AI makin kurang bikin tenang.",
                "",
                "Bukan karena nggak penting.",
                "",
                "Tapi karena hampir semua vendor bisa pamer skor bagus.",
                "",
                "Yang lebih susah dicari: model yang tahu kapan dia salah.",
            ]
        if "open model" in blob or "china" in blob or "open-source" in blob:
            return [
                "Yang bikin open-source AI susah dikejar bukan modelnya.",
                "",
                "Tapi ekosistemnya.",
                "",
                "Model bisa disalin.",
                "Komunitas, tools, benchmark, dan workflow jauh lebih susah dikejar.",
            ]
        if "workflow" in blob and "prompt" in blob:
            return [
                "Banyak engineer masih sibuk ngulik prompt.",
                "",
                "Padahal vendor AI mulai geser ke workflow.",
                "",
                "AI yang bisa bikin rencana, pecah kerjaan, jalan paralel, lalu cek hasil sendiri.",
                "",
                "Prompt tetap penting. Tapi leverage berikutnya kayaknya ada di desain kerja.",
            ]
    reason_parts = [strip_instruction_prefix(part) for part in split_sentences(insight.get("reason"))]
    title = compact_text(insight.get("title"))
    if reason_parts:
        lines = []
        if title and not starts_with_action_verb_id(title):
            lines.append(trim_text(title, 140))
            lines.append("")
        lines.extend([trim_text(part, 160) for part in reason_parts[:3] if trim_text(part, 160)])
        if len([line for line in lines if compact_text(line)]) < 2 and language == "id":
            lines.append("Ini bisa jadi bahan diskusi yang relevan buat workflow AI hari ini.")
        return lines
    return None


def build_ready_posts(language, insights, blocked_headlines=None):
    threads_post = None
    x_post = None
    seen_first_lines = set()
    blocked_headlines = blocked_headlines or set()
    for insight in insights:
        if insight_headline_key(insight, language) in blocked_headlines:
            continue
        if is_weak_telegram_item(insight):
            continue
        if section_key_for_insight(insight) not in {"important", "learning", "tool", "market", "content"}:
            continue
        if not threads_post:
            post = post_from_insight(insight, language)
            first_line = compact_text(next((line for line in (post or []) if compact_text(line)), ""))
            if (
                post
                and first_line
                and first_line not in seen_first_lines
                and all(not similar_text(first_line, blocked) for blocked in blocked_headlines)
            ):
                seen_first_lines.add(first_line)
                threads_post = (COPY.get(language, COPY["en"])["threads_label"], post)
        if not x_post:
            post = x_post_from_insight(insight, language)
            first_line = compact_text(next((line for line in (post or []) if compact_text(line)), ""))
            if (
                post
                and first_line
                and first_line not in seen_first_lines
                and all(not similar_text(first_line, blocked) for blocked in blocked_headlines)
            ):
                seen_first_lines.add(first_line)
                x_post = (COPY.get(language, COPY["en"])["x_label"], post)
        if threads_post and x_post:
            break
    return [item for item in (threads_post, x_post) if item]


def post_from_content_insight(insight, language):
    blob = lower_blob(insight)
    reason_parts = [strip_instruction_prefix(part) for part in split_sentences(insight.get("reason"))]
    if language == "id":
        if "workflow" in blob and "agent" in blob:
            return [
                "Kayaknya skill AI berikutnya bukan sekadar prompting.",
                "",
                "Atau minimal, bukan prompting doang.",
                "",
                "Karena AI yang makin berguna itu bukan cuma AI yang bisa jawab.",
                "",
                "Tapi AI yang bisa ngerti kerjaan panjang.",
                "",
                "Bisa pecah task.",
                "Bisa jalan paralel.",
                "Bisa cek hasilnya sendiri.",
                "Bisa tahu kapan perlu berhenti dan minta bantuan.",
                "",
                "Prompt masih penting sih.",
                "",
                "Tapi desain workflow mulai kelihatan lebih mahal nilainya.",
            ]
        if reason_parts:
            lines = [trim_text(compact_text(insight.get("title")), 120), ""]
            lines.extend([trim_text(part, 150) for part in reason_parts[:4] if trim_text(part, 150)])
            return lines
    return None


def render_ready_post(label, post):
    lines = [f"• {label}:"]
    lines.extend(post)
    return lines


def insight_priority_score(insight):
    priority_scores = {"high": 30, "medium": 20, "low": 10}
    type_scores = {
        "project": 9,
        "learning": 8,
        "tool": 7,
        "market": 5,
        "content": 4,
        "career": 4,
    }
    source_count = len(insight.get("source_signals") or [])
    blob = lower_blob(insight)
    topic_bonus = 0
    for keyword in ("workflow", "token", "reliabil", "evaluasi", "opus 4.8", "open-source", "open model"):
        if keyword in blob:
            topic_bonus += 1
    return (
        priority_scores.get(insight.get("priority"), 0)
        + type_scores.get(insight.get("insight_type"), 0)
        + min(source_count, 3)
        + min(topic_bonus, 3)
    )


def ranked_insights(insights):
    return sorted(
        insights,
        key=lambda insight: (insight_priority_score(insight), compact_text(insight.get("title"))),
        reverse=True,
    )


def _append_unique_insight(target, candidate, used):
    for existing in used:
        if similar_insight(existing, candidate):
            return False
    used.append(candidate)
    target.append(candidate)
    return True


def _append_unique_display(
    target,
    candidate,
    used_insights,
    used_signatures,
    used_headlines,
    language,
):
    headline = insight_headline_key(candidate, language)
    if not headline or headline in used_headlines:
        return False
    signature = insight_display_signature(candidate, language)
    if not signature or signature in used_signatures:
        return False
    if not _append_unique_insight(target, candidate, used_insights):
        return False
    used_headlines.add(headline)
    used_signatures.add(signature)
    return True


def render_insight_sections(language, insights):
    copy = COPY.get(language, COPY["en"])
    buckets = {key: [] for key in SECTION_ORDER}
    editorial_items = [item for item in ranked_insights(insights) if not is_weak_telegram_item(item)]
    used_insights = []
    used_signatures = set()
    used_headlines = set()
    top_items = []
    for insight in editorial_items:
        if len(top_items) >= 3:
            break
        _append_unique_display(
            top_items,
            insight,
            used_insights,
            used_signatures,
            used_headlines,
            language,
        )

    remaining = [item for item in editorial_items if all(not similar_insight(item, used) for used in used_insights)]
    for section in SECTION_ORDER:
        if section == "content":
            continue
        section_candidates = [item for item in remaining if section_key_for_insight(item) == section]
        if section == "market":
            section_candidates = [item for item in section_candidates if is_strong_watch_item(item)]
        picked = []
        for candidate in section_candidates:
            if _append_unique_display(
                picked,
                candidate,
                used_insights,
                used_signatures,
                used_headlines,
                language,
            ):
                break
        buckets[section] = picked
        if picked:
            remaining = [item for item in remaining if all(not similar_insight(item, used) for used in used_insights)]

    if not buckets["important"]:
        fallback_candidates = [
            item for item in remaining
            if section_key_for_insight(item) in {"market", "tool", "learning"}
        ]
        for candidate in fallback_candidates:
            candidate_title = compact_text(candidate.get("title"))
            if starts_with_action_verb_id(candidate_title):
                candidate = dict(candidate)
                candidate["title"] = to_observation_line(candidate_title)
            if _append_unique_display(
                buckets["important"],
                candidate,
                used_insights,
                used_signatures,
                used_headlines,
                language,
            ):
                remaining = [item for item in remaining if all(not similar_insight(item, used) for used in used_insights)]
                break

    content_candidates = [item for item in remaining if section_key_for_insight(item) == "content"]
    buckets["content"] = []
    for candidate in content_candidates:
        if _append_unique_display(
            buckets["content"],
            candidate,
            used_insights,
            used_signatures,
            used_headlines,
            language,
        ):
            break

    ready_posts = build_ready_posts(
        language,
        remaining,
        blocked_headlines=set(used_headlines),
    )
    lines = [f"# {copy['title']}", ""]
    rendered_sections = 0

    if top_items:
        lines.extend([f"## {copy['sections']['priority']}", ""])
        for index, insight in enumerate(top_items, start=1):
            rendered = render_feed_item(insight, language)
            if rendered:
                rendered[0] = f"{index}. {rendered[0].lstrip('• ').strip()}"
            lines.extend(rendered)
            lines.append("")
        rendered_sections += 1

    for section in SECTION_ORDER:
        items = buckets[section]
        if not items and section != "content":
            continue

        if rendered_sections:
            lines.extend(["", copy["separator"], ""])

        if section == "content":
            merged_posts = []
            for insight in items:
                post = post_from_content_insight(insight, language)
                if post:
                    merged_posts.append((copy["threads_label"], post))
            merged_posts.extend(ready_posts)

            if not merged_posts:
                continue

            lines.extend([f"## {copy['sections'][section]}", ""])
            rendered_any = False
            seen_posts = set()
            seen_labels = set()
            for label, post in merged_posts:
                key = compact_text("\n".join(post))
                if not key or key in seen_posts or label in seen_labels:
                    continue
                seen_posts.add(key)
                seen_labels.add(label)
                lines.extend(render_ready_post(label, post))
                lines.append("")
                rendered_any = True
                if len(seen_labels) >= 2:
                    break
            if not rendered_any:
                continue
        else:
            lines.extend([f"## {copy['sections'][section]}", ""])
            for insight in items:
                if section == "important":
                    lines.extend(render_important_item(insight, language))
                else:
                    lines.extend(render_feed_item(insight, language))
                lines.append("")

        rendered_sections += 1

    if not rendered_sections:
        lines.extend([copy["empty"], ""])

    return lines, len(used_insights)


def render_insights(category, date, language, signals, insights):
    copy = COPY.get(language, COPY["en"])
    stats = build_statistics(signals, insights)
    lines, displayed_count = render_insight_sections(language=language, insights=insights)
    lines.extend(
        [
            copy["separator"],
            "",
            f"## {copy['summary']}",
            "",
            f"{copy['signals']}: {stats['signals']}",
            f"{copy['displayed']}: {displayed_count} insight terbaik",
            "",
        ]
    )
    return "\n".join(lines)


def render_telegram_brief(language, signals, insights):
    rendered = render_insights(
        category="",
        date="",
        language=language,
        signals=signals,
        insights=insights,
    )
    lines = rendered.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[2:] if len(lines) > 1 and not lines[1].strip() else lines[1:]
    return "\n".join(lines).strip()
