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

import numpy as np
import torch
from traitlets import (
    Unicode,
    Int,
    Float,
    List,
)
from traitlets.config import Configurable

from knowledge4ir.salience.base import NNPara
from knowledge4ir.salience.baseline.baseline_model import (
    FrequencySalience,
)
from knowledge4ir.salience.baseline.dense_model import EmbeddingLR
from knowledge4ir.salience.baseline.dense_model import (
    FeatureLR,
)
from knowledge4ir.salience.baseline.local_context import (
    LocalAvgWordVotes,
    LocalRNNVotes,
    LocalRNNMaxSim,
)
from knowledge4ir.salience.baseline.translation_model import (
    EmbPageRank,
    EdgeCNN,
)
from knowledge4ir.salience.crf_model import (
    KernelCRF,
    LinearKernelCRF,
)
from knowledge4ir.salience.kernel_graph_cnn import (
    KernelGraphCNN,
    KernelGraphWalk,
    HighwayKCNN,
)
from knowledge4ir.salience.utils.data_io import (
    raw_io,
    feature_io,
    uw_io,
)
from knowledge4ir.salience.utils.evaluation import SalienceEva
from knowledge4ir.salience.utils.ranking_loss import (
    hinge_loss,
    pairwise_loss,
)
from knowledge4ir.utils import add_svm_feature, mutiply_svm_feature
from knowledge4ir.utils import (
    body_field,
    abstract_field,
)

use_cuda = torch.cuda.is_available()


class SalienceModelCenter(Configurable):
    learning_rate = Float(1e-3, help='learning rate').tag(config=True)
    pre_trained_emb_in = Unicode(help='pre-trained embedding').tag(config=True)
    model_name = Unicode(help="model name: trans").tag(config=True)
    nb_epochs = Int(2, help='nb of epochs').tag(config=True)
    l_class_weights = List(Float, default_value=[1, 10]).tag(config=True)
    batch_size = Int(128, help='number of documents per batch').tag(config=True)
    loss_func = Unicode('hinge', help='loss function to use: hinge, pairwise').tag(config=True)
    early_stopping_patient = Int(5, help='epochs before early stopping').tag(config=True)
    max_e_per_doc = Int(200, help='max e per doc')
    input_format = Unicode('raw', help='input format: raw | featured').tag(config=True)
    h_model = {
        "trans": EmbPageRank,  # not working
        'EdgeCNN': EdgeCNN,  # not working
        'lr': EmbeddingLR,   # not working
        'knrm': KernelGraphCNN,
        'kernel_pr': KernelGraphWalk,  # not working
        'highway_knrm': HighwayKCNN,
        'frequency': FrequencySalience,
        'feature_lr': FeatureLR,
        'kcrf': KernelCRF,  # not working
        'linear_kcrf': LinearKernelCRF,
        "avg_local_vote": LocalAvgWordVotes,
        'local_rnn': LocalRNNVotes,
        'local_max_rnn': LocalRNNMaxSim
    }
    in_field = Unicode(body_field)
    salience_field = Unicode(abstract_field)
    spot_field = Unicode('spot')

    def __init__(self, **kwargs):
        super(SalienceModelCenter, self).__init__(**kwargs)
        self.para = NNPara(**kwargs)
        h_loss = {
            "hinge": hinge_loss,
            "pairwise": pairwise_loss,
        }
        self.h_io_func = {
            'raw': raw_io,
            'featured': feature_io,
            'loc': uw_io,
        }
        self.criterion = h_loss[self.loss_func]
        self.evaluator = SalienceEva(**kwargs)
        self.pre_emb = None
        if self.pre_trained_emb_in:
            logging.info('loading pre trained embedding [%s]', self.pre_trained_emb_in)
            self.pre_emb = np.load(open(self.pre_trained_emb_in))
            logging.info('loaded with shape %s', json.dumps(self.pre_emb.shape))
            if not self.para.embedding_dim:
                self.para.entity_vocab_size, self.para.embedding_dim = self.pre_emb.shape
            assert self.para.entity_vocab_size == self.pre_emb.shape[0]
            assert self.para.embedding_dim == self.pre_emb.shape[1]
        self.model = None
        self._init_model()
        self.class_weight = torch.cuda.FloatTensor(self.l_class_weights)

    @classmethod
    def class_print_help(cls, inst=None):
        super(SalienceModelCenter, cls).class_print_help(inst)
        NNPara.class_print_help(inst)
        SalienceEva.class_print_help(inst)

    def _init_model(self):
        if self.model_name:
            self.model = self.h_model[self.model_name](self.para,
                                                       self.pre_emb,
                                                       )
            logging.info('use model [%s]', self.model_name)

    def train(self, train_in_name, validation_in_name=None, model_out_name=None):
        """
        train using the given data
        will use each doc as the mini-batch for now
        :param train_in_name: training data
        :param validation_in_name: validation data
        :param model_out_name: name to dump the model
        :return: keep the model
        """
        logging.info('training with data in [%s]', train_in_name)
        patient_cnt = 0
        best_valid_loss = None
        if validation_in_name:
            logging.info('loading validation data from [%s]', validation_in_name)
            l_valid_lines = open(validation_in_name).read().splitlines()
            ll_valid_line = [l_valid_lines[i:i + self.batch_size]
                             for i in xrange(0, len(l_valid_lines), self.batch_size)]
            # valid_e, valid_w, valid_label = self._data_io(l_valid_lines)
            logging.info('validation with [%d] doc', len(l_valid_lines))
            patient_cnt = 0
            best_valid_loss = sum([self._batch_test(l_one_batch)
                                   for l_one_batch in ll_valid_line]) / float(len(ll_valid_line))
            logging.info('initial validation loss [%.4f]', best_valid_loss)

        optimizer = torch.optim.Adam(
            filter(lambda model_para: model_para.requires_grad, self.model.parameters()),
            lr=self.learning_rate
        )
        l_epoch_loss = []
        for epoch in xrange(self.nb_epochs):
            p = 0
            total_loss = 0
            data_cnt = 0
            logging.info('start epoch [%d]', epoch)
            l_this_batch_line = []
            for line in open(train_in_name):
                if self._filter_empty_line(line):
                    continue
                data_cnt += 1
                l_this_batch_line.append(line)
                if len(l_this_batch_line) >= self.batch_size:
                    this_loss = self._batch_train(l_this_batch_line, self.criterion, optimizer)
                    p += 1
                    total_loss += this_loss
                    logging.debug('[%d] batch [%f] loss', p, this_loss)
                    assert not math.isnan(this_loss)
                    if not p % 100:
                        logging.info('batch [%d] [%d] data, average loss [%f]',
                                     p, data_cnt, total_loss / p)
                    l_this_batch_line = []

            if l_this_batch_line:
                this_loss = self._batch_train(l_this_batch_line, self.criterion, optimizer)
                p += 1
                total_loss += this_loss
                logging.debug('[%d] batch [%f] loss', p, this_loss)
                assert not math.isnan(this_loss)
                l_this_batch_line = []

            logging.info('epoch [%d] finished with loss [%f] on [%d] batch [%d] doc',
                         epoch, total_loss / p, p, data_cnt)
            l_epoch_loss.append(total_loss / p)

            # validation
            if validation_in_name:
                this_valid_loss = sum([self._batch_test(l_one_batch)
                                       for l_one_batch in ll_valid_line]) / float(len(ll_valid_line))
                logging.info('valid loss [%f]', this_valid_loss)
                if best_valid_loss is None:
                    best_valid_loss = this_valid_loss
                elif this_valid_loss > best_valid_loss:
                    patient_cnt += 1
                    logging.info('valid loss increased [%.4f -> %.4f][%d]',
                                 best_valid_loss, this_valid_loss, patient_cnt)
                    if patient_cnt >= self.early_stopping_patient:
                        logging.info('early stopped at [%d] epoch', epoch)
                        break
                else:
                    patient_cnt = 0
                    logging.info('valid loss decreased [%.4f -> %.4f][%d]',
                                 best_valid_loss, this_valid_loss, patient_cnt)
                    best_valid_loss = this_valid_loss

        logging.info('[%d] epoch done with loss %s', self.nb_epochs, json.dumps(l_epoch_loss))

        if model_out_name:
            self.model.save_model(model_out_name)
        return

    def _batch_train(self, l_line, criterion, optimizer):
        h_packed_data, m_label = self._data_io(l_line)
        optimizer.zero_grad()
        output = self.model(h_packed_data)
        # logging.debug('predicted: %s',
        #               json.dumps(output.data.cpu().numpy().tolist()))
        # logging.debug('target: %s',
        #               json.dumps(m_label.data.cpu().numpy().tolist()))
        loss = criterion(output, m_label)
        # logging.debug('loss: %s',
        #               json.dumps(loss.data.cpu().numpy().tolist()))
        loss.backward()
        optimizer.step()
        assert not math.isnan(loss.data[0])
        return loss.data[0]

    def predict(self, test_in_name, label_out_name):
        """
        predict the data in test_in,
        dump predict labels in label_out_name
        :param test_in_name:
        :param label_out_name:
        :return:
        """

        out = open(label_out_name, 'w')
        logging.info('start predicting for [%s]', test_in_name)
        p = 0
        h_total_eva = dict()
        for line in open(test_in_name):
            if self._filter_empty_line(line):
                continue
            h_out, h_this_eva = self._per_doc_predict(line)
            if h_out is None:
                continue
            h_total_eva = add_svm_feature(h_total_eva, h_this_eva)
            print >> out, json.dumps(h_out)
            p += 1
            h_mean_eva = mutiply_svm_feature(h_total_eva, 1.0 / p)
            if not p % 1000:
                logging.info('predicted [%d] docs, eva %s', p, json.dumps(h_mean_eva))
        h_mean_eva = mutiply_svm_feature(h_total_eva, 1.0 / p)
        logging.info('finished predicted [%d] docs, eva %s', p, json.dumps(h_mean_eva))
        json.dump(
            h_mean_eva,
            open(label_out_name + '.eval', 'w'),
            indent=1
        )
        out.close()
        return

    def _per_doc_predict(self, line):
        docno = json.loads(line)['docno']
        h_packed_data, v_label = self._data_io([line])
        v_e = h_packed_data['mtx_e']
        # v_w = h_packed_data['mtx_score']
        if (not v_e[0].size()) | (not v_label[0].size()):
            return None, None
        output = self.model(h_packed_data).cpu()[0]
        v_e = v_e[0].cpu()
        v_label = v_label[0].cpu()
        # pre_label = output.data.max(-1)[1]
        pre_label = output.data.sign().type(torch.LongTensor)
        l_score = output.data.numpy().tolist()
        y = v_label.data.view_as(pre_label)
        l_label = y.numpy().tolist()

        h_out = dict()
        h_out['docno'] = docno

        l_e = v_e.data.numpy().tolist()
        l_res = pre_label.numpy().tolist()
        h_out['predict'] = zip(l_e, zip(l_score, l_res))
        h_this_eva = self.evaluator.evaluate(l_score, l_label)
        h_out['eval'] = h_this_eva
        return h_out, h_this_eva

    def _batch_test(self, l_lines):
        h_packed_data, m_label = self._data_io(l_lines)
        # m_e, m_w = h_packed_data['mtx_e'], h_packed_data['mtx_score']
        output = self.model(h_packed_data)
        loss = self.criterion(output, m_label)
        return loss.data[0]

    def _filter_empty_line(self, line):
        h = json.loads(line)
        if self.input_format == 'raw':
            l_e = h[self.spot_field].get(self.in_field, [])
        else:
            l_e = h[self.spot_field].get(self.in_field, {}).get('entities')
        return not l_e

    def _data_io(self, l_line):
        return self.h_io_func[self.input_format](
            l_line, self.spot_field, self.in_field, self.salience_field, self.max_e_per_doc
        )


if __name__ == '__main__':
    import sys
    from knowledge4ir.utils import (
        set_basic_log,
        load_py_config,
    )
    set_basic_log(logging.DEBUG)

    class Main(Configurable):
        train_in = Unicode(help='training data').tag(config=True)
        test_in = Unicode(help='testing data').tag(config=True)
        test_out = Unicode(help='test res').tag(config=True)
        valid_in = Unicode(help='validation in').tag(config=True)
        model_out = Unicode(help='model dump out name').tag(config=True)

    if 2 != len(sys.argv):
        print "unit test model train test"
        print "1 para, config"
        SalienceModelCenter.class_print_help()
        Main.class_print_help()
        sys.exit(-1)

    conf = load_py_config(sys.argv[1])
    para = Main(config=conf)
    model = SalienceModelCenter(config=conf)
    model.train(para.train_in, para.valid_in, para.model_out)
    model.predict(para.test_in, para.test_out)