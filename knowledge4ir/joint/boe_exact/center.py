"""
feature extraction center

input:
    trec format candidate documents
    doc info
    q info
    feature group:
        base retrieval

output:
    svm format features

"""


from traitlets.config import Configurable
from knowledge4ir.utils import (
    load_py_config,
    load_trec_ranking_with_score,
    load_trec_labels_dict,
    dump_svm_feature,
    set_basic_log
)
import json
from knowledge4ir.joint.boe_exact.boe_feature import (
    AnaMatch
)
import json
import logging

from traitlets import (
    Int,
    Unicode,
    Bool,
    List,
)


class BoeLeToRFeatureExtractCenter(Configurable):
    l_feature_group = List(Unicode, default_value=['AnaExact']).tag(config=True)
    h_feature_extractor = {"AnaExact": AnaMatch}

    trec_rank_in = Unicode(help='trec rank candidate doc in').tag(config=True)
    q_info_in = Unicode(help='prepared query info in').tag(config=True)
    doc_info_in = Unicode(help='prepared doc info in').tag(config=True)
    qrel_in = Unicode(help='qrel').tag(config=True)
    out_name = Unicode(help='svm feature output place').tag(config=True)
    
    def __init__(self, **kwargs):
        super(BoeLeToRFeatureExtractCenter, self).__init__(**kwargs)
        self.l_extractor = []
        self.h_q_info = dict()
        self.h_doc_info = dict()
        self.h_qrel = dict()

        self._set_extractor(**kwargs)
        self._load_data()

    def _set_extractor(self, **kwargs):
        for name in self.l_feature_group:
            if name not in self.h_feature_extractor:
                logging.error('[%s] not in dict %s', name, json.dumps(self.h_feature_extractor))
            assert name in self.h_feature_extractor
            self.l_feature_group.append(self.h_feature_extractor[name](**kwargs))
            logging.info('init [%s] extractor', name)

        logging.info('total [%d] group features', len(self.l_feature_group))

    def _load_data(self):
        self.h_qrel = load_trec_labels_dict(self.qrel_in)

        l_h_data = [json.loads(line) for line in open(self.q_info_in)]
        l_qid = [h['qid'] for h in l_h_data]
        self.h_q_info = dict(zip(l_qid, l_h_data))

        l_h_data = [json.loads(line) for line in open(self.doc_info_in)]
        l_docno = [h['docno'] for h in l_h_data]
        self.h_doc_info = dict(zip(l_docno, l_h_data))

    def extract(self):
        l_q_rank = load_trec_ranking_with_score(self.trec_rank_in)
        l_svm_data = []

        for q, ranking in l_q_rank:
            q_info = self.h_q_info[q]
            for docno, base_score in ranking:
                doc_info = self.h_doc_info.get(docno, {})
                label = self.h_qrel.get(q, {}).get(docno, 0)
                h_feature = dict()
                h_feature['base'] = base_score

                for extractor in self.l_extractor:
                    h_feature.update(extractor.extract_pair(q_info, doc_info))

                svm_data = {
                    "qid": q,
                    "score": label,
                    "feature": h_feature,
                    "comment": docno
                }
                l_svm_data.append(svm_data)

        logging.info('extraction finished, dumping...')
        dump_svm_feature(l_svm_data, self.out_name)
        logging.info('ranking features dumped to [%s]', self.out_name)
        return


if __name__ == '__main__':
    import sys
    set_basic_log(logging.INFO)

    if 2 != len(sys.argv):
        print "1 para: config"
        BoeLeToRFeatureExtractCenter.class_print_help()
        sys.exit(-1)

    center = BoeLeToRFeatureExtractCenter(config=load_py_config(sys.argv[1]))
    center.extract()




