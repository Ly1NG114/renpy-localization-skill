# Adult Ren'Py Localization Quality Guide

## Contents

1. [Set the translation contract](#set-the-translation-contract)
2. [Build an explicit glossary](#build-an-explicit-glossary)
3. [Preserve character voice and scene function](#preserve-character-voice-and-scene-function)
4. [Handle sexual sound effects and mechanics](#handle-sexual-sound-effects-and-mechanics)
5. [Use machine translation without flattening the game](#use-machine-translation-without-flattening-the-game)
6. [Validate context and syntax](#validate-context-and-syntax)

## Set the translation contract

Translate the adult content as authored unless the user requests a different rating or tone. Do not silently censor, euphemize, moralize, or intensify it.

Preserve distinctions that affect plot or mechanics:

- consensual, coerced, deceptive, dream, loss-state, and game-over framing;
- human, disguised, transformed, possessed, ghost, demon, succubus, and other state-dependent identities;
- threat, teasing, comedy, humiliation, affection, fear, and seduction;
- narration versus the protagonist's internal thoughts;
- optional gallery/replay text versus canonical route text.

Use natural target-language phrasing while retaining the source's explicitness and emotional function.

## Build an explicit glossary

Record before bulk translation:

- character names, aliases, titles, pronouns, and forms;
- relationships and power dynamics;
- anatomy and sexual-action terms at the requested explicitness;
- recurring gameplay meters, resources, status effects, and failure terms;
- creature/species vocabulary;
- costume/fetish terminology;
- catchphrases, verbal tics, honorifics, accents, and deliberate grammar quirks;
- onomatopoeia and nonverbal utterance conventions.

Tie glossary entries to context when one English word requires different translations. For example, “come” as movement, invitation, or orgasm must not share a blind global replacement.

Keep names and route vocabulary consistent between dialogue, UI, gallery labels, save metadata, and tutorials.

## Preserve character voice and scene function

Review dialogue in local context, not alphabetic/string order. Read the speaker, previous lines, route conditions, current form, and next action.

Preserve:

- sentence length and rhythm during timed animation;
- hesitation, breath, interruptions, stutters, and escalating intensity;
- whether a line is spoken, narrated, thought, whispered, or displayed as a gameplay prompt;
- jokes, wordplay, taunts, and unreliable narration;
- deliberate repetition synchronized with loops or clicks.

Do not give every character the same polished register. A formal priestess, playful ghost, panicked protagonist, and terse monster should remain distinguishable in Chinese.

Avoid adding explanatory text that the source leaves ambiguous. Route clues and identity reveals often depend on controlled ambiguity.

## Handle sexual sound effects and mechanics

Treat quoted moans, gasps, laughter, and action sounds as text with a style system rather than random transliteration.

Define conventions for:

- moans and breath (`啊`, `嗯`, `哈`, etc.);
- wet/slurp/lick sounds;
- impact/slap sounds;
- climax/cut-off punctuation;
- repeated sounds during animation loops.

Keep `{w}`, `{p}`, `{nw}`, CPS, color, size, and other Ren'Py tags exact. These tags may synchronize dialogue to erotic animation or QTE timing.

Do not translate media filenames, channel names, labels, image identifiers, or mechanic variables merely because their English/Japanese names are explicit. Translate only user-visible text.

When an explicit scene references a missing audio file, choose any fallback by scene function (lick, impact, climax, UI jingle), not by extension alone. A technically loadable but semantically wrong sound is still a localization defect.

## Use machine translation without flattening the game

Use machine translation for scale, then perform targeted contextual repair.

Separate passes:

1. protect syntax and extract strings;
2. translate in batches with glossary constraints;
3. cache by exact source plus relevant context/version;
4. validate placeholders and tags;
5. review names, choices, explicit scenes, jokes, tutorials, and route clues in context;
6. repair repeated/systematic errors through the cache or exact overrides;
7. compile and inspect on device.

Low model-token usage does not imply little work. Local inference, cache reuse, compilation, APK transfer, media processing, and device QA can consume wall time without many assistant tokens.

Do not repeatedly translate unchanged strings. Preserve a deterministic cache and record manual overrides separately so later builds do not regress reviewed lines.

## Validate context and syntax

Require exact equality for:

- interpolation variable names and counts;
- Ren'Py text tags and nesting;
- escaped braces, percent tokens, and line-control markers;
- translate block identifiers and control flow;
- label, image, screen, persistent, and Python identifiers.

Sample every risk category, not only random dialogue:

- opening narration and named conversation;
- first choice and first tutorial;
- one explicit consensual scene and one loss/game-over scene when present;
- identity/form-dependent lines;
- long descriptions and rapid timed lines;
- gallery/replay captions;
- dynamic UI, meters, notifications, and save notes;
- prior user-reported mistranslations.

Inspect on a phone-sized screen for wrapping, punctuation, outline contrast, name-box width, and rare glyphs. A syntactically correct translation can still be unreadable or mistimed.

Report intentional untranslated content precisely: invented language, codes, logos, baked raster/video text, proper nouns, or user-approved English. Do not hide omissions behind “mostly localized.”
