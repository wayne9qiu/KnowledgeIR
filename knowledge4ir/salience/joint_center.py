"""
model I/O, train, and testing center
train:
    hashed nyt data
        three field:
            docno:
            body: l_e
            abstract: l_e
    and train the model
test:
    hashed nyt data
    output the scores for entities in body

hyper-parameters:
    mini-batch size
    learning rate
    vocabulary size
    embedding dim

"""

import json
import logging
import math
import os

import numpy as np
import torch
from traitlets import (
    Unicode,
    Int,
    Float,
    List,
    Bool
)
from traitlets.config import Configurable

from knowledge4ir.salience.center import SalienceModelCenter
from knowledge4ir.salience.graph_model import (
    MaskKernelCrf,

    AverageEventKernelCRF,
    AverageArgumentKernelCRF,

    GraphCNNKernelCRF,
    ConcatGraphCNNKernelCRF,
)
from knowledge4ir.salience.utils.joint_data_io import EventDataIO

from knowledge4ir.utils import (
    add_svm_feature,
    mutiply_svm_feature,
)

use_cuda = torch.cuda.is_available()


class JointSalienceModelCenter(SalienceModelCenter):

    def __init__(self, **kwargs):
        joint_models = {
            'masked_linear_kcrf': MaskKernelCrf,

            'kcrf_event_average': AverageEventKernelCRF,
            'kcrf_args_average': AverageArgumentKernelCRF,

            'kcrf_event_gcnn': GraphCNNKernelCRF,
            'kcrf_event_gcnn_concat': ConcatGraphCNNKernelCRF,
        }
        self.h_model.update(joint_models)
        super(JointSalienceModelCenter, self).__init__(**kwargs)

    def _setup_io(self, **kwargs):
        self.io_parser = EventDataIO(**kwargs)

    def _init_model(self):
        if self.model_name:
            self._merge_para()
            self.model = self.h_model[self.model_name](self.para, self.ext_data)
            logging.info('use model [%s]', self.model_name)

    def predict(self, test_in_name, label_out_name, debug=False):
        """
        predict the data in test_in,
        dump predict labels in label_out_name
        :param test_in_name:
        :param label_out_name:
        :param debug:
        :return:
        """
        res_dir = os.path.dirname(label_out_name)
        if not os.path.exists(res_dir):
            os.makedirs(res_dir)

        self.model.debug_mode(debug)

        out = open(label_out_name, 'w')
        logging.info('start predicting for [%s]', test_in_name)
        p = 0
        h_total_eva = dict()
        for line in open(test_in_name):
            if self.io_parser.is_empty_line(line):
                continue
            h_out, h_this_eva = self._per_doc_predict(line)
            if h_out is None:
                continue
            h_total_eva = add_svm_feature(h_total_eva, h_this_eva)
            if debug:
                print json.dumps(h_out)
                import sys
                sys.stdin.readline()

            print >> out, json.dumps(h_out)
            p += 1
            h_mean_eva = mutiply_svm_feature(h_total_eva, 1.0 / p)
            if not p % 1000:
                logging.info('predicted [%d] docs, eva %s', p,
                             json.dumps(h_mean_eva))
        h_mean_eva = mutiply_svm_feature(h_total_eva, 1.0 / max(p, 1.0))
        l_mean_eva = h_mean_eva.items()
        l_mean_eva.sort(key=lambda item: item[0])
        logging.info('finished predicted [%d] docs, eva %s', p,
                     json.dumps(l_mean_eva))
        json.dump(
            l_mean_eva,
            open(label_out_name + '.eval', 'w'),
            indent=1
        )
        out.close()
        return

    def _per_doc_predict(self, line):
        h_info = json.loads(line)
        key_name = 'docno'
        if key_name not in h_info:
            key_name = 'qid'
            assert key_name in h_info
        docno = h_info[key_name]
        h_packed_data, v_label = self._data_io([line])

        if not v_label[0].size():
            return None, None
        v_label = v_label[0].cpu()

        mtx_e = h_packed_data['mtx_e']
        v_e = mtx_e[0].cpu().data.numpy().tolist()

        v_evm = []
        if 'mtx_evm' in h_packed_data:
            mtx_evm = h_packed_data['mtx_evm']
            if mtx_evm is not None:
                v_evm = mtx_evm[0].cpu().data.numpy().tolist()

        output = self.model(h_packed_data).cpu()[0]

        pre_label = output.data.sign().type(torch.LongTensor)
        l_score = output.data.numpy().tolist()

        h_out = dict()
        h_out[key_name] = docno
        l_e = v_e + v_evm
        # l_e = [e - 1 for e in l_e]
        h_out[self.io_parser.content_field] = {'predict': zip(l_e, l_score)}

        # if self.predict_with_intermediate_res:
        #     middle_output = \
        #         self.model.forward_intermediate(h_packed_data).cpu()[0]
        #     l_middle_features = middle_output.data.numpy().tolist()
        #     h_out[self.io_parser.content_field][
        #         'predict_features'] = zip(l_e, l_middle_features)

        y = v_label.data.view_as(pre_label)
        l_label = y.numpy().tolist()
        h_this_eva = self.evaluator.evaluate(l_score, l_label)
        h_out['eval'] = h_this_eva
        return h_out, h_this_eva

    def _data_io(self, l_line):
        return self.model.data_io(l_line, self.io_parser)


if __name__ == '__main__':
    import sys
    from knowledge4ir.utils import (
        set_basic_log,
        load_py_config,
    )


    class Main(Configurable):
        train_in = Unicode(help='training data').tag(config=True)
        test_in = Unicode(help='testing data').tag(config=True)
        test_out = Unicode(help='test res').tag(config=True)
        valid_in = Unicode(help='validation in').tag(config=True)
        model_out = Unicode(help='model dump out name').tag(config=True)
        log_level = Unicode('INFO', help='log level').tag(config=True)
        skip_train = Bool(False, help='directly test').tag(config=True)
        debug = Bool(False, help='Debug mode').tag(config=True)


    if 2 != len(sys.argv):
        print "unit test model train test"
        print "1 para, config"
        JointSalienceModelCenter.class_print_help()
        Main.class_print_help()
        sys.exit(-1)

    conf = load_py_config(sys.argv[1])
    para = Main(config=conf)

    set_basic_log(logging.getLevelName(para.log_level))

    model = JointSalienceModelCenter(config=conf)

    model_loaded = False
    if para.skip_train:
        print 'Trying to load existing model.'
        if os.path.exists(para.model_out):
            model.load_model(para.model_out)
            model_loaded = True

    if not model_loaded:
        print 'Start to run training.'
        model.train(para.train_in, para.valid_in, para.model_out)

    model.predict(para.test_in, para.test_out, para.debug)
