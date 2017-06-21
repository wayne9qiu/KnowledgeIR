"""
convert boe representation (with attention) to tensor
input:
    boe info
    embedding (Use as entity id hash)
output:
    each line:
        boe id vector
        attention feature matrix
    and a numpy embedding
"""

import numpy as np
import json
import sys
import logging
from knowledge4ir.utils import (
    QUERY_FIELD,
    TARGET_TEXT_FIELDS,
)

# dump_emb = False


def _hash_feature(h_feature, h_feature_id):
    if not h_feature_id:
        h_feature_id = dict([(key, p) for p, key in enumerate(h_feature.keys())])
    l_res = [0] * len(h_feature_id)
    for name, score in h_feature.items():
        p = h_feature_id[name]
        l_res[p] = score
    return l_res, h_feature_id


def load_embedding(word2vec_in):
    l_e = []
    l_emb = []

    logging.info('start loading embedding')
    for p, line in enumerate(open(word2vec_in)):
        if not p:
            continue
        if not p % 1000:
            logging.info('loaded %d lines', p)
        cols = line.split()
        l_e.append(cols[0])
        if dump_emb:
            emb = [float(col) for col in cols[1:]]
            if not l_emb:
                l_emb.append([0] * len(emb))
            l_emb.append(emb)
    h_e_id = dict(zip(l_e, range(1, 1 + len(l_e))))
    emb_mtx = None
    logging.info('loaded [%d] entities', len(h_e_id))
    if dump_emb:
        emb_mtx = np.array(l_emb)
        logging.info('dump emb matrix shape: %s', json.dumps(emb_mtx.shape))
    return h_e_id, emb_mtx


def convert_boe_info(h_info, h_e_id, h_feature_id):
    """
    convert one boe info
    :param h_info: packed q or doc's att_boe info
    :param h_e_id: e -> id
    :param h_feature_id: feature name -> id
    :return: e id hashed, att feature put in one matrix,
    """
    h_boe_tensor = dict()
    for field in [QUERY_FIELD] + TARGET_TEXT_FIELDS:
        if field not in h_info['boe']:
            continue
        ll_feature = []
        l_ana = [ana for ana in h_info['boe'][field] if ana['id'] in h_e_id]
        l_e_id = [h_e_id[ana['id']] for ana in l_ana]
        for ana in l_ana:
            h_f = ana['feature']
            l_feature_vector, h_feature_id = _hash_feature(h_f, h_feature_id)
            ll_feature.append(l_feature_vector)

        h_boe_tensor[field] = {'boe': l_e_id, 'att_mtx': ll_feature}
    l_key = ['qid', 'docno']
    for key in l_key:
        if key in h_info:
            h_boe_tensor[key] = h_info[key]
    return h_boe_tensor, h_feature_id


def process(in_name, emb_name, out_name):
    out = open(out_name, 'w')
    h_e_id, emb_mtx = load_embedding(emb_name)
    if dump_emb:
        np.save(out_name + '.emb', emb_mtx)
    h_feature_id = {}
    for p, line in enumerate(open(in_name)):
        if not p % 1000:
            logging.info('converted [%d] lines', p)
        h_info = json.loads(line)

        h_boe_tensor, h_feature_id = convert_boe_info(h_info, h_e_id, h_feature_id)
        print >> out, json.dumps(h_boe_tensor)

    json.dump(h_e_id, open(out_name + '.e_id.json', 'w'))
    json.dump(h_feature_id, open(out_name + '.att_feature_id.json', 'w'), indent=1)
    logging.info('finished, res dumped to [%s]', out_name)
    return


if __name__ == '__main__':
    from knowledge4ir.utils import (
        set_basic_log,
    )
    set_basic_log(logging.INFO)
    if 4 > len(sys.argv):
        print "convert boe to tensor format"
        print "3+ para: boe info in + embedding name + out_name + dump emb mtx (default 0)"
        sys.exit(-1)
    global dump_emb
    dump_emb = False
    if len(sys.argv) > 4:
        dump_emb = bool(int(sys.argv[4]))
        logging.info('will dump embedding mtx')
    process(*sys.argv[1:4])

