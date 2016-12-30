"""
align attention scores
input:
    the attention letor result directory with intermediate results
    q info
output
    qid \t l_qt_score \t l_qe_score
"""

import sys
import json
import os


def load_all_att_vector(cv_dir):
    h_q_qt_vec = {}
    h_q_qe_vec = {}
    for k in xrange(10):
        qt_name = os.path.join(cv_dir, 'Fold%d' % k, "intermediate_qt_att_model")
        qe_name = os.path.join(cv_dir, 'Fold%d' % k, "intermediate_qe_att_model")
        qd_name = os.path.join(cv_dir, 'Fold%d' % k, "q_docno")

        l_qt_vec = [[round(r, 4) for r in json.loads(line)] for line in open(qt_name)]
        l_qe_vec = [[round(r, 4) for r in json.loads(line)] for line in open(qe_name)]
        l_qid = [line.split('\t')[0] for line in open(qd_name)]

        h_t = dict(zip(l_qid, l_qt_vec))
        h_e = dict(zip(l_qid, l_qe_vec))
        h_q_qt_vec.update(h_t)
        h_q_qe_vec.update(h_e)
    print "att vector loaded"
    return h_q_qt_vec, h_q_qe_vec


def align(q_info, h_qt_vec, h_qe_vec, out_name):
    out = open(out_name, 'w')

    for line in open(q_info):
        qid, data = line.split('\t')
        h_q = json.loads(data)
        l_qt = h_q['query'].split()
        l_qe_id_name = [(ana[0], ana[-1]) for ana in h_q['tagme']['query']]

        l_qt_att = h_qt_vec[qid]
        l_qe_att = h_qe_vec[qid]

        print >> out, qid + '\t' + json.dumps(zip(l_qt, l_qt_att)) + '\t' + json.dumps(zip(l_qe_id_name, l_qe_att))

    out.close()
    print "aligned"


def align_att_scores(q_info, cv_dir, out_name):
    h_q_qt_vec, h_q_qe_vec = load_all_att_vector(cv_dir)
    align(q_info, h_q_qt_vec, h_q_qe_vec, out_name)
    print "finished"


if __name__ == '__main__':
    if 4 != len(sys.argv):
        print "3 para: q info in + cv dir with results + out name"
        print "I fetch attention scores on q terms and q entities"
        sys.exit(-1)

    align_att_scores(*sys.argv[1:])






