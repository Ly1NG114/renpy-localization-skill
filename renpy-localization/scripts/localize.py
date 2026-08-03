# -*- coding: utf-8 -*-
"""
Ren'Py localization pipeline (PC-first, Android-compatible).

Subcommands:
  extract   - parse an engine-generated tl/<lang>/ skeleton into work/records.json + unique.json
  translate - bulk-translate unique strings via an OpenAI-compatible API (deterministic memory)
  polish    - second-pass native-proofreader polish of all translations
  validate  - 4-way checks: tags / interpolations / backslash escapes / glossary terms
  repair    - policy-driven fixes (glossary alternatives, tags, interpolations, newlines)
  apply     - rebuild tl/<lang>/*.rpy from memory
  names     - localize Character(...) display names in game .rpy files (with backup)

Consistency guarantees:
  * deterministic memory: same source string -> same translation, always
  * glossary terms injected into every prompt and validated afterwards
  * same-source deduplication: repeated lines are translated once

Environment:
  RENPY_GAME_DIR  - game root (folder containing game/, renpy/, lib/)
  DEEPSEEK_API_KEY (or --api-key)

Examples:
  python localize.py extract --lang chinese
  python localize.py translate --lang chinese --workers 4 --batch 150 --model deepseek-v4-flash
  python localize.py polish   --lang chinese --workers 4
  python localize.py validate --lang chinese
  python localize.py repair   --lang chinese
  python localize.py apply    --lang chinese
  python localize.py names
"""
import os, re, json, ssl, time, sys, threading, io, glob, shutil, collections, argparse, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.environ.get('RENPY_GAME_DIR', '')
WORK = os.path.join(ROOT, 'work')

# Tolerate local MITM / SSL-inspection proxies (common in CN networks).
CTX = ssl._create_unverified_context()

TAG_RE = re.compile(r'\{[^{}]*\}')
INT_RE = re.compile(r'\[[^\[\]]*\]')
BS_RE = re.compile(r'\\[^\\]')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
_JSONDEC = json.JSONDecoder()

def tl_dir(lang):
    return os.path.join(GAME_DIR, 'game', 'tl', lang)

def memory_path(lang):
    return os.path.join(WORK, 'memory_%s.json' % lang)

def records_path(lang):
    return os.path.join(WORK, 'records_%s.json' % lang)

def unique_path(lang):
    return os.path.join(WORK, 'unique_%s.json' % lang)

def glossary_path():
    return os.path.join(ROOT, 'glossary.json')

def load_glossary():
    p = glossary_path()
    if not os.path.exists(p):
        return {'entries': [], 'policies': {}}
    with io.open(p, encoding='utf-8') as f:
        return json.load(f)

def load_memory(lang):
    p = memory_path(lang)
    if os.path.exists(p):
        with io.open(p, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_memory(lang, memory):
    p = memory_path(lang)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=0)
    os.replace(tmp, p)

def api_key(args):
    return args.api_key or os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY') or ''

# ---------------------------------------------------------------------------
# JSON extraction
# LESSON: never hand-roll bracket counting. Translations legitimately contain
# [mc], [x] etc. inside string values, which break naive depth tracking.
# Use json.JSONDecoder.raw_decode at the first '[' or '{'.
# ---------------------------------------------------------------------------
def extract_json(content):
    content = content.strip()
    if content.startswith('```'):
        content = re.sub(r'^```[a-zA-Z]*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
    for ch in ('[', '{'):
        pos = content.find(ch)
        if pos < 0:
            continue
        try:
            obj, _ = _JSONDEC.raw_decode(content, pos)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, list):
                        return v
        except Exception:
            continue
    return None

def post_json(args, payload, timeout=420):
    req = urllib.request.Request(
        args.api_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + api_key(args), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def build_speaker_map():
    m = {}
    game = os.path.join(GAME_DIR, 'game')
    if not os.path.isdir(game):
        return m
    for fn in os.listdir(game):
        if not fn.endswith('.rpy'):
            continue
        try:
            with io.open(os.path.join(game, fn), encoding='utf-8') as f:
                txt = f.read()
        except Exception:
            continue
        for mm in re.finditer(r"define\s+(\w+)\s*=\s*(?:Dynamic)?Character\(\s*['\"]([^'\"]+)['\"]", txt):
            m[mm.group(1)] = mm.group(2)
    return m

# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------
def cmd_extract(args):
    lang = args.lang
    tl = tl_dir(lang)
    if not os.path.isdir(tl):
        sys.exit('tl dir not found: %s (run the game engine "translate %s" first)' % (tl, lang))
    BLOCK_RE = re.compile(r'^translate %s ([^:\n]+):\n((?:.*\n)*?)(?=^translate |\Z)' % re.escape(lang), re.M)
    STR_RE = re.compile(r'^    old "((?:[^"\\]|\\.)*)"\n    new "((?:[^"\\]|\\.)*)"', re.M)
    SAY_RE = re.compile(r'^\s*(?:(\w+(?:\.\w+)*)\s+)?("(?:[^"\\]|\\.)*")(.*)$')
    records, string_records = [], []
    for fn in sorted(glob.glob(os.path.join(tl, '*.rpy'))):
        base = os.path.basename(fn)
        with io.open(fn, encoding='utf-8-sig') as f:
            txt = f.read()
        for m in BLOCK_RE.finditer(txt):
            tid = m.group(1)
            body = m.group(2)
            if tid == 'strings':
                for sm in STR_RE.finditer(body):
                    pre = body[:sm.start()]
                    cm = re.findall(r'# ([^\n]+)', pre)
                    string_records.append({'kind': 'string', 'file': base, 'id': tid,
                                           'en': sm.group(1), 'zh': sm.group(2),
                                           'comment': cm[-1].strip() if cm else ''})
                continue
            stmt_line = None
            for ln in body.splitlines():
                s = ln.strip()
                if not s or s.startswith('#'):
                    continue
                stmt_line = s
                break
            if stmt_line is None:
                continue
            sm = SAY_RE.match(stmt_line)
            if not sm:
                print('WARN unparseable block', base, tid, repr(stmt_line[:120]))
                continue
            records.append({'kind': 'dialogue', 'file': base, 'id': tid,
                            'speaker': sm.group(1) or '', 'en': sm.group(2)[1:-1],
                            'tail': sm.group(3), 'comment': ''})
    uniq = {}
    for r in records + string_records:
        key = r['en']
        u = uniq.setdefault(key, {'en': key, 'dialogue': 0, 'strings': 0, 'speakers': [], 'files': []})
        if r['kind'] == 'dialogue':
            u['dialogue'] += 1
            if r['speaker'] and r['speaker'] not in u['speakers']:
                u['speakers'].append(r['speaker'])
        else:
            u['strings'] += 1
        if r['file'] not in u['files']:
            u['files'].append(r['file'])
    os.makedirs(WORK, exist_ok=True)
    with io.open(records_path(lang), 'w', encoding='utf-8') as f:
        json.dump({'dialogue': records, 'strings': string_records}, f, ensure_ascii=False, indent=1)
    with io.open(unique_path(lang), 'w', encoding='utf-8') as f:
        json.dump(list(uniq.values()), f, ensure_ascii=False, indent=1)
    print('dialogue records:', len(records), '| string records:', len(string_records), '| unique:', len(uniq))

# ---------------------------------------------------------------------------
# translate / polish shared engine
# ---------------------------------------------------------------------------
PROMPT_TRANSLATE = """你是资深视觉小说汉化译者，正在汉化成人向 Ren'Py 游戏。把英文台词翻译成简体中文。

【硬性规则】
1. 术语表（强制遵守，专有名词必须用下表译文，全文保持一致）：
{glossary}
2. 术语表之外的人名/地名按常见音译处理，并保持全文一致。
3. 保留所有 Ren'Py 标签原样：{{color=...}}{{/color}}、{{b}}{{/b}}、{{i}}{{/i}}、{{font=...}}{{/font}}、{{size=...}}{{/size}}、{{w}}、{{p}}、{{nw}}、{{image=...}}、{{alpha=...}} 等，不得增删改。
4. 保留所有反斜杠转义序列原样：\\"、\\\\、\\{{、\\n 等，不得增删改。
5. 保留所有插值变量 [name]、[mc]、[lastname] 等原样；保留 % 百分号标记。
6. 保留星号动作描写 *Laughs*（译为中文动作如 *笑*，星号保留）、括号内心独白（…）的括号、省略号与破折号。
7. 口语自然，符合角色语气与性别；脏话保留同等力度，不净化也不加重；成人内容按原文尺度直译。
8. 不添加原文没有的信息、不解释、不意译过度；保持原文的停顿节奏与句长。
9. 只输出严格 JSON 数组，每项为 {{"id":"...","zh":"..."}}，id 必须原样返回，zh 为译文。输出对象只允许 id 和 zh 两个键，禁止输出 text、speaker 等其它键。不要输出任何其他文字。"""

PROMPT_POLISH = """你是中文母语校对编辑，负责润色成人向 Ren'Py 游戏的汉化文本。下面给出每条台词的英文原文与现有中文译文，请输出【改进后的中文译文】。

【校对标准】
1. 修正语病、错别字、翻译腔、生硬直译、欧化长句；让表达自然口语化，符合说话人身份语气。
2. 原文流畅的译文保持原样，不要为了改而改；不要改变原意、信息量、语气强弱与成人内容尺度。
3. 术语表（强制遵守，专有名词必须用下表译文）：
{glossary}
4. 不得增删改任何 Ren'Py 标签、反斜杠转义、插值变量、% 标记。
5. 保留星号动作描写（*笑*）、括号、省略号、破折号的原有形式。
6. 只输出严格 JSON 数组，每项为 {{"id":"...","zh":"..."}}，id 必须原样返回。输出对象只允许 id 和 zh 两个键。不要输出任何其他文字。"""

def prompt_for(args, glossary_lines, mode):
    tmpl = PROMPT_TRANSLATE if mode == 'translate' else PROMPT_POLISH
    return tmpl.format(glossary=glossary_lines)

def run_batch_api(args, items, glossary_lines, speaker_map, mode, thinking):
    """items: [{'id','en','zh'(polish),'speakers'}] -> {id: zh}. Fills gaps internally."""
    sys_prompt = prompt_for(args, glossary_lines, mode)
    pending = list(items)
    result = {}
    for attempt in range(4):
        if not pending:
            break
        lines = []
        for it in pending:
            sp = it.get('speakers') or ['']
            names = [speaker_map.get(s, s) or '旁白' for s in sp[:2]]
            tag = '（说话人：' + '、'.join(names) + '）' if names else ''
            if mode == 'translate':
                lines.append(json.dumps({'id': it['id'], 'text': it['en'], 'speaker': tag}, ensure_ascii=False))
            else:
                lines.append(json.dumps({'id': it['id'], 'en': it['en'], 'zh': it['zh'], 'speaker': tag}, ensure_ascii=False))
        if mode == 'translate':
            user_content = ('翻译以下 %d 条游戏台词（JSON 数组）：\n[\n%s\n]\n输出格式：[{"id":"...","zh":"..."}]'
                            % (len(pending), ',\n'.join(lines)))
        else:
            user_content = ('请校对润色以下 %d 条台词（JSON 数组，含英文原文 en 与现有译文 zh）：\n[\n%s\n]\n输出格式：[{"id":"...","zh":"改进后的译文"}]'
                            % (len(pending), ',\n'.join(lines)))
        body = {
            'model': args.model,
            'messages': [{'role': 'system', 'content': sys_prompt},
                         {'role': 'user', 'content': user_content}],
            'temperature': 0.4,
            'max_tokens': 20000 if thinking else 16000,
            'thinking': {'type': 'enabled' if thinking else 'disabled'},
        }
        resp = post_json(args, body)
        msg = resp['choices'][0]['message']
        content = msg.get('content') or ''
        parsed = extract_json(content)
        if parsed is None:
            time.sleep(2 + attempt * 3)
            continue
        got = {}
        # LESSON: models sometimes echo the input shape ({id,text}) instead of
        # {id,zh} - accept both keys.
        for item in parsed:
            if isinstance(item, dict) and 'id' in item:
                zh = item.get('zh') or item.get('text')
                if isinstance(zh, str) and zh.strip():
                    got[str(item['id'])] = zh
        for it in pending:
            if it['id'] in got and got[it['id']].strip():
                result[it['id']] = got[it['id']]
        missing = [it for it in pending if it['id'] not in result]
        if missing:
            # LESSON: output truncation at max_tokens drops tail items -> re-request only gaps
            pending = missing
            time.sleep(1 + attempt)
            continue
        break
    if len(result) < len(items):
        raise ValueError('gave up on %d/%d items' % (len(items) - len(result), len(items)))
    return result

def build_batches(todo, batch_size, char_cap=14000):
    batches, cur, cur_chars = [], [], 0
    for u in todo:
        L = len(u['en']) + len(u.get('zh', ''))
        if cur and (len(cur) >= batch_size or cur_chars + L > char_cap):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(u)
        cur_chars += L
    if cur:
        batches.append(cur)
    return batches

def cmd_translate(args):
    lang = args.lang
    if not os.path.exists(unique_path(lang)):
        sys.exit('run extract first')
    with io.open(unique_path(lang), encoding='utf-8') as f:
        uniq = json.load(f)
    memory = load_memory(lang)
    g = load_glossary()
    speaker_map = build_speaker_map()
    glossary_lines = '\n'.join(e['en'] + '=' + e['zh'] for e in g['entries'])

    todo, skipped = [], 0
    for u in uniq:
        en = u['en']
        if en in memory:
            continue
        # identity strings: already CJK, or no latin letters -> skip API entirely
        if CJK_RE.search(en) or not re.search(r'[A-Za-z]', en):
            memory[en] = en
            skipped += 1
            continue
        todo.append(u)
    print('to_translate=%d identity_skip=%d cached=%d' % (len(todo), skipped, len(memory) - skipped))
    if not todo:
        save_memory(lang, memory)
        return

    mem_lock = threading.Lock()
    next_idx, nlock, failed, done = [0], threading.Lock(), [], [0]

    def run_round(batches):
        def worker():
            while True:
                with nlock:
                    i = next_idx[0]; next_idx[0] += 1
                if i >= len(batches):
                    return
                batch = batches[i]
                items = [{'id': str(j), 'en': u['en'], 'speakers': u.get('speakers', [])}
                         for j, u in enumerate(batch)]
                try:
                    res = run_batch_api(args, items, glossary_lines, speaker_map, 'translate', args.thinking)
                    with mem_lock:
                        for j, u in enumerate(batch):
                            zh = res.get(str(j))
                            if zh:
                                memory[u['en']] = zh
                        save_memory(lang, memory)
                        done[0] += 1
                        if done[0] % 10 == 0:
                            print('[progress] %d/%d cached=%d' % (done[0], len(batches), len(memory)), flush=True)
                except Exception as e:
                    with nlock:
                        failed.append({'batch': i, 'error': str(e)[:200]})
                    print('[FAIL] batch %d: %s' % (i, str(e)[:150]), flush=True)
        threads = [threading.Thread(target=worker) for _ in range(max(1, args.workers))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    batches = build_batches(todo, args.batch)
    run_round(batches)
    # residual rounds: failed/partial batches are retried until done (max 6)
    for rnd in range(6):
        remaining = [u for u in todo if u['en'] not in memory]
        if not remaining:
            break
        print('residual round %d: %d strings' % (rnd + 1, len(remaining)))
        next_idx[0] = 0
        run_round(build_batches(remaining, args.batch))
    save_memory(lang, memory)
    print('translate done. cached=%d failed_batches=%d' % (len(memory), len(failed)))

def cmd_polish(args):
    lang = args.lang
    with io.open(unique_path(lang), encoding='utf-8') as f:
        uniq = json.load(f)
    if args.only_en_file:
        with io.open(args.only_en_file, encoding='utf-8') as f:
            keep = set(l.rstrip('\n') for l in f if l.strip())
        uniq = [u for u in uniq if u['en'] in keep]
    memory = load_memory(lang)
    g = load_glossary()
    speaker_map = build_speaker_map()
    glossary_lines = '\n'.join(e['en'] + '=' + e['zh'] for e in g['entries'])

    todo = []
    for u in uniq:
        en = u['en']
        zh = memory.get(en)
        if zh is None or zh == en:
            continue
        # thinking pass for long / tagged / early-story lines, fast pass for the rest
        thinking = (len(en) >= 81 or bool(TAG_RE.search(en)) or
                    any(f in args.think_files for f in u.get('files', [])))
        todo.append({'id': str(len(todo)), 'en': en, 'zh': zh,
                     'speakers': u.get('speakers', []), 'thinking': thinking})
    print('polish candidates:', len(todo))
    if not todo:
        return
    batches = []
    for think in (True, False):
        batches.extend(build_batches([t for t in todo if t['thinking'] == think],
                                     100 if think else args.batch, 16000))
    mem_lock = threading.Lock()
    next_idx, nlock, failed, done = [0], threading.Lock(), [], [0]

    def worker():
        while True:
            with nlock:
                i = next_idx[0]; next_idx[0] += 1
            if i >= len(batches):
                return
            batch = batches[i]
            think = batch[0]['thinking']
            try:
                res = run_batch_api(args, batch, glossary_lines, speaker_map, 'polish', think)
                with mem_lock:
                    for it in batch:
                        zh = res.get(it['id'])
                        if zh and zh != it['zh']:
                            memory[it['en']] = zh
                    save_memory(lang, memory)
                    done[0] += 1
                    if done[0] % 10 == 0:
                        print('[progress] %d/%d cached=%d' % (done[0], len(batches), len(memory)), flush=True)
            except Exception as e:
                with nlock:
                    failed.append({'batch': i, 'error': str(e)[:200]})
                print('[FAIL] batch %d: %s' % (i, str(e)[:150]), flush=True)

    threads = [threading.Thread(target=worker) for _ in range(max(1, args.workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    save_memory(lang, memory)
    print('polish done. failed_batches=%d' % len(failed))

# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------
def cmd_validate(args):
    lang = args.lang
    with io.open(records_path(lang), encoding='utf-8') as f:
        recs = json.load(f)
    memory = load_memory(lang)
    g = load_glossary()
    all_recs = recs['dialogue'] + recs['strings']
    tag_bad, int_bad, bs_bad, gloss_bad, no_zh = [], [], [], [], []

    for r in all_recs:
        en = r['en']
        zh = memory.get(en)
        if zh is None or not zh.strip():
            if en == '':
                continue
            no_zh.append((r['file'], r['id'], en[:80]))
            continue
        if zh == en:
            continue
        # LESSON: compare tag/interp/backslash token multisets, not raw strings
        if collections.Counter(TAG_RE.findall(en)) != collections.Counter(TAG_RE.findall(zh)):
            tag_bad.append((r['file'], r['id'], en[:120], zh[:120]))
        if collections.Counter(INT_RE.findall(en)) != collections.Counter(INT_RE.findall(zh)):
            int_bad.append((r['file'], r['id'], en[:120], zh[:120]))
        if collections.Counter(BS_RE.findall(en)) != collections.Counter(BS_RE.findall(zh)):
            bs_bad.append((r['file'], r['id'], en[:120], zh[:120]))
        for ge_ in g['entries']:
            ge, gz = ge_['en'], ge_['zh']
            if len(ge) < 3 or ge_.get('type') == 'role':
                continue
            if not re.search(r'(?<![A-Za-z])' + re.escape(ge) + r'(?![A-Za-z])', en):
                continue
            # longer glossary entry overlapping this one and already used -> skip
            if any(len(g2['en']) > len(ge) and g2['zh'] in zh and
                   re.search(r'(?<![A-Za-z])' + re.escape(g2['en']) + r'(?![A-Za-z])', en)
                   for g2 in g['entries']):
                continue
            if gz not in zh:
                gloss_bad.append((r['file'], r['id'], ge, gz, en[:110], zh[:110]))

    def dump(name, rows):
        with io.open(os.path.join(WORK, name), 'w', encoding='utf-8') as f:
            for row in rows:
                f.write('\t'.join(str(x) for x in row) + '\n')
        print(name, len(rows))

    dump('v_tag_%s.txt' % lang, tag_bad)
    dump('v_interp_%s.txt' % lang, int_bad)
    dump('v_backslash_%s.txt' % lang, bs_bad)
    dump('v_glossary_%s.txt' % lang, gloss_bad)
    dump('v_nozh_%s.txt' % lang, no_zh)
    print('SUMMARY tag=%d interp=%d backslash=%d glossary=%d no_zh=%d' %
          (len(tag_bad), len(int_bad), len(bs_bad), len(gloss_bad), len(no_zh)))

# ---------------------------------------------------------------------------
# repair
# ---------------------------------------------------------------------------
def first_replace(s, old, new):
    i = s.find(old)
    return s if i < 0 else s[:i] + new + s[i + len(old):]

def fix_tags(en, zh):
    ec = collections.Counter(TAG_RE.findall(en))
    zc = collections.Counter(TAG_RE.findall(zh))
    missing = ec - zc
    extra = zc - ec
    # a) append missing closing tags in source order
    if missing and all(t.startswith('{/') for t in missing):
        order, seen = [], set()
        for t in TAG_RE.findall(en):
            if missing[t] > 0 and t not in seen:
                seen.add(t)
                order.append(t)
        zh = zh + ''.join(order)
        zc = collections.Counter(TAG_RE.findall(zh))
        missing = ec - zc
        extra = zc - ec
    # b) wrap balanced missing pairs around the whole line
    for t in list(missing):
        if t.startswith('{/'):
            continue
        close = t[:1] + '/' + t[1:]
        if missing.get(close, 0) > 0:
            zh = t + zh + close
            missing[t] -= 1
            missing[close] -= 1
    # c) remove extra pairs and lone extra closers
    for t in list(extra):
        if t.startswith('{/'):
            open_t = '{' + t[2:]
            if extra.get(open_t, 0) > 0:
                zh = first_replace(zh, open_t, '')
                zh = first_replace(zh, t, '')
                extra[open_t] -= 1
                extra[t] -= 1
            else:
                zh = zh.replace(t, '', 1)
                extra[t] -= 1
        else:
            close = t[:1] + '/' + t[1:]
            if extra.get(close, 0) > 0:
                zh = first_replace(zh, t, '')
                zh = first_replace(zh, close, '')
                extra[t] -= 1
                extra[close] -= 1
    # d) drop stray closers that have no opener anywhere in zh
    zh_toks = TAG_RE.findall(zh)
    for t in zh_toks:
        if t.startswith('{/') and '{' + t[2:] not in zh_toks:
            zh = first_replace(zh, t, '')
    # e) remove extra self-closing tags beyond en count (e.g. {w})
    ec2 = collections.Counter(TAG_RE.findall(en))
    for t in TAG_RE.findall(zh):
        if '/' not in t and t in ec2 and zh.count(t) > ec2[t]:
            zh = zh.replace(t, '', zh.count(t) - ec2[t])
    # f) invalid CJK emphasis tags like {你} -> unwrap
    zh = re.sub(r'\{([\u4e00-\u9fff]+)\}', r'\1', zh)
    return zh

def fix_interp(en, zh, canon):
    # normalize "[ mc ]" -> "[mc]"; replace non-canonical tokens ([奥赖恩])
    # with missing canonical en tokens ([mc])
    zh = re.sub(r'\[\s*([^\[\]]+?)\s*\]', r'[\1]', zh)
    zh_tokens, en_tokens = INT_RE.findall(zh), INT_RE.findall(en)
    bad = [t for t in zh_tokens if t not in canon]
    missing = [t for t in en_tokens if t not in zh_tokens]
    for b in bad:
        if missing:
            zh = first_replace(zh, b, missing.pop(0))
    return zh

def cmd_repair(args):
    lang = args.lang
    with io.open(unique_path(lang), encoding='utf-8') as f:
        uniq = json.load(f)
    memory = load_memory(lang)
    g = load_glossary()
    policies = g.get('policies', {})
    canon_set = set()
    for u in uniq:
        canon_set.update(INT_RE.findall(u['en']))
    changed = {}

    def set_zh(en, zh):
        if en in memory and memory[en] != zh:
            changed[en] = (memory[en], zh)
            memory[en] = zh

    def read_violations(name):
        p = os.path.join(WORK, name)
        rows = []
        if os.path.exists(p):
            with io.open(p, encoding='utf-8') as f:
                for ln in f:
                    parts = ln.rstrip('\n').split('\t')
                    if len(parts) >= 4:
                        rows.append(parts)
        return rows

    # glossary policies (violation rows carry TRUNCATED source -> prefix match)
    for row in read_violations('v_glossary_%s.txt' % lang):
        ge, en_pref = row[2], row[4]
        if ge not in policies:
            continue
        for en in [k for k in memory if k.startswith(en_pref)]:
            zh = memory[en]
            new_zh = zh
            for alt, canon_z in policies[ge].items():
                new_zh = new_zh.replace(alt, canon_z)
            if new_zh != zh:
                set_zh(en, new_zh)

    prefixes = set()
    for name in ('v_tag_%s.txt' % lang, 'v_interp_%s.txt' % lang):
        for row in read_violations(name):
            if len(row[2]) >= 20:
                prefixes.add(row[2])
    for en in [k for k in memory if any(k.startswith(p) for p in prefixes)]:
        zh = memory[en]
        new_zh = fix_tags(en, zh)
        new_zh = fix_interp(en, new_zh, canon_set)
        # LESSON: a literal newline inside zh would break the .rpy string parse
        new_zh = new_zh.replace('\n', '\\n')
        if new_zh != zh:
            set_zh(en, new_zh)

    save_memory(lang, memory)
    print('repaired entries:', len(changed))

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
def escape_rpy(s):
    """Escape a file-form string body for embedding in a .rpy quoted string.

    Keeps existing backslash sequences (\\", \\\\, \\{ ...) untouched, escapes
    bare double quotes, and converts literal newlines to \\n escapes.
    """
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '\\':
            out.append(c)
            if i + 1 < n:
                out.append(s[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            out.append('\\"')
            i += 1
            continue
        if c == '\n':
            out.append('\\n')
            i += 1
            continue
        if c == '\r':
            i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)

def cmd_apply(args):
    lang = args.lang
    with io.open(records_path(lang), encoding='utf-8') as f:
        recs = json.load(f)
    memory = load_memory(lang)
    missing = 0
    tl = tl_dir(lang)
    os.makedirs(tl, exist_ok=True)
    by_file = collections.OrderedDict()
    for r in recs['dialogue']:
        by_file.setdefault(r['file'], []).append(r)
    for r in recs['strings']:
        by_file.setdefault(r['file'], []).append(r)
    for fname, items in by_file.items():
        dlg = [r for r in items if r['kind'] == 'dialogue']
        strs = [r for r in items if r['kind'] == 'string']
        parts = []
        if strs:
            body = []
            for r in strs:
                zh = memory.get(r['en'], r['en'])
                if r['en'] not in memory:
                    missing += 1
                if r['comment']:
                    body.append('    # ' + r['comment'])
                body.append('    old "' + escape_rpy(r['en']) + '"')
                body.append('    new "' + escape_rpy(zh) + '"')
                body.append('')
            parts.append('translate %s strings:\n\n' % lang + '\n'.join(body))
        for r in dlg:
            zh = memory.get(r['en'], r['en'])
            if r['en'] not in memory:
                missing += 1
            stmt = (r['speaker'] + ' ' if r['speaker'] else '') + '"' + escape_rpy(zh) + '"' + r['tail']
            orig = (r['speaker'] + ' ' if r['speaker'] else '') + '"' + escape_rpy(r['en']) + '"' + r['tail']
            block = []
            if r['comment']:
                block.append('# ' + r['comment'])
            block.append('translate %s %s:' % (lang, r['id']))
            block.append('')
            block.append('    # ' + orig)
            block.append('    ' + stmt)
            block.append('')
            parts.append('\n'.join(block))
        with io.open(os.path.join(tl, fname), 'w', encoding='utf-8-sig') as f:
            f.write('\n'.join(parts))
        print('wrote', fname, len(dlg), 'dialogue,', len(strs), 'strings')
    print('MISSING translations:', missing)

# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------
def cmd_names(args):
    game = os.path.join(GAME_DIR, 'game')
    g = load_glossary()
    gloss = {e['en']: e['zh'] for e in g['entries']}
    DEF_RE = re.compile(r"(^\s*define\s+\w+\s*=\s*(?:Dynamic)?Character\(\s*['\"])([^'\"]+)(['\"])(.*)$")
    backup_dir = os.path.join(WORK, 'backup_rpy')
    os.makedirs(backup_dir, exist_ok=True)
    patched = 0
    for fn in sorted(glob.glob(os.path.join(game, '*.rpy'))):
        with io.open(fn, encoding='utf-8') as f:
            lines = f.readlines()
        changed = False
        for i, ln in enumerate(lines):
            m = DEF_RE.match(ln.rstrip('\n'))
            if not m:
                continue
            zh = gloss.get(m.group(2))
            if zh and zh != m.group(2):
                lines[i] = m.group(1) + zh + m.group(3) + m.group(4) + '\n'
                changed = True
                patched += 1
        if changed:
            dst = os.path.join(backup_dir, os.path.basename(fn))
            if not os.path.exists(dst):
                shutil.copy2(fn, dst)
            with io.open(fn, 'w', encoding='utf-8', newline='\n') as f:
                f.writelines(lines)
            print('patched', os.path.basename(fn))
    print('total name replacements:', patched)

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Ren'Py localization pipeline")
    ap.add_argument('--game-dir', default=os.environ.get('RENPY_GAME_DIR', ''), help='game root')
    ap.add_argument('--api-url', default='https://api.deepseek.com/chat/completions')
    ap.add_argument('--api-key', default='', help='API key (env DEEPSEEK_API_KEY preferred)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('extract'); p.add_argument('--lang', default='chinese'); p.set_defaults(func=cmd_extract)
    p = sub.add_parser('translate')
    p.add_argument('--lang', default='chinese')
    p.add_argument('--model', default='deepseek-v4-flash')
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--batch', type=int, default=150)
    p.add_argument('--thinking', action='store_true', help='enable reasoning for all batches')
    p.set_defaults(func=cmd_translate)
    p = sub.add_parser('polish')
    p.add_argument('--lang', default='chinese')
    p.add_argument('--model', default='deepseek-v4-flash')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--batch', type=int, default=150)
    p.add_argument('--think-files', nargs='*', default=['script.rpy', 'script2.rpy', 'chat.rpy'])
    p.add_argument('--only-en-file', default='', help='only polish these source strings (one per line)')
    p.set_defaults(func=cmd_polish)
    p = sub.add_parser('validate'); p.add_argument('--lang', default='chinese'); p.set_defaults(func=cmd_validate)
    p = sub.add_parser('repair'); p.add_argument('--lang', default='chinese'); p.set_defaults(func=cmd_repair)
    p = sub.add_parser('apply'); p.add_argument('--lang', default='chinese'); p.set_defaults(func=cmd_apply)
    p = sub.add_parser('names'); p.set_defaults(func=cmd_names)

    args = ap.parse_args()
    if not args.game_dir:
        sys.exit('set --game-dir or RENPY_GAME_DIR')
    global GAME_DIR
    GAME_DIR = args.game_dir
    if not api_key(args) and args.cmd in ('translate', 'polish'):
        sys.exit('API key required (DEEPSEEK_API_KEY or --api-key)')
    args.func(args)

if __name__ == '__main__':
    main()
