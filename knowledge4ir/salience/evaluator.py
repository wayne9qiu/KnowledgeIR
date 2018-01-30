import gzip
import json
from knowledge4ir.utils import add_svm_feature, mutiply_svm_feature
from knowledge4ir.salience.utils.evaluation import SalienceEva
import logging


def open_func(corpus_in):
    return gzip.open if corpus_in.endswith("gz") else open


class JointEvaluator():
    def __init__(self, entity_vocab_size, content_field='bodyText'):
        self.entity_vocab_size = entity_vocab_size
        self.content_field = content_field

    def load_pairs(self, docs, f_predict):
        with open_func(docs)(docs) as origin, open_func(f_predict)(
                f_predict) as pred:
            while True:
                try:
                    inline = origin.next()
                    pred_line = pred.next()

                    doc = json.loads(inline)
                    predict_res = json.loads(pred_line)

                    gold_doc = doc['docno']
                    pred_doc = predict_res['docno']

                    while not gold_doc == pred_doc:
                        # Some results may have skipped empty lines.
                        doc = json.loads(origin.next())
                        gold_doc = doc['docno']
                        yield None

                    # Backward compatibility.
                    if 'predict' in predict_res:
                        predictions = predict_res['predict']
                    else:
                        predictions = predict_res[self.content_field]['predict']

                    l_e = doc['spot']['bodyText']['entities']
                    l_label_e = doc['spot']['bodyText']['salience']
                    s_e_label = dict(zip(l_e, l_label_e))

                    l_evm = doc['event']['bodyText']['sparse_features'].get(
                        'LexicalHead', [])
                    l_label_evm = doc['event']['bodyText']['salience']
                    s_evm_label = dict(zip(l_evm, l_label_evm))
                    yield predictions, s_e_label, s_evm_label

                except StopIteration:
                    break

    def evaluate_normal(self, docs, f_predict):
        print("Evaluating predictions [%s] from [%s]." % (f_predict, docs))
        evaluator = SalienceEva()  # evaluator with default values.

        h_e_total_eva = dict()
        e_p = 0
        p = 0
        skip = 0

        for res in self.load_pairs(docs, f_predict):
            p += 1
            if not res:
                e_p += 1
            else:
                skip += 1
                continue

            predictions, s_e_label, s_evm_label = res

            l_e_pack = self.get_e_labels(predictions, s_e_label)

            if l_e_pack:
                h_e = evaluator.evaluate(l_e_pack[0], l_e_pack[1])
                h_e_total_eva = add_svm_feature(h_e_total_eva, h_e)

            if not e_p == 0:
                h_e_mean_eva = mutiply_svm_feature(h_e_total_eva, 1.0 / e_p)
                sys.stdout.write(
                    '\rEvaluated %d files, %d with entities,'
                    ' %d line skipped. P@1: %s.' % (
                        p, e_p, skip, h_e_mean_eva['p@01']))

        print('')

        h_e_mean_eva = {}
        if not e_p == 0:
            h_e_mean_eva = mutiply_svm_feature(h_e_total_eva, 1.0 / e_p)
            logging.info('finished predicted [%d] docs on entity, eva %s', e_p,
                         json.dumps(h_e_mean_eva))

        res = {'entity': h_e_mean_eva}

        with open(f_predict + '.entity.eval', 'w') as out:
            json.dump(res, out, indent=1)

    def evaluate_json_joint(self, docs, f_predict):
        print("Evaluating joint predictions [%s] from [%s]." % (
            f_predict, docs))

        evaluator = SalienceEva()  # evaluator with default values.

        h_e_total_eva = dict()
        h_e_mean_eva = dict()

        h_evm_total_eva = dict()
        h_evm_mean_eva = dict()

        h_all_total_eva = dict()
        h_all_mean_eva = dict()

        e_p = 0
        evm_p = 0
        all_p = 0
        p = 0

        for res in self.load_pairs(docs, f_predict):
            p += 1

            if not res:
                continue

            predictions, s_e_label, s_evm_label = res

            l_e_pack = self.get_e_labels(predictions, s_e_label)
            l_evm_pack = self.get_evm_labels(predictions, s_evm_label)
            all_pack = zip(*zip(*l_e_pack) + zip(*l_evm_pack))

            if l_e_pack:
                h_e = evaluator.evaluate(l_e_pack[0], l_e_pack[1])
                e_p += 1
                h_e_total_eva = add_svm_feature(h_e_total_eva, h_e)

            if l_evm_pack:
                h_evm = evaluator.evaluate(l_evm_pack[0], l_evm_pack[1])
                evm_p += 1
                h_evm_total_eva = add_svm_feature(h_evm_total_eva, h_evm)

            if all_pack:
                h_all = evaluator.evaluate(all_pack[0],
                                           all_pack[1])
                all_p += 1
                h_all_total_eva = add_svm_feature(h_all_total_eva, h_all)

            if not e_p == 0:
                h_e_mean_eva = mutiply_svm_feature(h_e_total_eva, 1.0 / e_p)
            if not evm_p == 0:
                h_evm_mean_eva = mutiply_svm_feature(h_evm_total_eva,
                                                     1.0 / evm_p)
            if not all_p == 0:
                h_all_mean_eva = mutiply_svm_feature(h_all_total_eva,
                                                     1.0 / all_p)

            ep1 = '%.4f' % h_e_mean_eva[
                'p@01'] if 'p@01' in h_e_mean_eva else 'N/A'
            evmp1 = '%.4f' % h_evm_mean_eva[
                'p@01'] if 'p@01' in h_evm_mean_eva else 'N/A'
            all1 = '%.4f' % h_all_mean_eva[
                'p@01'] if 'p@01' in h_all_mean_eva else 'N/A'

            sys.stdout.write(
                '\rEvaluated %d files, %d with entities and %d '
                'with events, En P@1: %s, Evm P@1: %s, '
                'All P@1: %s.' % (p, e_p, evm_p, ep1, evmp1, all1))

        print('')

        h_e_mean_eva = {}
        if not e_p == 0:
            h_e_mean_eva = mutiply_svm_feature(h_e_total_eva, 1.0 / e_p)
            logging.info('finished predicted [%d] docs on entity, eva %s', e_p,
                         json.dumps(h_e_mean_eva))

        h_evm_mean_eva = {}
        if not evm_p == 0:
            h_evm_mean_eva = mutiply_svm_feature(h_evm_total_eva, 1.0 / evm_p)
            logging.info('finished predicted [%d] docs on event, eva %s', evm_p,
                         json.dumps(h_evm_mean_eva))

        logging.info("Results to copy:")
        line1 = ["p@01", "p@05", "p@10", "p@20", "auc"]
        line2 = ["r@01", "r@05", "r@10", "r@20"]

        line1_evm_scores = ["%.4f" % h_evm_mean_eva[k] for k in line1]
        line1_ent_scores = ["%.4f" % h_e_mean_eva[k] for k in line1]
        line1_all_scores = ["%.4f" % h_all_mean_eva[k] for k in line1]

        line2_evm_scores = ["%.4f" % h_evm_mean_eva[k] for k in line2]
        line2_ent_scores = ["%.4f" % h_e_mean_eva[k] for k in line2]
        line2_all_scores = ["%.4f" % h_all_mean_eva[k] for k in line2]

        print "\t-\t".join(line1_evm_scores) + "\t-\t-\t" + \
              "\t".join(line1_all_scores) + "\t-\t" + \
              "\t".join(line1_ent_scores)

        print "\t-\t".join(line2_evm_scores) + "\t-\t-\t-\t-\t" + \
              "\t".join(line2_all_scores) + "\t-\t-\t" + \
              "\t".join(line2_ent_scores)

        res = {'entity': h_e_mean_eva, 'event': h_evm_mean_eva}

        with open(f_predict + '.joint.eval', 'w') as out:
            json.dump(res, out, indent=1)

    def get_e_labels(self, predictions, s_e_label):
        e_list = []

        for pred in predictions:
            eid = pred[0]
            score = pred[1]
            if eid < self.entity_vocab_size:
                e_list.append((score, s_e_label[eid], eid))
        return zip(*e_list)

    def get_evm_labels(self, predictions, s_evm_label):
        evm_list = []

        for pred in predictions:
            eid = pred[0]
            score = pred[1]
            if eid >= self.entity_vocab_size:
                evm_list.append((score,
                                 s_evm_label[eid - self.entity_vocab_size],
                                 eid - self.entity_vocab_size))
        return zip(*evm_list)

    def split_joint_list(self, entity_vocab_size, predictions, s_e_label,
                         s_evm_label):
        e_list = []
        evm_list = []

        for pred in predictions:
            eid = pred[0]
            score = pred[1]
            if eid >= entity_vocab_size:
                evm_list.append((score, s_evm_label[eid - entity_vocab_size],
                                 eid - entity_vocab_size))
            else:
                e_list.append((score, s_e_label[eid], eid))

        return zip(*e_list), zip(*evm_list)


if __name__ == '__main__':
    import sys

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)

    args = sys.argv
    if len(args) < 4:
        print(
            "Usage: [this script] [joint|normal] [gold standard] [prediction] "
            "[Default: 723749 entity vocab size]")
        exit(1)

    vocab_size = 723749 if len(args) < 5 else int(args[4])

    evaluator = JointEvaluator(vocab_size)

    if args[1] == 'joint':
        print("Going to evaluate a joint result.")
        evaluator.evaluate_json_joint(args[2], args[3])
    else:
        print("Going to evaluate a normal result.")
        evaluator.evaluate_normal(args[2], args[3])
