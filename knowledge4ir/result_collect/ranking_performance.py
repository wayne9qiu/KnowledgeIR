"""
analysis ranking performance

overall table
p-value
win/tie/loss

input:
    for each run
        a folder/
            eval.d01,- eval.d20
    name of each run
"""

from traitlets import (
    Unicode,
    Int,
    List,
)
from traitlets.config import Configurable
from knowledge4ir.utils import (
    load_gdeval_res,
)
from knowledge4ir.result_collect import (
    randomization_test,
    win_tie_loss,
)
import logging
import os


class RankingPerformanceCollector(Configurable):
    result_dir = Unicode(help='result dir').tag(config=True)
    l_run_name = List(Unicode, help='run names').tag(config=True)
    baseline_name = Unicode(help='base line name').tag(config=True)
    l_sig_test_name = List(Unicode,
                           help='list of runs for all others to test statistical significance'
                           ).tag(config=True)
    l_sig_symbol = List(Unicode,
                        default_value=['\\dagger', '\\ddagger',
                                       '\\mathsection', '\\mathparagraph',
                                       '*', '**'],
                        help='symbols to indicate significances'
                        ).tag(config=True)
    out_dir = Unicode(help='out directory').tag(config=True)

    l_target_metric = List(Unicode, default_value=['ndcg', 'err']).tag(config=True)
    l_target_depth = List(Int, default_value=[1, 5, 10, 20]).tag(config=True)
    eva_prefix = Unicode('eval.d')
    sig_str = Unicode('\dagger')

    def __init__(self, **kwargs):
        super(RankingPerformanceCollector, self).__init__(**kwargs)
        self.l_run_h_eval_per_q = []  # h_eval{'metric': l_q_score in qid order}
        self.l_run_h_eval = []  # h_eval{'metric': score}
        self.h_base_eval_per_q = []
        self.h_base_eval = []
        self.l_to_comp_run_p = [self.l_run_name.index(name) for name in self.l_sig_test_name]

    def _load_eva_results(self):
        self.h_base_eval_per_q, self.h_base_eval = self._load_per_run_results(self.baseline_name)
        for run_name in self.l_run_name:
            h_eval_per_q, h_eval = self._load_per_run_results(run_name)
            self.l_run_h_eval_per_q.append(h_eval_per_q)
            self.l_run_h_eval.append(h_eval)

        return

    def _load_per_run_results(self, run_name):
        run_dir = os.path.join(self.result_dir, run_name)
        h_eval_per_q = dict()
        h_eval = dict()
        for depth in self.l_target_depth:
            eva_res_name = os.path.join(run_dir, self.eva_prefix + '%02d' % depth)
            l_q_eva, ndcg, err = load_gdeval_res(eva_res_name)
            l_q_eva.sort(key=lambda item: int(item[0]))
            l_ndcg = [item[1][0] for item in l_q_eva]
            l_err = [item[1][1] for item in l_q_eva]
            for metric in self.l_target_metric:
                name = metric + '%02d' % depth
                if metric == 'ndcg':
                    h_eval_per_q[name] = l_ndcg
                    h_eval[name] = ndcg
                elif metric == 'err':
                    h_eval_per_q[name] = l_err
                    h_eval[name] = err
                else:
                    logging.error('[%s] metric not implemented', metric)
                    raise NotImplementedError

        return h_eval_per_q, h_eval

    def csv_overall_performance_table(self):
        self._load_eva_results()
        if not os.path.exists(self.out_dir):
            os.makedirs(self.out_dir)
        out = open(self.out_dir +'/overall.csv', 'w')

        header = "\\bf{Method}"
        for eva_metric in self.l_target_metric:
            for d in self.l_target_depth:
                metric = eva_metric.upper() + '@%2d' % d
                header += '& \\bf{%s}' % metric + '& &\\bf{W/T/L}'

        # for metric in [self.target_metric.upper() + '@%2d' % d for d in self.l_target_depth]:
        #     header += '& \\bf{%s}' % metric + '& &\\bf{W/T/L}'
        print >> out, header + '\\\\ \\hline'
        print header + '\\\\ \\hline'
        for run_name in self.l_run_name:
            print >> out, self._overall_performance_per_run(run_name) + '\\\\'
            print self._overall_performance_per_run(run_name) + '\\\\'
        out.close()

        return

    def _overall_performance_per_run(self, run_name):
        """
        score (with , relative %, w/t/l
        :param run_name:
        :return:
        """
        res_str = '\\texttt{%s}\n' % run_name.replace('_', "\\_")
        if run_name != self.baseline_name:
            p = self.l_run_name.index(run_name)
            h_eval_per_q = self.l_run_h_eval_per_q[p]
            h_eval = self.l_run_h_eval[p]
        else:
            h_eval = self.h_base_eval
            h_eval_per_q = self.h_base_eval_per_q
        wtl_str = ""
        for d in self.l_target_depth:
            for eva_metric in self.l_target_metric:
                metric = eva_metric + '%02d' % d
                score = h_eval[metric]
                if run_name == self.baseline_name:
                    res_str += ' & $%.4f$ & -- ' % score
                    # if d == 20:
                    #     res_str += ' & --/--/--'
                    continue
                l_base_q_score = self.h_base_eval_per_q[metric]
                base_score = self.h_base_eval[metric]
                l_q_score = h_eval_per_q[metric]
                rel = float(score) / base_score - 1

                w, t, l = win_tie_loss(l_q_score, l_base_q_score)

                # if rel > 0:
                #     p_value = randomization_test(l_q_score, l_base_q_score)
                # else:
                #     p_value = randomization_test(l_base_q_score, l_q_score)

                # if p_value <= 0.05:
                #     score_str = '${%.4f}^%s$' % (score, self.sig_str)
                # else:
                #     score_str = '${%.4f}$' % score
                sig_mark = self._calc_sig_mark(l_q_score, metric)
                if sig_mark:
                    score_str = '${%.4f}^%s$' % (score, sig_mark)
                else:
                    score_str = '${%.4f}$' % score
                res_str += ' & ' + ' & '.join([
                    score_str,
                    "$ {0:+.2f}\\%  $ ".format(rel * 100),
                ]) + '\n\n'
                if (d == 20) & (eva_metric == 'ndcg'):
                    wtl_str = '& %02d/%02d/%02d\n\n' % (w, t, l)

        res_str += wtl_str

        return res_str

    def _calc_sig_mark(self, l_q_score, metric):
        sig_mark = ""

        assert len(self.l_to_comp_run_p) <= len(self.l_sig_symbol)

        for i in xrange(len(self.l_to_comp_run_p)):
            run_p = self.l_to_comp_run_p[i]
            l_cmp_q_score = self.l_run_h_eval_per_q[run_p][metric]
            if sum(l_q_score) <= sum(l_cmp_q_score):
                # only test improvements
                continue
            p_value = randomization_test(l_q_score, l_cmp_q_score)
            if p_value < 0.05:
                sig_mark += self.l_sig_symbol[i] + ' '

        if sig_mark:
            sig_mark = '{' + sig_mark + "}"
        return sig_mark


if __name__ == '__main__':
    import sys
    from knowledge4ir.utils import (
        load_py_config,
        set_basic_log,
    )
    set_basic_log()
    if 2 > len(sys.argv):
        RankingPerformanceCollector.class_print_help()
        print "can list baseline and run name after conf parameter"
        sys.exit()

    conf = load_py_config(sys.argv[1])
    collector = RankingPerformanceCollector(config=conf)
    if len(sys.argv) == 2:
        collector.csv_overall_performance_table()
    else:
        baseline = sys.argv[2]
        run_name = sys.argv[3]
        collector.baseline_name = baseline
        collector.l_run_name = [run_name]
        collector.out_dir = os.path.join(collector.out_dir, run_name)
        collector.csv_overall_performance_table()






