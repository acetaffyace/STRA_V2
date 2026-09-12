from __future__ import annotations

import csv, hashlib, json, re, sqlite3, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

DB = Path(r"D:\reviews\SentiNext\source\data\sentinext.db")
OUT = Path("audit_outputs")
OUT.mkdir(exist_ok=True)
BUCKETS = [(1,3),(4,8),(9,15),(16,30),(31,50),(51,80),(81,120),(121,200),(201,300),(301,None)]

def jload(v, default):
    try: return json.loads(v) if v else default
    except Exception: return default

def norm(s):
    s = unicodedata.normalize("NFKC", s or "").replace("\r\n","\n").replace("\r","\n").strip()
    return re.sub(r"[ \t\f\v]+", " ", s)

def cmp_norm(s): return norm(s).casefold()
def lexical(c): return unicodedata.category(c).startswith(("L","N"))
def tokens(s): return re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", s, flags=re.UNICODE)

DRAWING = set("─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋█░▒▓▀▄▌▐▖▗▘▙▚▛▜▝▞▟⠁⠃⣿")
ASCII_ART = set(r"/\|_-=*#@.:;+~")

def is_emoji(c):
    n = ord(c)
    return 0x1F000 <= n <= 0x1FAFF or 0x2600 <= n <= 0x27BF or 0xFE00 <= n <= 0xFE0F

def line_stats(line):
    cs=list(line); letters=sum(unicodedata.category(c).startswith("L") for c in cs)
    digits=sum(unicodedata.category(c).startswith("N") for c in cs); n=max(len(cs),1)
    return {"line_length":len(cs),"letter_count":letters,"digit_count":digits,
            "cjk_count":sum("CJK" in unicodedata.name(c,"") for c in cs),
            "lexical_count":letters+digits,"whitespace_count":sum(c.isspace() for c in cs),
            "punctuation_count":sum(unicodedata.category(c).startswith("P") for c in cs),
            "symbol_count":sum(unicodedata.category(c).startswith("S") for c in cs)+sum(c in ASCII_ART for c in cs),
            "drawing_char_count":sum(c in DRAWING for c in cs),"emoji_count":sum(is_emoji(c) for c in cs),
            "lexical_ratio":(letters+digits)/n,"symbol_ratio":(sum(unicodedata.category(c).startswith("S") for c in cs)+sum(c in ASCII_ART for c in cs))/n,
            "drawing_char_ratio":sum(c in DRAWING for c in cs)/n}

def art_lines(text):
    out=[]
    for i,raw in enumerate(text.replace("\r\n","\n").replace("\r","\n").split("\n")):
        line=raw.strip()
        if line:
            st=line_stats(line); st.update(line_no=i+1,text=line); out.append(st)
    return out

def label_parts(payload):
    p=payload if isinstance(payload,dict) else {}
    def arr(*ks):
        for k in ks:
            if isinstance(p.get(k),list): return [str(x) for x in p[k]]
        return []
    return arr("subcategories","primary_subcategories","topics"),arr("issue_subcategories","issues"),arr("request_subcategories","requests")

def pct(n,d): return round(100*n/d,2) if d else 0.0

def write_csv(name,rows,fields):
    with (OUT/name).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def paragraph_dedup_len(text):
    paras=[cmp_norm(p) for p in re.split(r"\n\s*\n+",text) if p.strip()]
    seen=set(); kept=[]
    for p in paras:
        if p not in seen: seen.add(p); kept.append(p)
    return sum(map(len,kept))+max(0,len(kept)-1)*2

def main():
    con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True); con.row_factory=sqlite3.Row
    rows=[]
    sql="SELECT r.id,r.review_id,r.app_id,r.data,r.timestamp_created,rl.payload AS label_payload FROM reviews r LEFT JOIN review_labels rl ON rl.app_id=r.app_id AND rl.review_id=r.review_id"
    for q in con.execute(sql):
        data=jload(q["data"],{}); original="" if data.get("review") is None else str(data.get("review"))
        ntext=norm(original); ls=art_lines(original)
        a=[x for x in ls if x["line_length"]>=8 and x["drawing_char_ratio"]>=.50]
        b=[x for x in ls if x["line_length"]>=8 and x["symbol_ratio"]>=.75 and x["lexical_count"]<=3]
        lines=[x.strip() for x in original.replace("\r\n","\n").replace("\r","\n").split("\n") if x.strip()]
        groups=defaultdict(list)
        for x in lines: groups[cmp_norm(x)].append(x)
        line_dedup="\n".join(v[0] for v in groups.values())
        paras=[cmp_norm(p) for p in re.split(r"\n\s*\n+",original) if p.strip()]
        para_len=paragraph_dedup_len(original)
        pri,iss,req=label_parts(jload(q["label_payload"],{}))
        rows.append({"row_id":q["id"],"review_id":str(q["review_id"]),"app_id":q["app_id"],"language":str(data.get("language") or "unknown"),
          "timestamp":q["timestamp_created"],"voted_up":data.get("voted_up"),"helpful_votes":data.get("votes_up",data.get("votes_helpful",0)),
          "original_text":original,"normalized_text":ntext,"char_count":len(original),"normalized_char_count":len(ntext),
          "line_count":len(original.replace("\r\n","\n").replace("\r","\n").split("\n")),"non_empty_line_count":len(ls),"paragraph_count":len(paras),
          "labelled":q["label_payload"] is not None,"primary":pri,"issues":iss,"requests":req,"art_a":a,"art_b":b,
          "art_c":sum(x["line_length"]>=8 and x["symbol_ratio"]>=.75 and x["lexical_count"]<=3 for x in ls)>=3,
          "art_chars":sum(x["line_length"] for x in b),"line_dedup_text":line_dedup,"line_saved":max(0,len(original)-len(line_dedup)),
          "line_dup_count":sum(len(v)-1 for v in groups.values() if len(v)>1),"para_saved":max(0,len(original)-para_len),
          "combined_saved":max(0,len(original)-paragraph_dedup_len(line_dedup))})
    nonempty=[r for r in rows if r["normalized_text"]]; labelled=[r for r in nonempty if r["labelled"]]
    text_counts=Counter(r["normalized_text"].casefold() for r in nonempty); clusters=defaultdict(list)
    for r in nonempty: clusters[hashlib.sha256(r["normalized_text"].casefold().encode()).hexdigest()].append(r)
    dup={h:v for h,v in clusters.items() if len(v)>=2}

    arts=[]; symbols=[]
    for r in rows:
        ls=art_lines(r["original_text"]); lc=sum(lexical(c) for c in r["original_text"]); total=max(1,r["char_count"]); ach=sum(x["line_length"] for x in r["art_b"])
        if r["art_b"]:
            rem="\n".join(x["text"] for x in ls if x not in r["art_b"])
            arts.append({"review_id":r["review_id"],"app_id":r["app_id"],"language":r["language"],"original_char_count":r["char_count"],"art_ratio":round(ach/total,4),"art_line_count":len(r["art_b"]),"original_preview":r["original_text"][:500],"remaining_after_art":rem[:500],"has_normal_text_after":bool(tokens(rem))})
        if r["char_count"] and lc<=2 and lc/total<.10:
            form="emoji_only" if all(is_emoji(c) or c.isspace() for c in r["original_text"]) else ("drawing_only" if all(c in DRAWING or c.isspace() for c in r["original_text"]) else ("punctuation_or_symbol" if lc==0 else "low_lexical"))
            symbols.append({"review_id":r["review_id"],"app_id":r["app_id"],"language":r["language"],"char_count":r["char_count"],"lexical_count":lc,"lexical_ratio":round(lc/total,4),"form":form,"normalized_text":r["normalized_text"][:300],"voted_up":r["voted_up"]})
    write_csv("ascii_art_candidates.csv",sorted(arts,key=lambda x:x["art_ratio"],reverse=True),["review_id","app_id","language","original_char_count","art_ratio","art_line_count","original_preview","remaining_after_art","has_normal_text_after"])
    write_csv("symbol_only_candidates.csv",symbols,["review_id","app_id","language","char_count","lexical_count","lexical_ratio","form","normalized_text","voted_up"])
    reps=[{"review_id":r["review_id"],"app_id":r["app_id"],"original_char_count":r["char_count"],"line_dedup_char_count":r["char_count"]-r["line_saved"],"saved_chars":r["line_saved"],"saved_ratio":round(r["line_saved"]/max(1,r["char_count"]),4),"duplicate_line_count":r["line_dup_count"],"original_preview":r["original_text"][:500],"line_dedup_text":r["line_dedup_text"][:500]} for r in rows if r["line_saved"]>0]
    write_csv("repeat_compression_candidates.csv",sorted(reps,key=lambda x:x["saved_ratio"],reverse=True),list(reps[0]) if reps else ["review_id"])

    cls=[]; conflicts=[]
    for h,rs in sorted(dup.items(),key=lambda kv:len(kv[1]),reverse=True):
        variants=[(tuple(x["primary"]),tuple(x["issues"]),tuple(x["requests"])) for x in rs if x["labelled"]]; consistent=len(set(variants))<=1 if variants else None
        cls.append({"hash":h,"cluster_size":len(rs),"normalized_text":rs[0]["normalized_text"][:1000],"review_ids":"|".join(x["review_id"] for x in rs[:50]),"app_ids":"|".join(str(x["app_id"]) for x in rs),"languages":"|".join(x["language"] for x in rs),"voted_up_distribution":json.dumps(Counter(str(x["voted_up"]) for x in rs),ensure_ascii=False),"labelled_members":sum(x["labelled"] for x in rs),"labels_consistent":consistent})
        if len(variants)>=2 and not consistent:
            conflicts.append({"hash":h,"cluster_size":len(rs),"normalized_text":rs[0]["normalized_text"][:1000],"labelled_members":len(variants),"label_variants":json.dumps([{"review_id":x["review_id"],"primary":x["primary"],"issues":x["issues"],"requests":x["requests"]} for x in rs if x["labelled"]],ensure_ascii=False)})
    write_csv("exact_duplicate_clusters.csv",cls,["hash","cluster_size","normalized_text","review_ids","app_ids","languages","voted_up_distribution","labelled_members","labels_consistent"])
    write_csv("exact_duplicate_label_conflicts.csv",conflicts,["hash","cluster_size","normalized_text","labelled_members","label_variants"])

    dist=[]; ldist=[]; tops=[]
    for lo,hi in BUCKETS:
        name=f"{lo}+" if hi is None else f"{lo}-{hi}"
        group=[r for r in nonempty if r["char_count"]>=lo and (hi is None or r["char_count"]<=hi)]; lg=[r for r in labelled if r in group]; tc=[len(set(r["primary"]+r["issues"]+r["requests"])) for r in lg]
        dupn=sum(text_counts[r["normalized_text"].casefold()]>=2 for r in group)
        dist.append({"bucket":name,"review_count":len(group),"share_pct":pct(len(group),len(nonempty)),"unique_normalized_text_count":len(set(r["normalized_text"].casefold() for r in group)),"exact_duplicate_count":dupn,"exact_duplicate_rate_pct":pct(dupn,len(group)),"average_char_count":round(sum(r["char_count"] for r in group)/len(group),2) if group else 0,"median_char_count":median([r["char_count"] for r in group]) if group else 0})
        dist_labels={"bucket":name,"labelled_review_count":len(lg),"average_topic_count":round(sum(tc)/len(tc),2) if tc else 0,"median_topic_count":median(tc) if tc else 0,"only_other_general_pct":pct(sum(not r["issues"] and not r["requests"] and len(r["primary"])<=1 for r in lg),len(lg)),"issue_pct":pct(sum(bool(r["issues"]) for r in lg),len(lg)),"request_pct":pct(sum(bool(r["requests"]) for r in lg),len(lg)),"two_plus_topic_pct":pct(sum(x>=2 for x in tc),len(lg)),"four_plus_topic_pct":pct(sum(x>=4 for x in tc),len(lg))}
        ldist.append(dist_labels)
    for lim in [3,8,15,30,50]:
        eligible=[r for r in nonempty if r["char_count"]<=lim]; counts=Counter(r["normalized_text"].casefold() for r in eligible)
        for txt,cnt in counts.most_common(50):
            rs=[r for r in eligible if r["normalized_text"].casefold()==txt]; lab=[r for r in rs if r["labelled"]]
            tops.append({"max_chars":lim,"normalized_text":txt,"count":cnt,"unique_review_ids":len(set(r["review_id"] for r in rs)),"app_count":len(set(r["app_id"] for r in rs)),"language_distribution":json.dumps(Counter(r["language"] for r in rs),ensure_ascii=False),"voted_up_distribution":json.dumps(Counter(str(r["voted_up"]) for r in rs),ensure_ascii=False),"labelled_count":len(lab),"label_variants":json.dumps(Counter(str((r["primary"],r["issues"],r["requests"])) for r in lab),ensure_ascii=False),"other_general_pct":pct(sum(not r["issues"] and not r["requests"] and len(r["primary"])<=1 for r in lab),len(lab)),"issue_pct":pct(sum(bool(r["issues"]) for r in lab),len(lab)),"request_pct":pct(sum(bool(r["requests"]) for r in lab),len(lab))})
    write_csv("short_text_distribution.csv",dist+ldist,["bucket","review_count","share_pct","unique_normalized_text_count","exact_duplicate_count","exact_duplicate_rate_pct","average_char_count","median_char_count","labelled_review_count","average_topic_count","median_topic_count","only_other_general_pct","issue_pct","request_pct","two_plus_topic_pct","four_plus_topic_pct"])
    write_csv("top_short_texts.csv",tops,list(tops[0]) if tops else ["max_chars"])

    total=len(rows); empty=total-len(nonempty); chars=sum(r["char_count"] for r in rows); line_saved=sum(r["line_saved"] for r in rows); para_saved=sum(r["para_saved"] for r in rows); combined_saved=sum(r["combined_saved"] for r in rows)
    art_a=sum(bool(r["art_a"]) for r in rows); art_b=sum(bool(r["art_b"]) for r in rows); art_c=sum(r["art_c"] for r in rows); art50=sum(r["art_chars"]>=.5*max(1,r["char_count"]) for r in rows); art80=sum(r["art_chars"]>=.8*max(1,r["char_count"]) for r in rows); artmix=sum(bool(r["art_b"]) and bool(tokens("\n".join(x["text"] for x in art_lines(r["original_text"]) if x not in r["art_b"]))) for r in rows)
    pure=sum(r["char_count"]>0 and not any(lexical(c) for c in r["original_text"]) for r in rows); dup_members=sum(map(len,dup.values())); dup_clusters=len(dup); unique_texts=len(clusters); reduction=dup_members-dup_clusters
    ml=[v for v in dup.values() if sum(x["labelled"] for x in v)>=2]; consistent=sum(len({(tuple(x["primary"]),tuple(x["issues"]),tuple(x["requests"])) for x in v if x["labelled"]})<=1 for v in ml)
    summary={"database":str(DB),"read_only":True,"normalization":"NFKC; trim; CRLF/CR to LF; ordinary whitespace fold; casefold only for comparisons; Python len(str) code points","dataset":{"total_reviews":total,"non_empty_reviews":len(nonempty),"empty_reviews":empty,"labelled_reviews":len(labelled),"app_count":len(set(r["app_id"] for r in rows)),"language_count":len(set(r["language"] for r in rows)),"languages":dict(Counter(r["language"] for r in rows))},"art":{"rule_A_count":art_a,"rule_B_count":art_b,"rule_C_count":art_c,"art_ratio_ge_50_count":art50,"art_ratio_ge_80_count":art80,"mixed_text_after_removal_count":artmix},"symbol":{"pure_non_lexical_count":pure,"low_lexical_candidate_count":len(symbols)},"compression":{"total_chars":chars,"line_dedup_saved_chars":line_saved,"line_dedup_saved_pct":pct(line_saved,chars),"paragraph_dedup_saved_chars":para_saved,"paragraph_dedup_saved_pct":pct(para_saved,chars),"line_plus_paragraph_saved_chars":combined_saved,"line_plus_paragraph_saved_pct":pct(combined_saved,chars),"line_repeat_review_count":len(reps),"saved_gt_10_pct":sum(x["saved_ratio"]>.10 for x in reps),"saved_gt_25_pct":sum(x["saved_ratio"]>.25 for x in reps),"saved_gt_50_pct":sum(x["saved_ratio"]>.50 for x in reps),"saved_gt_80_pct":sum(x["saved_ratio"]>.80 for x in reps)},"exact_duplicates":{"cluster_count":dup_clusters,"duplicate_member_count":dup_members,"unique_text_count_all":unique_texts,"theoretical_review_input_reduction":reduction,"reduction_pct":pct(reduction,len(nonempty)),"size_distribution":dict(Counter("2" if len(v)==2 else "3" if len(v)==3 else "4-5" if len(v)<=5 else "6-10" if len(v)<=10 else "11-20" if len(v)<=20 else "21-50" if len(v)<=50 else "50+" for v in dup.values()))},"label_consistency":{"multi_label_cluster_count":len(ml),"consistent_cluster_count":consistent,"conflict_cluster_count":len(ml)-consistent,"consistency_pct":pct(consistent,len(ml))}}
    (OUT/"audit_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

    def table(headers,rows):
        clean=lambda x: str(x).replace("|","\\|").replace("\n"," ")
        return "| "+" | ".join(clean(x) for x in headers)+" |\n|"+"|".join("---" for _ in headers)+"|\n"+"\n".join("| "+" | ".join(clean(x) for x in row)+" |" for row in rows)+"\n"
    report="# SentiNext Steam 评论本地预处理审计\n\n"
    report+=f"## 1. Dataset Overview\n\n只读来源：{DB}。核心表为 reviews（id、review_id、app_id、data JSON、timestamp_created/timestamp_updated）和 review_labels（app_id、review_id、payload JSON）。实际评论字段为 data.review、data.language、data.voted_up、data.votes_up；标签 payload 中使用 subcategories、issue_subcategories、request_subcategories。未修改数据库、原文或标签。总评论 **{total:,}**，非空 **{len(nonempty):,}**，空 **{empty:,}**，已有标签 **{len(labelled):,}**，游戏 **{len(set(r['app_id'] for r in rows)):,}**，语言 **{len(set(r['language'] for r in rows)):,}**。文本结构统计以全部评论为分母；标签关系以已有标签评论为分母。\n\nNormalization：Unicode NFKC、首尾裁剪、CRLF/CR→LF、普通空白折叠；比较时另行 casefold；不翻译、不改写、不删除普通词。字符长度均为 Python len(str) Unicode code point 数量。\n\n"
    art_sample=[[x["review_id"],x["app_id"],x["language"],x["original_char_count"],x["art_ratio"],x["has_normal_text_after"],x["original_preview"].replace("\n"," / ")[:120],x["remaining_after_art"].replace("\n"," / ")[:120]] for x in arts[:25]]
    report+="## 2. ASCII / Unicode Art Audit\n\n"+table(["规则","命中数","占全部"],[["A drawing ratio≥50%",art_a,pct(art_a,total)],["B symbol ratio≥75%, lexical≤3",art_b,pct(art_b,total)],["C ≥3 行满足 B",art_c,pct(art_c,total)],["B 字符占原文≥50%",art50,pct(art50,total)],["B 字符占原文≥80%",art80,pct(art80,total)],["去 art 行后仍有 lexical",artmix,pct(artmix,total)]])+"\n规则 A/B/C 仅为候选比较，不是部署阈值。以下是按 art ratio 排序的前 25 条候选；去掉候选行后仍有正常文本的记录不能直接 skip。\n\n"+table(["review_id","app","lang","chars","art ratio","normal remains","original preview","remaining text"],art_sample)+"\n完整候选见 ascii_art_candidates.csv。\n\n"
    report+=f"## 3. Non-Lexical / Symbol-only Audit\n\n纯非 lexical 候选 **{pure:,} ({pct(pure,total)}%)**；低 lexical 候选（lexical≤2 且 ratio<10%）**{len(symbols):,} ({pct(len(symbols),total)}%)**。详见 symbol_only_candidates.csv；其中保留了 10/10、W、L、GG 等可疑但可能有信息的文本供抽样。\n\n"
    report+=f"## 4. Repeated Line / Paragraph Compression\n\n全部原始字符 **{chars:,}**。exact repeated-line 模拟节省 **{line_saved:,} ({pct(line_saved,chars)}%)** 字符；重复行评论 **{len(reps):,}**；saved ratio >10%/>25%/>50%/>80%：**{sum(x['saved_ratio']>.1 for x in reps):,}/{sum(x['saved_ratio']>.25 for x in reps):,}/{sum(x['saved_ratio']>.5 for x in reps):,}/{sum(x['saved_ratio']>.8 for x in reps):,}**。仅 paragraph dedup 节省 **{para_saved:,} ({pct(para_saved,chars)}%)**；先 line 再 paragraph 的组合模拟节省 **{combined_saved:,} ({pct(combined_saved,chars)}%)**。Top 样本见 repeat_compression_candidates.csv。\n\n"
    report+=f"## 5. Exact Duplicate Clusters\n\nnormalized_text SHA-256 exact duplicate cluster **{dup_clusters:,}**，涉及评论 **{dup_members:,}**；unique text 数 **{unique_texts:,}**。每 cluster 只分类一次，理论减少评论级输入 **{reduction:,} ({pct(reduction,len(nonempty))}%)**。最大 cluster 见 exact_duplicate_clusters.csv。\n\n"
    report+=f"## 6. Exact Duplicate Label Consistency\n\n至少两个成员已有标签的 cluster **{len(ml):,}**；完全一致 **{consistent:,}**；不一致 **{len(ml)-consistent:,}**；一致率 **{pct(consistent,len(ml))}%**。冲突见 exact_duplicate_label_conflicts.csv。比较字段为 subcategories、issue_subcategories、request_subcategories 三组数组。\n\n"
    report+="## 7–8. Short Text Distribution and Existing Labels\n\n全部非空评论：\n\n"+table(["bucket","reviews","share %","unique text","dup rate %","avg chars","median"],[[x["bucket"],x["review_count"],x["share_pct"],x["unique_normalized_text_count"],x["exact_duplicate_rate_pct"],x["average_char_count"],x["median_char_count"]] for x in dist])+"\n已有标签评论：\n\n"+table(["bucket","labelled","avg topics","median","general %","issue %","request %","2+ %","4+ %"],[[x["bucket"],x["labelled_review_count"],x["average_topic_count"],x["median_topic_count"],x["only_other_general_pct"],x["issue_pct"],x["request_pct"],x["two_plus_topic_pct"],x["four_plus_topic_pct"]] for x in ldist])+"\n短文本没有按长度直接判垃圾；语言字段只做分组，不做过滤。完整 Top 短文本与语言分布见 top_short_texts.csv。\n\n"
    report+="## 9. Top Short Texts\n\n每个 <=3/8/15/30/50 区间输出 Top 50，含计数、app/language/voted_up 和已有标签分布，见 top_short_texts.csv。\n\n"
    report+="## 10. Estimated Savings\n\n"+table(["scenario","review/input reduction","character reduction","note"],[["A pure non-lexical skip",f"{pure:,} reviews ({pct(pure,total)}%)",f"{sum(r['char_count'] for r in rows if r['char_count'] and not any(lexical(c) for c in r['original_text'])):,}","conservative candidate estimate"],["B A + line/paragraph compression",f"{pure:,} skipped",f"{combined_saved:,}","simulation only"],["C B + exact duplicate reuse",f"{reduction:,} fewer classification inputs ({pct(reduction,len(nonempty))}%)",f"{combined_saved:,} chars compressed","DB row count unchanged"],["D + short-general candidates","not quantified","not claimed","needs whitelist validation"]])+"\nScenario B uses the combined line-then-paragraph simulation and avoids double-counting. Scenario A counts only pure non-lexical text; mixed art plus normal text is not automatically included.\n\n"
    report+="## 11. Recommendation\n\n### SAFE TO IMPLEMENT\n\n- Exact repeated line/paragraph compression as a reversible deterministic input transform, with original text retained.\n- Exact duplicate classification reuse with app/language/sentiment context preserved and consistency monitoring.\n- Pure non-lexical skip only behind an explicit reviewed rule and audit logging.\n\n### NEEDS MORE VALIDATION\n\n- Art thresholds and deletion of art lines, especially mixed reviews.\n- Short-general whitelist and lexical-ratio threshold.\n- Near-duplicate reuse; not run automatically here.\n\n### DO NOT IMPLEMENT YET\n\n- Length-only filtering; language-based information judgments; meme/local semantic judgments; broad keyword topic classifier.\n\n## Reproducibility and Outputs\n\nRun py audit_steam_preprocessing.py from repository root. Outputs: audit_summary.json, ascii_art_candidates.csv, symbol_only_candidates.csv, repeat_compression_candidates.csv, exact_duplicate_clusters.csv, exact_duplicate_label_conflicts.csv, short_text_distribution.csv, top_short_texts.csv.\n"
    (OUT/"STEAM_REVIEW_PREPROCESSING_AUDIT.md").write_text(report,encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
