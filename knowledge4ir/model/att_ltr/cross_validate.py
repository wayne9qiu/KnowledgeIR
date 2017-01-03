"""
cross validate hybrid model
"""

from knowledge4ir.model.att_ltr.hierarchical import (
    HierarchicalAttLeToR,
    FlatLeToR,
    QTermLeToR,
    QEntityLeToR,
    MaskHierarchicalAttLeToR,
    ProbAttLeToR,
)
from knowledge4ir.model.att_ltr import (
    AttLeToR,
    dfs_para,
)
from knowledge4ir.model import (
    fix_kfold_partition,
    filter_json_lines,
)
from knowledge4ir.utils import (
    load_py_config,
    dump_trec_ranking_with_score,
    GDEVAL_PATH,
    seg_gdeval_out,
    set_basic_log,
)
from traitlets.config import Configurable
from traitlets import (
    Int,
    Unicode,
    List,
    Bool,
    Dict,
)
import logging
import json
import os
import subprocess


class CrossValidator(Configurable):
    data_in = Unicode(help="total data in").tag(config=True)
    with_dev = Bool(True, help='with development').tag(config=True)
    h_dev_para = Dict(default_value={},
                      help="to explore parameters").tag(config=True)
    out_dir = Unicode(help="out dir").tag(config=True)
    qrel = Unicode(help='qrel in').tag(config=True)

    nb_folds = Int(10, help="k").tag(config=True)
    q_st = Int(-1).tag(config=True)
    q_ed = Int(-1).tag(config=True)
    model_name = Unicode('hierarchical',
                    help='to cross validate model: hierarchical, prob'
                         'qterm_flat, qentity_flat, flat, mask'
                    ).tag(config=True)
    get_intermediate_res = Bool(True, help="whether predict intermediate results").tag(config=True)

    def __init__(self, **kwargs):
        super(CrossValidator, self).__init__(**kwargs)
        self.model = None
        self._init_model(**kwargs)
        self.l_total_data_lines = []
        if self.data_in:
            self.l_total_data_lines = open(self.data_in).read().splitlines()
            if (self.q_st == -1) | (self.q_ed == -1):
                l_qid, __ = AttLeToR.get_qid_docno(self.l_total_data_lines)
                l_qid = [int(q) for q in l_qid]
                self.q_st = min(l_qid)
                self.q_ed = max(l_qid)
        logging.info('q range [%d, %d]', self.q_st, self.q_ed)
        self.l_train_folds, self.l_test_folds, self.l_dev_folds = fix_kfold_partition(
            self.with_dev, self.nb_folds, self.q_st, self.q_ed
        )

        if not os.path.exists(self.out_dir):
            try:
                os.makedirs(self.out_dir)
            except OSError:
                logging.warn('out dir create conflict')

    def _init_model(self, **kwargs):
        if self.model_name == 'hierarchical':
            self.model = HierarchicalAttLeToR(**kwargs)
        if self.model_name == 'prob':
            self.model = ProbAttLeToR(**kwargs)
        if self.model_name == 'qterm_flat':
            self.model = QTermLeToR(**kwargs)
        if self.model_name == 'qentity_flat':
            self.model = QEntityLeToR(**kwargs)
        if self.model_name == 'flat':
            self.model = FlatLeToR(**kwargs)
        if self.model_name == 'mask':
            self.model = MaskHierarchicalAttLeToR(**kwargs)

    @classmethod
    def class_print_help(cls, inst=None):
        super(CrossValidator, cls).class_print_help(inst)
        HierarchicalAttLeToR.class_print_help(inst)
        QTermLeToR.class_print_help(inst)
        QEntityLeToR.class_print_help(inst)
        QTermLeToR.class_print_help(inst)

    def train_test_fold(self, k):
        out_dir = os.path.join(self.out_dir, 'Fold%d' % k)
        logging.info('fold [%d] for [%s]', k, out_dir)
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except OSError:
                logging.warn('out dir create conflicted')
        l_train_svm = filter_json_lines(self.l_total_data_lines, self.l_train_folds[k])
        l_test_svm = filter_json_lines(self.l_total_data_lines, self.l_test_folds[k])
        self.model.train(l_train_svm)

        self.testing(l_test_svm, out_dir)
        # l_q_ranking = self.model.predict(l_test_svm)
        # rank_out_name = out_dir + '/trec'
        # eva_out_name = out_dir + '/eval'
        # dump_trec_ranking_with_score(l_q_ranking, rank_out_name)
        # eva_str = subprocess.check_output(
        #     ['perl', GDEVAL_PATH, self.qrel, rank_out_name]).strip()
        # print >> open(eva_out_name, 'w'), eva_str.strip()
        # logging.info("training testing fold %d done with %s",
        #              k, eva_str.splitlines()[-1])
        return

    def train_dev_test_fold(self, k):
        out_dir = os.path.join(self.out_dir, 'Fold%d' % k)
        logging.info('fold [%d] for [%s]', k, out_dir)

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        l_train_lines = filter_json_lines(self.l_total_data_lines, self.l_train_folds[k])
        l_test_lines = filter_json_lines(self.l_total_data_lines, self.l_test_folds[k])
        l_dev_lines = filter_json_lines(self.l_total_data_lines, self.l_dev_folds[k])
        best_ndcg = 0
        best_para = None
        dev_eva_out = open(out_dir + '/dev_para.eval', 'w')
        logging.info('start developing parameters')
        for h_para in self._get_dev_para_list():
            logging.info('evaluating para %s', json.dumps(h_para))
            self.model.set_para(h_para)
            self.model.train(l_train_lines)
            l_q_ranking = self.model.predict(l_dev_lines)
            rank_out_name = out_dir + '/dev.trec'
            dump_trec_ranking_with_score(l_q_ranking, rank_out_name)
            eva_str = subprocess.check_output(
                ['perl', GDEVAL_PATH,  self.qrel, rank_out_name]).strip()
            __, ndcg, err = seg_gdeval_out(eva_str)
            logging.info('para %s get ndcg %f', json.dumps(h_para), ndcg)
            print >> dev_eva_out, '%s\t%f,%f' % (json.dumps(h_para), ndcg, err)
            if ndcg > best_ndcg:
                logging.info('get better ndcg %f with %s', ndcg, json.dumps(h_para))
                best_ndcg = ndcg
                best_para = h_para
        dev_eva_out.close()
        logging.info('best ndcg %f with %s', best_ndcg, json.dumps(best_para))
        logging.info('start training total')
        self.model.set_para(best_para)
        self.model.train(l_train_lines + l_dev_lines)

        self.testing(l_test_lines, out_dir)
        # l_q_ranking = self.model.predict(l_test_lines)
        # rank_out_name = out_dir + '/trec'
        # eva_out_name = out_dir + '/eval'
        # dump_trec_ranking_with_score(l_q_ranking, rank_out_name)
        # eva_str = subprocess.check_output(
        #     ['perl', GDEVAL_PATH, self.qrel, rank_out_name]).strip()
        # print >> open(eva_out_name, 'w'), eva_str.strip()
        # __, ndcg, err = seg_gdeval_out(eva_str)
        # logging.info('training testing fold %d done with ndcg %f', k, ndcg)
        return

    def overfit(self):
        logging.info('start overfit data')
        self.model.train(self.l_total_data_lines)
        self.testing(self.l_total_data_lines, os.path.join(self.out_dir, 'overfit'))

    # def training(self, l_train_lines):
    #     self.model.train(l_train_lines)

    def testing(self, l_test_lines, out_dir):
        l_q_ranking = self.model.predict(l_test_lines)
        rank_out_name = out_dir + '/trec'
        eva_out_name = out_dir + '/eval'
        dump_trec_ranking_with_score(l_q_ranking, rank_out_name)
        eva_str = subprocess.check_output(
            ['perl', GDEVAL_PATH, self.qrel, rank_out_name]).strip()
        print >> open(eva_out_name, 'w'), eva_str.strip()
        __, ndcg, err = seg_gdeval_out(eva_str)

        if self.get_intermediate_res:
            ll_intermediate_res, l_q_d = self.model.predict_intermediate(l_test_lines)
            out = open(os.path.join(out_dir, 'q_docno'), 'w')
            for q, d in l_q_d:
                print >> out, '%s\t%s' % (q, d)
            out.close()
            for name, l_res in ll_intermediate_res:
                out = open(os.path.join(out_dir, 'intermediate_' + name), 'w')
                for res in l_res:
                    print >> out, json.dumps(res.tolist())
                out.close()
                logging.info('intermediate [%s] scores dumped', name)
            logging.info('all intermediate results dumped')
        logging.info('training testing [%s] done with ndcg %f, err %f', out_dir, ndcg, err)
        return

    def run_one_fold(self, fold_k):
        if self.with_dev:
            self.train_dev_test_fold(fold_k)
        else:
            self.train_test_fold(fold_k)

    def _get_dev_para_list(self):
        h_para = {}
        l_l2_w  = self.h_dev_para.get('l2_w', [])
        l_att_layer_nb = self.h_dev_para.get('nb_att_layer', [])
        l_rank_layer_nb = self.h_dev_para.get('nb_rank_layer', [])
        # if len(l_l2_w) * len(l_att_layer_nb) * len(l_rank_layer_nb):
        h_mid = {}
        l_res_paras = []
        dfs_para([l_l2_w, l_att_layer_nb, l_rank_layer_nb],
                 ['l2_w', 'nb_att_layer', 'nb_rank_layer'], 0, h_mid, l_res_paras)
        return l_res_paras


if __name__ == '__main__':
    import sys
    set_basic_log()
    if 3 != len(sys.argv):
        print "cross validate one fold"
        print '2 para: config + fold k'
        CrossValidator.class_print_help()
        sys.exit()

    k = int(sys.argv[2])
    conf = load_py_config(sys.argv[1])
    runner = CrossValidator(config=conf)
    if k == -2:
        runner.overfit()
    else:
        runner.run_one_fold(k)











