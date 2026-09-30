from pathlib import Path
import hashlib
import json
import logging
import time
import numpy as np
from src.confidence import score, mean, sigmoid, flag
from src.normalization import fold

LOG = logging.getLogger(__name__)

def period_values(row: dict, table: dict) -> dict[str, list[float]]:
    result = {}
    for col in table['columns']:
        cell = row['values'][col['id']]
        period = col.get('period') or row.get('period')
        if period and cell['state']=='numeric' and cell.get('unit')!='percent':
            result.setdefault(period,[]).append(cell['value'])
    return result

def representation(row: dict, table: dict, note: dict | None = None) -> str:
    parent_id = row.get('hierarchy',{}).get('parent_id')
    parent = next((r['normalized_label'] for r in table['rows'] if r['id']==parent_id),'')
    return '\n'.join([f'Tablo: {table["title"]}', f'Dipnot: {note["number"]} {note["title"]}' if note else f'Dipnot: {row["note_reference"]}', f'Kalem: {row["normalized_label"]}', f'Parent: {parent}', f'Dönem ve değer: {period_values(row,table)}', f'Sütunlar: {", ".join(c["title"] for c in table["columns"])}'])

def candidates(note: dict) -> list[dict]:
    return [dict(row=r,table=t,text=representation(r,t,note)) for t in note['tables'] for r in t['rows'] if any(v['state']=='numeric' for v in r['values'].values())]

def numeric_features(source: dict, source_table: dict, candidate: dict, tolerance: float) -> dict:
    svals, nvals = period_values(source,source_table), period_values(candidate['row'],candidate['table'])
    evidence = []
    for period, vals in svals.items():
        targets = nvals.get(period,[])
        if targets:
            exact = min(targets,key=lambda v:abs(v-vals[0]))
            evidence.append(dict(period=period, summary_value=vals[0], note_value=exact, difference=exact-vals[0], equal=abs(exact-vals[0])<=tolerance))
    return dict(numeric=mean(e['equal'] for e in evidence), period=len(evidence)/max(1,len(svals)), evidence=evidence)

def rank_candidates(records: list[dict], method: str) -> list[dict]:
    return sorted(records,key=lambda r:(-r[f'{method}_decision'],r['row_id']))

def select_period_candidates(ranking: list[dict], periods) -> list[dict]:
    selected = ranking[:1]
    for period in periods:
        candidate = next((r for r in ranking if any(e['period']==period and e['equal'] for e in r['evidence'])),None)
        if candidate is not None and candidate not in selected:
            selected.append(candidate)
    return selected

class Matchers:
    def __init__(self,cfg: dict):
        self.cfg = cfg
        self.metadata = dict(embedding_inference=False,reranker_inference=False,fallbacks=[],models={})
        self.embedding = self.reranker = None
        import torch
        torch.set_num_threads(4)
        from sentence_transformers import SentenceTransformer, CrossEncoder
        for key,cls,attr in [('embedding_model',SentenceTransformer,'embedding'),('reranker_model',CrossEncoder,'reranker')]:
            name = cfg['matching'][key]
            path = Path(cfg['cache_dir'])/'models'/name.replace('/','--')
            try:
                model = cls(str(path) if path.is_dir() else name,local_files_only=True,device='cpu')
                if attr=='embedding':
                    model.max_seq_length=512
                else:
                    model.max_length=512
                setattr(self,attr,model)
                self.metadata['models'][attr] = dict(name=name,path=str(path),max_tokens=512)
            except Exception as exc:
                if not cfg['matching'].get('allow_fallback',True):
                    raise RuntimeError(f'Model {name} could not be loaded; run python scripts/setup_assets.py --models. {exc}') from exc
                warning = f'{attr} unavailable: {type(exc).__name__}: {exc}'
                self.metadata['fallbacks'].append(warning)
                LOG.warning(warning)

    def run(self,summaries: list[dict], note: dict, force: bool=False) -> tuple[list[dict],dict]:
        pool = candidates(note)
        sources = [(r,t) for t in summaries for r in t['rows'] if note['number'] in r['note_reference']]
        if not pool or not sources:
            return [],dict(items=[],processing=self.metadata,warnings=['No source rows or note candidates'])
        queries = [representation(r,t) for r,t in sources]
        passages = [c['text'] for c in pool]
        signature = hashlib.sha256(json.dumps([queries,passages,self.cfg['matching']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        cache = Path(self.cfg['cache_dir'])/'matching'/f'{signature}.json'
        cache.parent.mkdir(parents=True,exist_ok=True)
        saved=json.loads(cache.read_text(encoding='utf8')) if cache.exists() and not force else None
        tensor_cache=cache.with_suffix('.npz')
        start = time.perf_counter()
        if self.embedding and tensor_cache.exists() and not force:
            with np.load(tensor_cache) as tensors:
                similarities=tensors['similarities']
                per_period_similarities=[tensors[f'period_{i}'] for i in range(len(sources))]
            self.metadata['embedding_inference']=True
            self.metadata['embedding_cache_hit']=True
        elif self.embedding:
            q = self.embedding.encode(['query: '+t for t in queries],normalize_embeddings=True,show_progress_bar=False)
            p = self.embedding.encode(['passage: '+t for t in passages],normalize_embeddings=True,show_progress_bar=False)
            similarities = q@p.T
            per_period_similarities=[]
            for row,table in sources:
                period_queries=[f'query: Kalem: {row["normalized_label"]}. Tablo: {table["title"]}. Dipnot: {note["number"]}. Dönem: {period}. Değer: {values[0]}.' for period,values in period_values(row,table).items()]
                pq=self.embedding.encode(period_queries,normalize_embeddings=True,show_progress_bar=False)
                per_period_similarities.append(pq@p.T)
            self.metadata['embedding_inference']=True
            self.metadata['embedding_cache_hit']=False
            np.savez_compressed(tensor_cache,similarities=similarities,**{f'period_{i}':s for i,s in enumerate(per_period_similarities)})
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectors = TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5)).fit_transform(queries+passages)
            similarities=(vectors[:len(queries)]@vectors[len(queries):].T).toarray()
        self.metadata['embedding_seconds']=time.perf_counter()-start
        relationships, comparisons, raw_results = [],[],[]
        for i,(source,source_table) in enumerate(sources):
            indices = np.argsort(-similarities[i],kind='stable')[:self.cfg['matching']['top_k']]
            if self.embedding:
                union=set(int(j) for j in indices)
                for period_sim in per_period_similarities[i]:
                    union.update(int(j) for j in np.argsort(-period_sim,kind='stable')[:self.cfg['matching']['top_k']])
                indices=np.array(sorted(union,key=lambda j:-similarities[i,j]))
            union=set(int(j) for j in indices)
            for j,candidate in enumerate(pool):
                if numeric_features(source,source_table,candidate,self.cfg['validation']['tolerance'])['numeric']>0:
                    union.add(j)
            def shortlist_score(j):
                evidence=numeric_features(source,source_table,pool[j],self.cfg['validation']['tolerance'])
                semantic=max(0.,min(1.,(float(similarities[i,j])-.5)/.5)) if self.embedding else float(similarities[i,j])
                return .60*semantic+.30*evidence['numeric']+.10*evidence['period']
            indices=np.array(sorted(union,key=lambda j:-shortlist_score(j))[:self.cfg['matching']['top_k']])
            start = time.perf_counter()
            saved_logits={r['row_id']:r['b_logit'] for r in saved['rankings'][i]} if saved else {}
            selected_ids=[pool[int(j)]['row']['id'] for j in indices]
            if self.reranker and all(saved_logits.get(row_id) is not None for row_id in selected_ids):
                logits=np.asarray([saved_logits[row_id] for row_id in selected_ids])
                self.metadata['reranker_inference']=True
                self.metadata['reranker_cache_hit']=True
            elif self.reranker:
                import torch
                logits = np.asarray(self.reranker.predict([(queries[i],passages[int(j)]) for j in indices],activation_fn=torch.nn.Identity(),show_progress_bar=False)).reshape(-1)
                self.metadata['reranker_inference']=True
                self.metadata['reranker_cache_hit']=False
            else:
                logits = np.zeros(len(indices))
            self.metadata['reranker_seconds']=self.metadata.get('reranker_seconds',0.)+time.perf_counter()-start
            records=[]
            cosine_order={int(j):rank for rank,j in enumerate(np.argsort(-similarities[i],kind='stable'),1)}
            for rank,(j,logit) in enumerate(zip(indices,logits),1):
                candidate=pool[int(j)]
                features=numeric_features(source,source_table,candidate,self.cfg['validation']['tolerance'])
                semantic=float(similarities[i,j])
                semantic_scaled=max(0.,min(1.,(semantic-.5)/.5)) if self.embedding else semantic
                rerank=sigmoid(float(logit)) if self.reranker else semantic_scaled
                structural=mean([source['confidence'],source_table['confidence'],candidate['row']['confidence'],candidate['table']['confidence']])
                records.append(dict(row_id=candidate['row']['id'],table_id=candidate['table']['id'],label=candidate['row']['normalized_label'],a_rank=rank,cosine_rank=cosine_order[int(j)],a_score=semantic,b_logit=float(logit) if self.reranker else None,b_score=rerank,semantic_scaled=semantic_scaled,**features,structural=structural,a_decision=.60*semantic_scaled+.30*features['numeric']+.10*features['period'],b_decision=.30*semantic_scaled+.25*rerank+.35*features['numeric']+.10*features['period']))
            for rank,record in enumerate(sorted(records,key=lambda r:-r['b_score']),1):
                record['b_rank']=rank
            a=rank_candidates(records,'a')
            b=rank_candidates(records,'b')
            for method, ranking in [('a',a),('b',b)]:
                for position, record in enumerate(ranking,1):
                    record[f'{method}_combined_rank'] = position
            best=b[0]
            margin=best['b_decision']-b[1]['b_decision'] if len(b)>1 else best['b_decision']
            selected=select_period_candidates(b,period_values(source,source_table))
            selected_a=select_period_candidates(a,period_values(source,source_table))
            confidence_features=dict(semantic=best['semantic_scaled'],reranker=best['b_score'],margin=min(1.,margin/.15),numeric=mean(r['numeric'] for r in selected),period=min(1.,sum(r['period'] for r in selected)),source=best['structural'],structure=float(note['number'] in source['note_reference']))
            confidence=score(confidence_features,dict(semantic=.15,reranker=.15,margin=.10,numeric=.25,period=.10,source=.20,structure=.05))
            label=fold(best['label'])
            relation_type='closing_balance' if 'kapan' in label or 'net defter' in label else 'opening_balance' if 'acilis' in label else 'valuation_gain' if 'deger' in label and 'kazanc' in label else 'total' if 'total' in label or 'toplam' in label else 'other'
            warnings=[]
            if margin<.03:
                warnings.append('candidate_margin_low')
            covered=set(e['period'] for r in selected for e in r['evidence'])
            if covered!=set(period_values(source,source_table)):
                warnings.append('missing_period_evidence')
                confidence*=len(covered)/max(1,len(period_values(source,source_table)))
            if not self.metadata['embedding_inference'] or not self.metadata['reranker_inference']:
                warnings.append('model_fallback_active')
                confidence*=.5
            relation=flag(dict(summary_row_id=source['id'],note_number=note['number'],note_table_id=best['table_id'],note_table_ids=list(dict.fromkeys(r['table_id'] for r in selected)),note_row_ids=[r['row_id'] for r in selected],relation_type=relation_type,approach_a=dict(score=a[0]['a_score'],rank=a[0]['a_rank'],candidate=a[0]['row_id']),approach_b=dict(score=best['b_score'],rank=best['b_rank'],candidate=best['row_id']),numeric_evidence=[e for r in selected for e in r['evidence']],period_evidence=dict(source=list(period_values(source,source_table)),covered=sorted(set(e['period'] for r in selected for e in r['evidence']))),confidence=confidence,confidence_features=confidence_features,warnings=warnings),self.cfg['confidence']['low_confidence_threshold'],'relationship_evidence_below_threshold')
            relationships.append(relation)
            comparisons.append(dict(summary_row_id=source['id'],label=source['normalized_label'],approach_a=dict(candidate=a[0]['row_id'],label=a[0]['label'],score=a[0]['a_score'],rank=a[0]['a_rank'],combined_score=a[0]['a_decision']),approach_b=dict(candidate=best['row_id'],label=best['label'],score=best['b_score'],rank=best['b_rank'],combined_score=best['b_decision']),same_decision=a[0]['row_id']==best['row_id'],embedding_top1=pool[int(np.argmax(similarities[i]))]['row']['id'],embedding_cosine_top_k=[dict(row_id=pool[int(j)]['row']['id'],score=float(similarities[i,j])) for j in np.argsort(-similarities[i],kind='stable')[:self.cfg['matching']['top_k']]],reranker_top1=max(records,key=lambda r:r['b_score'])['row_id'],candidate_rankings=b,analysis=f'A: {a[0]["label"]}; B: {best["label"]}. B margin={margin:.4f}; numeric={best["numeric"]:.2f}; period={best["period"]:.2f}. Scores are not probabilities.'))
            comparison= comparisons[-1]
            for method, chosen in [('a',selected_a),('b',selected)]:
                details=dict(note_row_ids=[r['row_id'] for r in chosen],numeric_evidence=[e for r in chosen for e in r['evidence']],covered_periods=sorted({e['period'] for r in chosen for e in r['evidence']}))
                comparison[f'approach_{method}'].update(details)
                relation[f'approach_{method}'].update(details)
            comparison['same_decision']=set(comparison['approach_a']['note_row_ids'])==set(comparison['approach_b']['note_row_ids'])
            comparison['ranking_differences']=[dict(row_id=r['row_id'],a_position=r['a_combined_rank'],b_position=r['b_combined_rank']) for r in b if r['a_combined_rank']!=r['b_combined_rank']]
            raw_results.append(records)
        cache.write_text(json.dumps(dict(signature=signature,rankings=raw_results,processing=self.metadata),ensure_ascii=False,indent=2),encoding='utf8')
        return relationships,dict(items=comparisons,processing=self.metadata,agreement=mean(c['same_decision'] for c in comparisons),ground_truth_accuracy=None)
