"""
split doc info via candidate file partition
input:
    folder of trec splits
    doc info in
    out folder
output:
    out folder/[doc_info].[trec splits name]
"""
import os
import sys
import json
import logging
import ntpath
from knowledge4ir.utils import load_trec_ranking_with_score, load_json_info


def mul_load_candidate_doc(in_dir):
    l_name, l_s_doc = [], []
    for dir_name, sub_dir, f_names in os.path.walk(in_dir):
        for f_name in f_names:
            l_name.append(f_name)
            l_q_rank = load_trec_ranking_with_score(os.path.join(dir_name, f_name))
            s_doc = set(sum([ [doc for doc, score in rank]    for q, rank in l_q_rank ], []))
            l_s_doc.append(s_doc)
    return l_name, l_s_doc


def partition_doc_info(doc_info_in, l_name, l_s_doc, out_dir):

    h_doc_info = load_json_info(doc_info_in, 'docno')
    for name, s_doc in zip(l_name, l_s_doc):
        out_name = os.path.join(out_dir, ntpath.basename(doc_info_in)) + '.' + name
        out = open(out_name, 'w')
        logging.info('[%s] has [%d] target doc', name, len(s_doc))
        cnt = 0
        for docno in s_doc:
            if docno in h_doc_info:
                cnt += 1
                print >> out, json.dumps(h_doc_info[docno])
        logging.info('[%s] finished [%d/%d] find', out_name, cnt, len(s_doc))
        out.close()
    logging.info('finished')



