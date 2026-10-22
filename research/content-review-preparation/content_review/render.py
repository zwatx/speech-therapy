"""Static HTML reading copy of the content review preparation packet.

render_packet(packet) validates the packet against the pinned compiler output
first, then returns one self-contained HTML document: no scripts, no external
assets, no timestamps. Every packet value passes through html.escape. The page
records no decisions; the existing controlled SLP record stays the only
approval workflow.
"""

from __future__ import annotations

from html import escape

from .packet import validate_packet

__all__ = ["render_packet"]


_SHARED_ISSUES = ("reference_variety_pending", "professional_review_pending")

_ISSUE_ORDER = (
    "variant_choice",
    "selected_occurrence_ambiguous",
    "repeated_target",
    "source_spelling_alias",
    "cluster_context",
    "unsupported_target",
)

_ISSUE_LABELS = {
    "variant_choice": "More than one dictionary pronunciation",
    "repeated_target": "Target sound repeats in the word",
    "selected_occurrence_ambiguous": "Several occurrences at the selected position",
    "source_spelling_alias": "Displayed spelling differs from source",
    "unsupported_target": "Target outside current model inventory",
    "cluster_context": "Target inside a consonant cluster",
    "reference_variety_pending": "Reference variety",
    "professional_review_pending": "Professional review",
}

_ISSUE_SUMMARIES = {
    "variant_choice": "Decide which dictionary pronunciations are acceptable references. All are kept; none is chosen.",
    "selected_occurrence_ambiguous": "Record an explicit occurrence rule. The packet lists every index and does not pick one.",
    "repeated_target": "Decide how other occurrences of the same sound in the word are treated.",
    "source_spelling_alias": "Confirm the displayed spelling and that it names the same word as the source spelling.",
    "cluster_context": "Decide whether a target inside a consonant cluster is acceptable for its position.",
    "unsupported_target": "An engineering coverage limit only. It does not make the word invalid.",
    "reference_variety_pending": "Which variety of English a reference should represent is not yet chosen.",
    "professional_review_pending": "A qualified decision belongs in the existing controlled SLP record.",
}

_REQUIREMENTS = {
    "reference_variety": ("Reference variety", "Which variety of English a reference pronunciation should represent."),
    "acceptable_variants": ("Acceptable variants", "Which of the listed dictionary pronunciations are acceptable."),
    "occurrence_rule": ("Occurrence rule", "Which target occurrence counts, stated explicitly by index."),
    "age_readiness": ("Age readiness", "Whether the word and target suit the stated age scope."),
    "adult_support": ("Adult support", "What adult involvement an exercise with this prompt would need."),
    "reference_provenance": ("Reference provenance", "Who would produce a reference, and how. A description, not proof."),
    "reference_rights": ("Reference rights", "Permission to use a reference. A description, not verified rights."),
    "reference_scope": ("Reference scope", "What a reference may and may not be used for."),
    "illustration_meaning_rights": (
        "Illustration meaning and rights",
        "Whether a picture clearly shows this word, and permission to use it.",
    ),
    "cue_instruction_safety": (
        "Cue and instruction safety",
        "Whether any cue or instruction wording is safe. None is supplied here.",
    ),
    "controlled_professional_record": (
        "Controlled professional record",
        "The decision itself, recorded in the existing controlled SLP record.",
    ),
}

_REQUIREMENT_GROUPS = (
    ("Pronunciation and occurrence", ("reference_variety", "acceptable_variants", "occurrence_rule")),
    ("Learner suitability", ("age_readiness", "adult_support")),
    ("Reference source", ("reference_provenance", "reference_rights", "reference_scope")),
    ("Materials and instructions", ("illustration_meaning_rights", "cue_instruction_safety")),
    ("Professional record", ("controlled_professional_record",)),
)

_CLAIM_LABELS = {
    "qualifiedApprovalEstablished": "Qualified professional approval",
    "referenceAudioVerified": "Reference audio verified",
    "rightsVerified": "Rights verified",
    "learnerFeedbackEligible": "Eligible for learner feedback",
    "clinicalUseEligible": "Eligible for clinical use",
    "productionUseEligible": "Eligible for production use",
}

_WORKFLOW_LABELS = (
    ("handoff", "SLP handoff"),
    ("worksheet", "Engineering pack worksheet"),
    ("annotationPreparation", "Annotation data preparation"),
)

_POSITION_LABELS = {
    "beginning": "Beginning of word",
    "middle": "Middle of word",
    "end": "End of word",
}

_LANGUAGE_LABELS = {"en": "English"}


_CSS = """
:root{color-scheme:light;--ink:#1c1c1a;--muted:#55544d;--rule:#d8d4c8;--paper:#f8f7f2;--panel:#fff;--hover:#efede5;--teal:#0b5a55;--teal-bg:#e3efed;--amber-ink:#6b4100;--amber-bg:#fbefd8;--amber-rule:#b97c12;--serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 var(--sans)}
h1,h2,h3{font-family:var(--serif);font-weight:600;line-height:1.2;color:var(--ink)}
h4{font-size:.8125rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:1.5rem 0 .6rem;font-weight:600}
h5{font-size:.8125rem;margin:0 0 .3rem;color:var(--muted);font-weight:600}
code,.ph,.vid{font-family:var(--mono);font-size:.875em}
a{color:var(--teal);text-underline-offset:.15em}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--teal);outline-offset:2px;border-radius:2px}
main:focus:not(:focus-visible){outline:none}
.vh{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.skip{position:absolute;left:1rem;top:-4rem;z-index:10;background:var(--ink);color:#fff;padding:.5rem .8rem;border-radius:3px}
.skip:focus{top:1rem}
.muted{color:var(--muted)}
.wrap{max-width:80rem;margin:0 auto;padding:0 2rem}
.masthead{border-bottom:1px solid var(--rule);background:var(--panel)}
.masthead .wrap{padding-top:2.25rem;padding-bottom:2rem}
.eyebrow{text-transform:uppercase;letter-spacing:.09em;font-size:.75rem;font-weight:600;color:var(--muted);margin:0 0 .5rem}
h1{font-size:2.25rem;margin:0 0 .6rem}
.lede{max-width:46rem;color:var(--muted);font-size:1.0625rem;margin:0 0 1.5rem}
.status-banner{max-width:60rem;background:var(--amber-bg);color:var(--amber-ink);border:1px solid var(--amber-rule);border-left:6px solid var(--amber-rule);border-radius:3px;padding:1rem 1.25rem 1.1rem}
.status-banner h2{font-family:var(--sans);font-size:1.1875rem;font-weight:700;color:var(--amber-ink);margin:0 0 .5rem;letter-spacing:.01em}
.status-banner ul{margin:0;padding-left:1.15rem}
.status-banner li{margin:.15rem 0}
.counts{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));max-width:60rem;margin:1.5rem 0 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.counts div{padding:.8rem 1rem .8rem 0}
.counts div+div{padding-left:1rem;border-left:1px solid var(--rule)}
.counts dt{font-size:.8125rem;color:var(--muted);line-height:1.3}
.counts dd{margin:.2rem 0 0;font-family:var(--serif);font-size:2rem;line-height:1.1}
.index-note{max-width:60rem;font-size:.9375rem;margin:1rem 0 0}
.layout{display:grid;grid-template-columns:15rem minmax(0,1fr);gap:2.5rem;align-items:start}
.toc{position:sticky;top:0;max-height:100vh;overflow-y:auto;padding:1.75rem .25rem 2rem 0;font-size:.875rem}
.toc-title{font-size:.6875rem;text-transform:uppercase;letter-spacing:.1em;font-weight:600;color:var(--muted);margin:0 0 .35rem .5rem}
.toc ol{list-style:none;margin:0 0 1.5rem;padding:0}
.toc a{display:flex;gap:.5rem;align-items:baseline;padding:.28rem .5rem;border-radius:3px;color:var(--ink);text-decoration:none}
.toc a:hover{background:var(--hover)}
.toc-n{font-family:var(--mono);font-size:.75rem;color:var(--muted);min-width:1.3rem}
.toc-w{font-weight:600;min-width:0;overflow-wrap:anywhere}
.toc-m{margin-left:auto;font-size:.75rem;color:var(--muted);white-space:nowrap}
.toc-pending{display:block;margin:0 0 .5rem .5rem;font-size:.75rem;color:var(--amber-ink)}
main{min-width:0;max-width:52rem;padding:1.75rem 0 1rem}
main>section{margin:0 0 3rem}
section[id],article[id]{scroll-margin-top:1rem}
h2{font-size:1.625rem;margin:0 0 .75rem}
main p,main li{max-width:46rem}
.legend{display:flex;flex-wrap:wrap;gap:.5rem 1.5rem;padding:0;margin:.75rem 0 0;list-style:none;font-size:.875rem}
.legend li{display:flex;gap:.4rem;align-items:center}
.idx{display:inline-block;min-width:1.7em;padding:0 .35em;border:1px solid var(--rule);border-radius:3px;background:var(--panel);font-family:var(--mono);font-size:.8125rem;text-align:center;line-height:1.5}
.idx.sel{border-color:var(--teal);color:var(--teal);background:var(--teal-bg);font-weight:700}
.idx-t{font-family:var(--mono);font-weight:700}
.badge{display:inline-block;font-size:.75rem;font-weight:700;letter-spacing:.02em;padding:.12rem .55rem;border-radius:999px;border:1px solid;white-space:nowrap}
.badge-pending{color:var(--amber-ink);background:var(--amber-bg);border-color:var(--amber-rule)}
.badge-info{color:var(--teal);background:var(--teal-bg);border-color:var(--teal)}
.tag{display:inline-block;font-size:.75rem;padding:.05rem .45rem;border:1px solid var(--amber-rule);border-radius:3px;color:var(--amber-ink);background:var(--amber-bg)}
.qs{margin:0;padding:0}
.qs>div{display:grid;grid-template-columns:minmax(0,15rem) minmax(0,1fr);gap:.25rem 1.5rem;padding:.85rem 0;border-top:1px solid var(--rule)}
.qs dt{font-weight:600}
.qs dd{margin:0}
.qs dd p{margin:0 0 .25rem}
.qs-links a{white-space:nowrap}
.req-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:1.25rem 2rem;margin-top:1rem}
.req-groups ul{list-style:none;margin:0;padding:0}
.req-groups li{margin:0 0 .55rem;font-size:.9375rem}
.req-groups li strong{display:block;font-weight:600}
.req-groups li span{display:block;color:var(--muted);font-size:.875rem}
.prompt{background:var(--panel);border:1px solid var(--rule);border-radius:4px;padding:1.4rem 1.75rem 1.25rem;margin:0 0 1.5rem}
.prompt:target{border-color:var(--teal);box-shadow:0 0 0 3px var(--teal-bg)}
.prompt-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:.5rem 1rem;border-bottom:1px solid var(--rule);padding-bottom:.75rem;margin-bottom:1rem}
.prompt-head h3{font-size:1.75rem;margin:0}
.prompt-num{display:block;font-family:var(--sans);font-size:.75rem;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-bottom:.2rem}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.7rem 1.5rem;margin:0}
.facts dt{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.facts dd{margin:.1rem 0 0;overflow-wrap:anywhere}
.variant{margin:0 0 1.1rem}
.variant figcaption{font-size:.9375rem;margin:0 0 .4rem}
.vid{color:var(--muted)}
.table-wrap{max-width:100%;overflow-x:auto}
table.phones{border-collapse:collapse;font-size:.875rem}
table.phones th{text-align:left;font-weight:500;color:var(--muted);padding:.3rem .9rem .3rem 0;white-space:nowrap}
table.phones td{text-align:center;min-width:2.9rem;padding:.3rem .5rem;border-left:1px solid var(--rule)}
table.phones tr+tr th,table.phones tr+tr td{border-top:1px solid var(--rule)}
table.phones .r-idx td{font-family:var(--mono);font-size:.8125rem;color:var(--muted)}
table.phones .r-ph td{font-family:var(--mono);font-size:1rem;font-weight:700}
table.phones .r-ph td.is-target{background:var(--hover)}
table.phones .r-ph td.is-selected{box-shadow:inset 0 -3px 0 var(--teal)}
.mk-t{color:var(--ink)}
.mk-s{color:var(--teal);font-weight:700}
.mk-no{color:var(--muted)}
.idx-line{display:flex;flex-wrap:wrap;gap:.35rem 1.5rem;margin:.5rem 0 0;font-size:.875rem;color:var(--muted)}
.note{font-size:.875rem;margin:.45rem 0 0;padding:.4rem .7rem;border-left:3px solid var(--teal);background:var(--teal-bg)}
.hl{color:var(--teal);font-weight:700;text-decoration:underline;text-underline-offset:.2em}
.questions{list-style:none;margin:0;padding:0}
.questions li{border-left:3px solid var(--amber-rule);padding:.15rem 0 .15rem .9rem;margin:0 0 .85rem}
.q-label{display:block;font-size:.75rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--amber-ink);margin-bottom:.1rem}
.shared{font-size:.875rem;color:var(--muted);margin:.25rem 0 0}
.checklist{display:grid;grid-template-columns:repeat(auto-fit,minmax(13.5rem,1fr));gap:.9rem 1.75rem}
.checklist ul{list-style:none;margin:0;padding:0}
.checklist li{display:flex;gap:.5rem;align-items:baseline;font-size:.875rem;padding:.12rem 0}
.box{flex:none;width:.7rem;height:.7rem;border:1.5px solid var(--amber-rule);border-radius:2px}
.pend{margin-left:auto;padding-left:.5rem;font-size:.75rem;color:var(--amber-ink);white-space:nowrap}
.back{display:inline-block;margin-top:1rem;font-size:.8125rem}
.callout{border:1px solid var(--rule);border-left:4px solid var(--ink);background:var(--panel);padding:.9rem 1.2rem;margin:1rem 0;border-radius:3px}
.callout p{margin:.3rem 0}
.draft-flag{display:inline-block;font-family:var(--sans);font-size:.75rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--amber-ink);background:var(--amber-bg);border:1px solid var(--amber-rule);border-radius:3px;padding:.05rem .45rem;vertical-align:middle;margin-left:.4rem}
.paths{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:.45rem 1.25rem;margin:1rem 0}
.paths dt{font-weight:600}
.paths dd{margin:0;overflow-wrap:anywhere}
table.limits{border-collapse:collapse;width:100%;max-width:40rem;font-size:.9375rem}
table.limits th,table.limits td{text-align:left;padding:.5rem .75rem .5rem 0;border-bottom:1px solid var(--rule)}
table.limits thead th{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}
table.limits td{color:var(--amber-ink);font-weight:600}
.site-foot{border-top:1px solid var(--rule);margin-top:1rem;padding:1.25rem 0 2.5rem;font-size:.8125rem;color:var(--muted)}
.site-foot p{margin:0 0 .5rem}
.tech{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:.2rem 1rem;margin:.5rem 0 0}
.tech dd{margin:0;font-family:var(--mono);font-size:.75rem;overflow-wrap:anywhere}
@media (max-width:60rem){
.layout{grid-template-columns:minmax(0,1fr);gap:0}
.toc{position:static;max-height:none;border-bottom:1px solid var(--rule)}
.toc-prompts{columns:2;column-gap:1.5rem}
.counts{grid-template-columns:repeat(3,minmax(0,1fr))}
.counts div:nth-child(4){border-left:0;padding-left:0}
.qs>div{grid-template-columns:minmax(0,1fr)}
}
@media print{
@page{margin:15mm}
body{background:#fff;font-size:10pt}
.skip,.toc,.back{display:none}
.wrap{max-width:none;padding:0}
.layout{display:block}
main{max-width:none;padding-top:1rem}
.masthead{background:#fff}
.prompt{break-inside:avoid;border-color:#999}
.prompt:target{box-shadow:none}
h2,h3,h4,h5{break-after:avoid}
a{color:inherit;text-decoration:none}
.status-banner,.badge,.tag,.idx.sel,.note,.draft-flag,table.phones td{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.counts dd{font-size:1.5rem}
}
"""


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _and(items: list[str]) -> str:
    """Join already-escaped fragments as plain English: a, b and c."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _index_word(count: int) -> str:
    return "index" if count == 1 else "indexes"


def _idx_words(values) -> str:
    return _and([f'<span class="idx-t">{_e(v)}</span>' for v in values])


def _chips(values, selected: bool = False) -> str:
    if not values:
        return '<span class="muted">none</span>'
    cls = "idx sel" if selected else "idx"
    return " ".join(f'<span class="{cls}">{_e(v)}</span>' for v in values)


def _phone(code: object) -> str:
    return f'<span class="ph">{_e(code)}</span>'


def _phones(seq) -> str:
    return f'<span class="ph">{_e(" ".join(seq))}</span>'


def _variant_name(variant: dict) -> str:
    return f'<span class="vid">{_e(variant["id"])}</span>'


def _anchor(prompt: dict) -> str:
    return _e("p-" + prompt["id"])


def _prompt_link(prompt: dict) -> str:
    return f'<a href="#{_anchor(prompt)}">{_e(prompt["word"])} ({_e(prompt["position"])})</a>'


def _humanize(code: object) -> str:
    text = str(code).replace("_", " ")
    return text[:1].upper() + text[1:]


def _selected_union(prompt: dict) -> list[int]:
    return sorted({i for v in prompt["variants"] for i in v["selectedPositionIndexes"]})


def _context_window(phones, index: int) -> str:
    parts = []
    for j in range(max(0, index - 1), min(len(phones), index + 2)):
        if j == index:
            parts.append(f'<span class="hl">{_e(phones[j])}</span>')
        else:
            parts.append(_e(phones[j]))
    return '<span class="ph">' + " ".join(parts) + "</span>"


# Plain-language reviewer questions, built only from the packet's own metadata.


def _q_variant_choice(prompt: dict, siblings: list[dict]) -> str:
    variants = prompt["variants"]
    forms = _and([f"{_variant_name(v)} {_phones(v['phones'])}" for v in variants])
    selections = {tuple(v["selectedPositionIndexes"]) for v in variants}
    same = ""
    if len(selections) == 1:
        only = next(iter(selections))
        if only:
            same = f" The selected-position {_index_word(len(only))} is {_idx_words(only)} in each."
    return (
        f"The dictionary gives {len(variants)} pronunciations of “{_e(prompt['word'])}”: {forms}.{same} "
        "Which of them are acceptable references for the intended variety, and should any be excluded? "
        "All are kept in this packet; none has been chosen."
    )


def _q_repeated_target(prompt: dict, siblings: list[dict]) -> str:
    phone = _phone(prompt["targetPhone"])
    position = _e(prompt["position"])
    lines = []
    has_other = False
    for v in prompt["variants"]:
        all_idx = v["allTargetIndexes"]
        sel = v["selectedPositionIndexes"]
        if len(all_idx) < 2:
            continue
        others = [i for i in all_idx if i not in sel]
        if others:
            has_other = True
            verb = "is another occurrence" if len(others) == 1 else "are other occurrences"
            lines.append(
                f"In {_variant_name(v)}, {phone} appears at indexes {_idx_words(all_idx)}. "
                f"This prompt’s selected-position {_index_word(len(sel))} is {_idx_words(sel)}, so "
                f"{_index_word(len(others))} {_idx_words(others)} {verb} of the same sound."
            )
        else:
            lines.append(
                f"In {_variant_name(v)}, {phone} appears at indexes {_idx_words(all_idx)}, "
                f"and every one of them falls at the {position} position."
            )
    if not lines:
        lines.append(f"The source metadata flags {phone} as appearing more than once in this word.")
    if has_other:
        ask = (
            "Should the other occurrence be set aside when judging this prompt, or does the repeat "
            "make the word unsuitable for this position?"
        )
    else:
        ask = "Is a word with the target sound repeated at the same position suitable for this prompt?"
    text = " ".join(lines) + " " + ask
    if siblings:
        refs = _and(
            [
                f"{_prompt_link(s)}, which selects {_index_word(len(_selected_union(s)))} "
                f"{_idx_words(_selected_union(s))}"
                for s in siblings
            ]
        )
        text += f" The same source word is also used by {refs}. Should every prompt from this word remain in the set?"
    return text


def _q_selected_ambiguous(prompt: dict, siblings: list[dict]) -> str:
    position = _e(prompt["position"])
    lines = []
    for v in prompt["variants"]:
        sel = v["selectedPositionIndexes"]
        if len(sel) > 1:
            quantity = "both" if len(sel) == 2 else "all"
            lines.append(
                f"In {_variant_name(v)}, indexes {_idx_words(sel)} are {quantity} listed as the {position} position."
            )
    if not lines:
        lines.append("The source metadata flags more than one occurrence at the selected position.")
    return (
        " ".join(lines) + " This packet does not pick one. What explicit occurrence rule should apply: "
        "one named index, every listed index, or excluding the word? Until a rule is recorded in the "
        "controlled record, every listed index stays pending."
    )


def _q_source_alias(prompt: dict, siblings: list[dict]) -> str:
    return (
        f"The prompt displays “{_e(prompt['word'])}”, while the source spelling is "
        f"“{_e(prompt['sourceWord'])}” (lexical group <code>{_e(prompt['lexicalGroup'])}</code>). "
        "Confirm which spelling should be displayed, and that both spellings name the same word and picture."
    )


def _q_unsupported(prompt: dict, siblings: list[dict]) -> str:
    return (
        f"{_phone(prompt['targetPhone'])} is outside the current model’s target inventory, so this prompt "
        "has no model target ID. That is an engineering coverage limit only; it does not make "
        f"“{_e(prompt['word'])}” an invalid or unsuitable word. Should the word stay in the content set "
        "while coverage is pending?"
    )


def _q_cluster(prompt: dict, siblings: list[dict]) -> str:
    contexts = []
    for v in prompt["variants"]:
        for i in v["selectedPositionIndexes"]:
            if 0 <= i < len(v["phones"]):
                contexts.append(f"{_variant_name(v)} {_context_window(v['phones'], i)}")
    where = f" (dictionary context: {_and(contexts)})" if contexts else ""
    return (
        f"This prompt is flagged because the selected {_phone(prompt['targetPhone'])} sits inside a "
        f"consonant cluster{where}. Should a target inside a cluster count for the "
        f"{_e(prompt['position'])} position, or would a word where the sound is not next to another "
        "consonant be preferred?"
    )


def _q_reference_variety(prompt: dict, siblings: list[dict]) -> str:
    return (
        "Which variety of English should a reference for this word represent? "
        "The packet scope leaves the reference variety pending."
    )


def _q_professional(prompt: dict, siblings: list[dict]) -> str:
    return (
        "A qualified decision belongs in the existing controlled SLP record. "
        "Nothing in this packet stands in for that review."
    )


_QUESTION_BUILDERS = {
    "variant_choice": _q_variant_choice,
    "repeated_target": _q_repeated_target,
    "selected_occurrence_ambiguous": _q_selected_ambiguous,
    "source_spelling_alias": _q_source_alias,
    "unsupported_target": _q_unsupported,
    "cluster_context": _q_cluster,
    "reference_variety_pending": _q_reference_variety,
    "professional_review_pending": _q_professional,
}


def _question(code: str, prompt: dict, siblings: list[dict]) -> str:
    builder = _QUESTION_BUILDERS.get(code)
    if builder is None:
        return f"Flagged in the source metadata as <code>{_e(code)}</code>."
    return builder(prompt, siblings)


# Page sections.


def _render_masthead(packet: dict) -> str:
    scope = packet["scope"]
    counts = packet["counts"]
    ages = f"{_e(scope['minAge'])}–{_e(scope['maxAge'])}"
    language = _e(_LANGUAGE_LABELS.get(scope["intendedLanguage"], scope["intendedLanguage"]))
    count_items = (
        ("Prompts", counts["prompts"]),
        ("Dictionary variants", counts["variants"]),
        ("All target occurrences", counts["allTargetOccurrences"]),
        ("Selected-position occurrences", counts["selectedPositionOccurrences"]),
        ("Distinct source words", counts["distinctSourceWords"]),
    )
    count_html = "".join(f"<div><dt>{label}</dt><dd>{_e(value)}</dd></div>" for label, value in count_items)
    return f"""<header class="masthead"><div class="wrap">
<p class="eyebrow">Content review preparation · engineering packet</p>
<h1>Content review preparation packet</h1>
<p class="lede">A reading copy of the {_e(counts['prompts'])} pending prompts, prepared for professional content review. It sets out dictionary metadata and the questions a qualified reviewer needs to answer. It records no decisions.</p>
<section class="status-banner" aria-labelledby="status-title">
<h2 id="status-title">All professional review pending</h2>
<ul>
<li>Engineering preparation only, scoped to ages {ages} ({language}; reference variety {_e(scope['referenceVariety'])}).</li>
<li>No reference audio, rights or qualified approval has been verified. This packet contains no audio, no cues and no approvals.</li>
<li>Not for learner feedback, clinical use or production use.</li>
<li>The existing controlled SLP record remains the only approval workflow.</li>
</ul>
</section>
<dl class="counts">{count_html}</dl>
<p class="index-note"><strong>About the indexes.</strong> Every index is a zero-based position in a pronunciation-dictionary phone sequence: the first phone is index 0. Indexes describe dictionary entries, not measured articulation or anything a person said. All {_e(counts['allTargetOccurrences'])} target occurrences are shown, along with the {_e(counts['selectedPositionOccurrences'])} that fall at each prompt’s selected position.</p>
</div></header>"""


def _render_toc(packet: dict) -> str:
    prompts = packet["prompts"]
    sections = (
        ("reading", "How to read this packet"),
        ("questions", "Review questions at a glance"),
        ("checklist", "Pending checklist"),
        ("prompts", "Prompts"),
        ("declarations", "Declarations and validation draft"),
        ("workflow", "Controlled workflow"),
        ("limits", "Claim limits"),
    )
    section_items = "".join(f'<li><a href="#{key}">{label}</a></li>' for key, label in sections)
    prompt_items = "".join(
        f'<li><a href="#{_anchor(p)}"><span class="toc-n">{n:02d}</span>'
        f'<span class="toc-w">{_e(p["word"])}</span>'
        f'<span class="toc-m">{_e(p["targetPhone"])} · {_e(p["position"])}</span></a></li>'
        for n, p in enumerate(prompts, 1)
    )
    return f"""<nav class="toc" id="contents" aria-label="Packet contents">
<p class="toc-title">Contents</p>
<ol>{section_items}</ol>
<p class="toc-title">Prompts</p>
<span class="toc-pending">All {len(prompts)} pending professional review</span>
<ol class="toc-prompts">{prompt_items}</ol>
</nav>"""


def _render_reading(packet: dict) -> str:
    example = packet["prompts"][0]["variants"][0]["phones"]
    example_html = _phones(example)
    first = _phone(example[0])
    return f"""<section id="reading" aria-labelledby="reading-title">
<h2 id="reading-title">How to read this packet</h2>
<p>Each prompt pairs a word with one target sound at one position (beginning, middle or end). Pronunciations come from a pronunciation dictionary and are written as phone codes; for example, {example_html}, where {first} is index 0.</p>
<p><strong>All target indexes</strong> lists every place the target phone appears in a dictionary pronunciation. <strong>Selected-position indexes</strong> is the subset at the prompt’s position. Where a word has more than one pronunciation, or more than one occurrence, every one is kept and none is chosen.</p>
<ul class="legend" aria-label="Legend">
<li><span class="idx">2</span> target occurrence index</li>
<li><span class="idx sel">2</span> selected-position index</li>
<li><span class="badge badge-pending">Pending</span> awaiting professional review</li>
</ul>
</section>"""


def _render_question_summary(packet: dict) -> str:
    prompts = packet["prompts"]
    present: list[str] = []
    for p in prompts:
        for code in p["issues"]:
            if code not in present:
                present.append(code)
    ordered = [c for c in _ISSUE_ORDER if c in present]
    ordered += [c for c in present if c not in _ISSUE_ORDER and c not in _SHARED_ISSUES]
    rows = []
    for code in ordered:
        hits = [p for p in prompts if code in p["issues"]]
        label = _e(_ISSUE_LABELS.get(code, _humanize(code)))
        summary = _e(_ISSUE_SUMMARIES.get(code, "Flagged in the source metadata."))
        links = ", ".join(_prompt_link(p) for p in hits)
        rows.append(f'<div><dt>{label}</dt><dd><p>{summary}</p><p class="qs-links">{links}</p></dd></div>')
    for code in _SHARED_ISSUES:
        hits = [p for p in prompts if code in p["issues"]]
        if not hits:
            continue
        label = _e(_ISSUE_LABELS[code])
        summary = _e(_ISSUE_SUMMARIES[code])
        rows.append(
            f'<div><dt>{label}</dt><dd><p>{summary}</p>'
            f'<p class="muted">Pending for {len(hits)} of {len(prompts)} prompts.</p></dd></div>'
        )
    return f"""<section id="questions" aria-labelledby="questions-title">
<h2 id="questions-title">Review questions at a glance</h2>
<p>Questions come only from flags in the source metadata. Each prompt section below asks them in full, using that prompt’s own phones and indexes.</p>
<dl class="qs">{''.join(rows)}</dl>
</section>"""


def _grouped_requirements(codes: list[str]) -> list[tuple[str, list[str]]]:
    groups = []
    known = set()
    for title, members in _REQUIREMENT_GROUPS:
        known.update(members)
        hits = [c for c in members if c in codes]
        if hits:
            groups.append((title, hits))
    extra = [c for c in codes if c not in known]
    if extra:
        groups.append(("Other", extra))
    return groups


def _render_checklist_overview(packet: dict) -> str:
    prompts = packet["prompts"]
    codes: list[str] = []
    for p in prompts:
        for code in p["requirements"]:
            if code not in codes:
                codes.append(code)
    blocks = []
    for title, members in _grouped_requirements(codes):
        items = []
        for code in members:
            label, description = _REQUIREMENTS.get(code, (_humanize(code), ""))
            n = sum(1 for p in prompts if code in p["requirements"])
            items.append(
                f"<li><strong>{_e(label)}</strong><span>{_e(description)}</span>"
                f'<span class="pend">Pending · {n} of {len(prompts)} prompts</span></li>'
            )
        blocks.append(f"<div><h5>{_e(title)}</h5><ul>{''.join(items)}</ul></div>")
    return f"""<section id="checklist" aria-labelledby="checklist-title">
<h2 id="checklist-title">Pending checklist</h2>
<p>The packet supplies the same {len(codes)} requirements for every prompt. None has been met. Each is answered by a qualified reviewer through the existing controlled SLP record, not in this packet.</p>
<div class="req-groups">{''.join(blocks)}</div>
</section>"""


def _render_variant(prompt: dict, variant: dict) -> str:
    phones = variant["phones"]
    all_idx = variant["allTargetIndexes"]
    sel_idx = variant["selectedPositionIndexes"]
    yes_t = '<td class="mk mk-t"><span aria-hidden="true">●</span><span class="vh">yes</span></td>'
    yes_s = '<td class="mk mk-s"><span aria-hidden="true">●</span><span class="vh">yes</span></td>'
    no = '<td class="mk mk-no"><span aria-hidden="true">·</span><span class="vh">no</span></td>'
    idx_cells, phone_cells, target_cells, selected_cells = [], [], [], []
    for i, ph in enumerate(phones):
        classes = []
        if i in all_idx:
            classes.append("is-target")
        if i in sel_idx:
            classes.append("is-selected")
        class_attr = f' class="{" ".join(classes)}"' if classes else ""
        idx_cells.append(f"<td>{i}</td>")
        phone_cells.append(f"<td{class_attr}>{_e(ph)}</td>")
        target_cells.append(yes_t if i in all_idx else no)
        selected_cells.append(yes_s if i in sel_idx else no)
    label = _e(f"Dictionary phones for {prompt['word']} {variant['id']}, with zero-based indexes")
    table = (
        f'<div class="table-wrap"><table class="phones" aria-label="{label}"><tbody>'
        f'<tr class="r-idx"><th scope="row">Index</th>{"".join(idx_cells)}</tr>'
        f'<tr class="r-ph"><th scope="row">Phone</th>{"".join(phone_cells)}</tr>'
        f'<tr><th scope="row">Target occurrence</th>{"".join(target_cells)}</tr>'
        f'<tr><th scope="row">Selected position</th>{"".join(selected_cells)}</tr>'
        "</tbody></table></div>"
    )
    lines = (
        f'<p class="idx-line"><span>All target indexes {_chips(all_idx)}</span>'
        f"<span>Selected-position indexes {_chips(sel_idx, selected=True)}</span></p>"
    )
    if len(sel_idx) > 1:
        quantity, chosen = ("both", "Neither") if len(sel_idx) == 2 else ("all", "None")
        lines += (
            f'<p class="note">Indexes {_idx_words(sel_idx)} are {quantity} listed as selected positions. '
            f"{chosen} is chosen here; an explicit occurrence rule is pending.</p>"
        )
    return (
        f"<figure class=\"variant\"><figcaption>{_variant_name(variant)} {_phones(phones)} "
        f'<span class="muted">· {len(phones)} phones</span></figcaption>{table}{lines}</figure>'
    )


def _render_prompt(number: int, total: int, prompt: dict, groups: dict) -> str:
    siblings = [q for q in groups[prompt["lexicalGroup"]] if q["id"] != prompt["id"]]
    anchor = _anchor(prompt)

    if prompt["word"] != prompt["sourceWord"]:
        source = f'“{_e(prompt["sourceWord"])}” <span class="badge badge-info">differs from display</span>'
    else:
        source = f'“{_e(prompt["sourceWord"])}” <span class="muted">(same as displayed)</span>'
    lexical = f"<code>{_e(prompt['lexicalGroup'])}</code>"
    if siblings:
        lexical += " · also " + ", ".join(_prompt_link(s) for s in siblings)
    if prompt["modelInventorySupported"]:
        inventory = f"Supported · target ID <code>{_e(prompt['modelTargetId'])}</code>"
    else:
        inventory = "Not in current inventory · no target ID"
    facts = (
        ("Prompt ID", f"<code>{_e(prompt['id'])}</code>"),
        ("Target phone", _phone(prompt["targetPhone"])),
        ("Position", _e(_POSITION_LABELS.get(prompt["position"], prompt["position"]))),
        ("Source spelling", source),
        ("Lexical group", lexical),
        ("Model inventory", inventory),
    )
    facts_html = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts)

    variants = prompt["variants"]
    noun = "pronunciation" if len(variants) == 1 else "pronunciations"
    variants_html = "".join(_render_variant(prompt, v) for v in variants)

    targeted = [c for c in prompt["issues"] if c not in _SHARED_ISSUES]
    shared = [c for c in prompt["issues"] if c in _SHARED_ISSUES]
    if targeted:
        items = "".join(
            f'<li><span class="q-label">{_e(_ISSUE_LABELS.get(c, _humanize(c)))}</span>'
            f"{_question(c, prompt, siblings)}</li>"
            for c in targeted
        )
        questions = f'<ul class="questions">{items}</ul>'
    else:
        questions = (
            '<p class="muted">No prompt-specific questions are flagged in the source metadata. '
            "The shared pending items below still apply.</p>"
        )
    if shared:
        tags = " ".join(f'<span class="tag">{_e(_ISSUE_LABELS.get(c, _humanize(c)))}</span>' for c in shared)
        questions += f'<p class="shared">Also pending, as for every prompt: {tags}</p>'

    checklist = []
    for title, members in _grouped_requirements(prompt["requirements"]):
        items = "".join(
            f'<li><span class="box" aria-hidden="true"></span>'
            f"{_e(_REQUIREMENTS.get(c, (_humanize(c), ''))[0])}"
            f'<span class="pend">Pending</span></li>'
            for c in members
        )
        checklist.append(f"<div><h5>{_e(title)}</h5><ul>{items}</ul></div>")

    status = "Professional review pending" if prompt["status"] == "pending" else _humanize(prompt["status"])
    return f"""<article class="prompt" id="{anchor}" aria-labelledby="{anchor}-title">
<div class="prompt-head">
<h3 id="{anchor}-title"><span class="prompt-num">Prompt {number} of {total}</span>{_e(prompt['word'])}</h3>
<span class="badge badge-pending">{_e(status)}</span>
</div>
<dl class="facts">{facts_html}</dl>
<h4>Dictionary {noun} · {len(variants)} retained</h4>
{variants_html}
<h4>Questions for the reviewer</h4>
{questions}
<h4>Pending requirements · {len(prompt['requirements'])}</h4>
<div class="checklist">{''.join(checklist)}</div>
<a class="back" href="#contents">Back to contents</a>
</article>"""


def _render_prompts(packet: dict) -> str:
    prompts = packet["prompts"]
    groups: dict[str, list[dict]] = {}
    for p in prompts:
        groups.setdefault(p["lexicalGroup"], []).append(p)
    articles = "".join(_render_prompt(n, len(prompts), p, groups) for n, p in enumerate(prompts, 1))
    return f"""<section id="prompts" aria-labelledby="prompts-title">
<h2 id="prompts-title">Prompts</h2>
<p>{len(prompts)} prompts, each pending professional review. Every dictionary pronunciation, every target index and every selected-position index from the packet is shown.</p>
{articles}
</section>"""


def _render_declarations() -> str:
    return """<section id="declarations" aria-labelledby="declarations-title">
<h2 id="declarations-title">Declarations and validation draft</h2>
<div class="callout">
<p><strong>Declarations are descriptions, not verification.</strong> The declarations file holds what a person states for each checklist field, including reference provenance, rights and scope. Filling a field in does not establish anyone’s identity or qualification, does not verify rights or permissions, and does not check any audio, image or other media. This packet contains no media.</p>
<p>A fully completed set of declarations, including an invented practice exercise, is still not an approval. Every claim limit stays at “No”.</p>
</div>
<h3>Prospective validation draft <span class="draft-flag">Not final · not collected</span></h3>
<p>The validation draft is a planning template only. Before any accuracy claim could be considered, it would need:</p>
<ul>
<li>an independent reference judgement for each item, separate from the system being evaluated;</li>
<li>every attempt counted, including incomplete, rejected and retried attempts, so the denominator covers all attempt outcomes;</li>
<li>declared participant, household and lexical-group linkage, with any inseparable joint groups and split infeasibility reported before evaluation;</li>
<li>repeats, retries and recording conditions documented;</li>
<li>evidence about false corrections: cases where a correct production would be flagged as wrong.</li>
</ul>
<p>Sample sizes, acceptance thresholds, reviewed references, identity, use permission and retention durations are all left empty and pending. No criteria carry over from earlier /r/ work.</p>
</section>"""


def _render_workflow(packet: dict) -> str:
    workflow = packet["controlledWorkflow"]
    rows = []
    shown = set()
    for key, label in _WORKFLOW_LABELS:
        if key in workflow:
            shown.add(key)
            rows.append(f"<dt>{label}</dt><dd><code>{_e(workflow[key])}</code></dd>")
    for key, value in workflow.items():
        if key in shown or key == "meaning":
            continue
        rows.append(f"<dt>{_e(_humanize(key))}</dt><dd><code>{_e(value)}</code></dd>")
    meaning = workflow.get("meaning", "")
    meaning_html = f'<p class="muted">{_e(meaning)}.</p>' if meaning else ""
    return f"""<section id="workflow" aria-labelledby="workflow-title">
<h2 id="workflow-title">Controlled workflow</h2>
<p>Professional decisions are recorded only through the existing controlled SLP record. This packet is a preparation addendum to it, not a parallel approval route.</p>
{meaning_html}
<dl class="paths">{''.join(rows)}</dl>
<p class="muted">These are repository paths, relative to the repository root. Open them from a checkout of the repository; they are not links from this page.</p>
</section>"""


def _render_limits(packet: dict) -> str:
    rows = []
    for key, value in packet["claimLimits"].items():
        if value is not False:
            raise ValueError("claim limit is not false")
        label = _CLAIM_LABELS.get(key, _humanize(key))
        rows.append(f'<tr><th scope="row">{_e(label)}</th><td>No · not established</td></tr>')
    return f"""<section id="limits" aria-labelledby="limits-title">
<h2 id="limits-title">Claim limits</h2>
<p>These limits are fixed for this packet and do not change when declarations are completed.</p>
<table class="limits"><thead><tr><th scope="col">Claim</th><th scope="col">Status</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</section>"""


def _render_footer(packet: dict) -> str:
    tech = (
        ("Schema version", packet["schemaVersion"]),
        ("Packet kind", packet["kind"]),
        ("Project ID", packet["projectId"]),
        ("Packet status", packet["status"]),
        ("Use", packet["scope"]["use"]),
        ("Source pack SHA-256", packet["sourcePackSha256"]),
        ("Source manifest SHA-256", packet["sourceManifestSha256"]),
    )
    rows = "".join(f"<dt>{label}</dt><dd>{_e(value)}</dd>" for label, value in tech)
    return f"""<footer class="site-foot">
<p>All professional review pending · engineering preparation only · not for learner, clinical or production use.</p>
<p>Technical identifiers. Rendered deterministically from the pinned pack; no timestamp is recorded.</p>
<dl class="tech">{rows}</dl>
</footer>"""


def render_packet(packet: dict) -> str:
    """Validate a compiled packet and return a self-contained static HTML page."""
    validate_packet(packet)

    body = "".join(
        (
            _render_reading(packet),
            _render_question_summary(packet),
            _render_checklist_overview(packet),
            _render_prompts(packet),
            _render_declarations(),
            _render_workflow(packet),
            _render_limits(packet),
            _render_footer(packet),
        )
    )
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'none'; base-uri 'none'">
<meta name="referrer" content="no-referrer">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light">
<title>Content review preparation packet · all professional review pending</title>
<style>{_CSS}</style>
</head>
<body>
<a class="skip" href="#main">Skip to main content</a>
{_render_masthead(packet)}
<div class="wrap layout">
{_render_toc(packet)}
<main id="main" tabindex="-1">
{body}
</main>
</div>
</body>
</html>
"""
    # ASCII-only output: non-ASCII copy becomes numeric character references.
    return document.encode("ascii", "xmlcharrefreplace").decode("ascii")
