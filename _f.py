import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open('outputs/analysis.json', encoding='utf-8'))
P=d['politicians']; nm=lambda p:P[p]['profile']['name_ru']
order=sorted(P, key=lambda p:-P[p]['overview']['tweets_total'])
def topN(pid,k='topics',n=3):
    it=sorted(P[pid][k].items(), key=lambda kv:-kv[1]['share_of_tweets'])[:n]
    return [(x[0], f"{x[1]['share_of_tweets']:.0%}") for x in it]
print("### keyness top-1 у каждого (характерное слово)")
for p in order:
    k=P[p]['keyness'].get('1',[])
    if k: print(f"  {nm(p):20s} {k[0]['phrase']} (×{k[0].get('ratio','—')}, G²={k[0]['g2']})")
print("\n### атака vs программа")
for p in sorted(order, key=lambda x:-P[x]['rhetoric']['attack']['share_of_tweets']):
    a=P[p]['rhetoric']['attack']['share_of_tweets']; g=P[p]['rhetoric']['program']['share_of_tweets']
    print(f"  {nm(p):20s} атака {a:.0%} / программа {g:.0%}")
print("\n### мы/они")
for p in sorted(order, key=lambda x:-(P[x]['rhetoric']['we_words']['hits']/max(1,P[x]['rhetoric']['they_words']['hits']))):
    w=P[p]['rhetoric']['we_words']['hits']; t=P[p]['rhetoric']['they_words']['hits']
    print(f"  {nm(p):20s} мы {w} / они {t} = {w/max(1,t):.1f}")
print("\n### сфокусированность (HHI) — кто моно-тематичен")
for p in sorted(order, key=lambda x:-(P[x].get('topic_concentration') or {}).get('hhi',0)):
    tc=P[p].get('topic_concentration') or {}
    print(f"  {nm(p):20s} HHI {tc.get('hhi',0):.2f} топ={tc.get('top_topic')}")
print("\n### лексическое разнообразие")
for p in sorted(order, key=lambda x:-(P[x].get('lexical_diversity') or {}).get('ttr',0)):
    ld=P[p].get('lexical_diversity') or {}
    if ld.get('total',0)>=50: print(f"  {nm(p):20s} TTR {ld['ttr']:.2f} ({ld['total']} сл.)")
print("\n### кого больше всего упоминают")
mm=d['mentions']
for pid,w in mm['most_talked_about'][:6]:
    if pid in P: print(f"  {nm(pid):20s} {w}")
