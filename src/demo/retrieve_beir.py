# Note that BEIR uses https://github.com/cvangysel/pytrec_eval to evaluate the retrieval results.
import sys

sys.path.append('.')
from src.hipporag import HippoRAG
import os
import pytrec_eval
import argparse
import json

from tqdm import tqdm


def error_analysis(queries, run_dict, eval_res):
    retrieval_logs = []
    for idx, query_id in enumerate(run_dict):
        if eval_res[query_id]['ndcg'] > 0.5:
            continue
        gold_passages = queries[idx]['paragraphs']
        pred_passages = []
        for pred_corpus_id in run_dict[query_id]:
            for corpus_item in corpus:
                if corpus_item['idx'] == pred_corpus_id:
                    pred_passages.append(corpus_item)

        retrieval_logs.append({'query': queries[idx]['text'], 'gold_passages': gold_passages, 'pred_passages': pred_passages})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=str, help='e.g., `sci_fact_test`, `fiqa_dev`.')
    parser.add_argument('--extraction_model', type=str, default='gpt-3.5-turbo-1106')
    parser.add_argument('--retrieval_model', type=str, choices=['facebook/contriever', 'colbertv2'])
    parser.add_argument('--doc_ensemble', action='store_true')
    parser.add_argument('--dpr_only', action='store_true')
    args = parser.parse_args()

    # assert at most only one of them is True
    assert not (args.doc_ensemble and args.dpr_only)
    corpus = json.load(open(f'data/{args.dataset}_corpus.json'))
    qrel = json.load(open(f'data/{args.dataset}_qrel.json'))  # note that this is json file processed from tsv file, used for pytrec_eval
    hipporag = HippoRAG(args.dataset, 'openai', args.extraction_model, args.retrieval_model, doc_ensemble=args.doc_ensemble, dpr_only=args.dpr_only)

    with open(f'data/{args.dataset}_queries.json') as f:
        queries = json.load(f)

    doc_ensemble_str = 'doc_ensemble' if args.doc_ensemble else 'no_ensemble'
    extraction_str = args.extraction_model.replace('/', '_').replace('.', '_')
    retrieval_str = args.retrieval_model.replace('/', '_').replace('.', '_')
    dpr_only_str = '_dpr_only' if args.dpr_only else ''
    run_output_path = f'exp/{args.dataset}_run_{doc_ensemble_str}_{extraction_str}_{retrieval_str}{dpr_only_str}.json'

    metrics = {'map', 'ndcg'}
    evaluator = pytrec_eval.RelevanceEvaluator(qrel, metrics)

    if os.path.isfile(run_output_path):
        run_dict = json.load(open(run_output_path))
        print(f'Log file found at {run_output_path}, len: {len(run_dict)}')
    else:
        run_dict = {}  # for pytrec_eval

    to_update_run = False
    for query in tqdm(queries):
        query_text = query['text']
        query_id = query['id']
        if query_id in run_dict:
            continue
        ranks, scores, logs = hipporag.rank_docs(query_text, top_k=10)

        retrieved_docs = [corpus[r] for r in ranks]
        run_dict[query_id] = {doc['idx']: score for doc, score in zip(retrieved_docs, scores)}
        to_update_run = True

    if to_update_run:
        with open(run_output_path, 'w') as f:
            json.dump(run_dict, f)
            print(f'Run saved to {run_output_path}, len: {len(run_dict)}')

    eval_res = evaluator.evaluate(run_dict)

    # get average scores
    avg_scores = {}
    for metric in metrics:
        avg_scores[metric] = round(sum([v[metric] for v in eval_res.values()]) / len(eval_res), 3)
    print(f'Evaluation results: {avg_scores}')
    # error_analysis(queries, run_dict, eval_res)
