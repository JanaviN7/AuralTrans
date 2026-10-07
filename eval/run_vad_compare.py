"""VAD on/off comparison from cached ASR results (no model run needed).

Prereq: eval/run_asr.py has produced the "ami_small_int8" (VAD on) and "ami_small_int8_novad"
(VAD off) caches for the meeting. Usage: python eval/run_vad_compare.py [MEETING]
"""

import sys

import collections

import jiwer

from auraltrans.config import settings
from auraltrans.evaluation import ami
from auraltrans.evaluation.metrics import normalize_text
from auraltrans.evaluation.report import cache_path, load_cached
from auraltrans.speech.asr import AsrResult

d = settings.eval_data_dir
m = sys.argv[1] if len(sys.argv) > 1 else "IS1009a"
ref_segs = ami.load_reference(d, m)
ref = normalize_text(" ".join(s.text for s in ref_segs))
r = ref.split()
BACK = {"yeah", "okay", "right", "yes", "no", "oh", "mm", "so", "well", "sure", "true", "exactly"}

results = {}
for tag, key in [("VAD on", "ami_small_int8"), ("VAD off", "ami_small_int8_novad")]:
    asr = load_cached(cache_path(d, "asr", key, m), AsrResult)
    hyp = normalize_text(" ".join(s.text for s in asr.segments))
    o = jiwer.process_words(ref, hyp)
    n = o.hits + o.substitutions + o.deletions
    h = hyp.split()
    dels, ins = collections.Counter(), collections.Counter()
    for c in o.alignments[0]:
        if c.type == "delete":
            for w in r[c.ref_start_idx:c.ref_end_idx]:
                dels[w] += 1
        elif c.type == "insert":
            for w in h[c.hyp_start_idx:c.hyp_end_idx]:
                ins[w] += 1
    back_del = sum(v for k, v in dels.items() if k in BACK)
    # repeated-phrase hallucination check: same segment text repeated 3+ times in a row
    texts = [s.text.strip().lower() for s in asr.segments]
    loops = sum(1 for i in range(2, len(texts)) if texts[i] == texts[i - 1] == texts[i - 2] and texts[i])
    # speech covered by ASR segments vs reference speech
    covered = sum(s.end - s.start for s in asr.segments)
    results[tag] = (o, n, hyp, dels, ins, back_del, loops, covered, len(asr.segments))
    print(f"{tag}: WER {100*(o.substitutions+o.deletions+o.insertions)/n:.2f}%  S={o.substitutions} D={o.deletions} "
          f"I={o.insertions}  N={n}  hyp words={len(h)}  segments={len(asr.segments)}  "
          f"ASR-covered seconds={covered:.0f}  backchannel-type deletions={back_del}  repeated-segment loops={loops}")
    print("   top deletions:", dels.most_common(6))
    print("   top insertions:", ins.most_common(6))

a, b = results["VAD on"], results["VAD off"]
print()
print(f"Change from turning VAD off: WER {100*(b[0].substitutions+b[0].deletions+b[0].insertions)/b[1] - 100*(a[0].substitutions+a[0].deletions+a[0].insertions)/a[1]:+.2f} points; "
      f"deletions {b[0].deletions - a[0].deletions:+d}, insertions {b[0].insertions - a[0].insertions:+d}, substitutions {b[0].substitutions - a[0].substitutions:+d}")
