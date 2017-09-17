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

from knowledge4ir.salience.translation_model import (
    GraphTranslation,
    BachPageRank,
    EdgeCNN,
)
from traitlets.config import Configurable
from traitlets import (
    Unicode,
    Int,
    Float,
    List,
)
import numpy as np
import json
import logging
from knowledge4ir.utils import (
    body_field,
    abstract_field,
    term2lm,
)
import math
import torch
from torch.autograd import Variable
from torch import nn
import torch.nn.functional as F
from knowledge4ir.salience.utils import hinge_loss
use_cuda = torch.cuda.is_available()


class SalienceModelCenter(Configurable):
    learning_rate = Float(1e-3, help='learning rate').tag(config=True)
    pre_trained_emb_in = Unicode(help='pre-trained embedding').tag(config=True)
    model_name = Unicode(help="model name: trans").tag(config=True)
    random_walk_step = Int(1, help='random walk step').tag(config=True)  # need to be a config para
    nb_epochs = Int(2, help='nb of epochs').tag(config=True)
    l_class_weights = List(Float, default_value=[1, 10]).tag(config=True)
    batch_size = Int(128, help='number of documents per batch').tag(config=True)

    max_e_per_doc = Int(1000, help='max e per doc')
    h_model = {
        "trans": BachPageRank,
        'EdgeCNN': EdgeCNN,
    }
    in_field = Unicode(body_field)
    salience_field = Unicode(abstract_field)
    spot_field = Unicode('spot')

    def __init__(self, **kwargs):
        super(SalienceModelCenter, self).__init__(**kwargs)
        self.pre_emb = None
        if self.pre_trained_emb_in:
            logging.info('loading pre trained embedding [%s]', self.pre_trained_emb_in)
            self.pre_emb = np.load(open(self.pre_trained_emb_in))
            logging.info('loaded with shape %s', json.dumps(self.pre_emb.shape))
        self.model = None
        self._init_model()
        self.class_weight = torch.cuda.FloatTensor(self.l_class_weights)

    def _init_model(self):
        if self.model_name:
            self.model = self.h_model[self.model_name](self.random_walk_step,
                                                       self.pre_emb.shape[0],
                                                       self.pre_emb.shape[1],
                                                       self.pre_emb,
                                                       )

    def train(self, train_in_name):
        """
        train using the given data
        will use each doc as the mini-batch for now
        :param train_in_name:
        :return: keep the model
        """
        logging.info('training with data in [%s]', train_in_name)
        # criterion = nn.NLLLoss(weight=self.class_weight)
        criterion = hinge_loss
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
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
                    this_loss = self._batch_train(l_this_batch_line, criterion, optimizer)
                    p += 1
                    total_loss += this_loss
                    logging.debug('[%d] batch [%f] loss', p, this_loss)
                    assert not math.isnan(this_loss)
                    if not p % 1000:
                        logging.info('batch [%d] [%d] data, average loss [%f]', p, data_cnt, total_loss / p)
                    l_this_batch_line = []

            if l_this_batch_line:
                this_loss = self._batch_train(l_this_batch_line, criterion, optimizer)
                p += 1
                total_loss += this_loss
                logging.debug('[%d] batch [%f] loss', p, this_loss)
                assert not math.isnan(this_loss)
                l_this_batch_line = []

            logging.info('epoch [%d] finished with loss [%f] on [%d] batch [%d] doc',
                         epoch, total_loss / p, p, data_cnt)
            l_epoch_loss.append(total_loss / p)

        logging.info('[%d] epoch done with loss %s', self.nb_epochs, json.dumps(l_epoch_loss))
        return

    def _batch_train(self, l_line, criterion, optimizer):
        m_e, m_w, m_label = self._data_io(l_line)
        optimizer.zero_grad()
        output = self.model(m_e, m_w)
        # loss = criterion(
        #     output.view(-1, output.size()[-1]),
        #     m_label.view(-1, 1).squeeze(-1)
        #                  )
        loss = criterion(output, m_label)
        loss.backward()
        # nn.utils.clip_grad_norm(self.model.parameters(), 10)
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
        total_accuracy, total_precision, total_recall = 0, 0, 0
        p = 0
        for line in open(test_in_name):
            if self._filter_empty_line(line):
                continue
            docno = json.loads(line)['docno']
            v_e, v_w, v_label = self._data_io([line])
            if (not v_e[0].size()) | (not v_label[0].size()):
                continue
            output = self.model(v_e, v_w).cpu()[0]
            v_e = v_e[0].cpu()
            v_label = v_label[0].cpu()
            # pre_label = output.data.max(-1)[1]
            pre_label = output.data.sign().type(torch.LongTensor)
            score = output.data
            h_out = dict()
            h_out['docno'] = docno
            l_e = v_e.data.numpy().tolist()
            l_res = pre_label.numpy().tolist()

            h_out['predict'] = zip(l_e, zip(score.numpy().tolist(), l_res))
            print >> out, json.dumps(h_out)
            y = v_label.data.view_as(pre_label)
            correct = pre_label.eq(y).sum()
            precision = (
                (pre_label.eq(y)) * (pre_label.eq(1))
            ).sum()

            recall = (
                (pre_label.eq(y)) * (y.eq(1))
            ).sum()
            this_acc = correct / float(len(l_e))
            this_pre = precision / max(pre_label.sum(), 1.0)
            this_recall = recall / max(y.sum(), 1.0)
            total_accuracy += this_acc
            total_precision += this_pre
            total_recall += this_recall
            p += 1
            # logging.debug('doc [%d][%s] accuracy [%f]', p, docno, this_acc)
            if not p % 1000:
                logging.info('predicted [%d] docs, accuracy [%f], precision [%f], recall [%f]', p,
                             total_accuracy / p, total_precision / p, total_recall / p)
        logging.info('finished predicting [%d] docs, accuracy [%f], precision [%f], recall [%f]', p,
                     total_accuracy / p, total_precision / p, total_recall / p)
        out.close()
        return

    def _filter_empty_line(self, line):
        h = json.loads(line)
        l_e = h[self.spot_field].get(self.in_field, [])
        return not l_e

    def _data_io(self, l_line):
        """
        convert data to the input for the model
        :param line: the json formatted data
        :return: v_e, v_w, v_label
        v_e: entities in the doc
        v_w: initial weight, TF
        v_label: 1 or -1, salience or not, if label not given, will be 0
        """
        ll_e = []
        ll_w = []
        ll_label = []
        for line in l_line:
            h = json.loads(line)
            l_e = h[self.spot_field].get(self.in_field, [])
            s_salient_e = set(h[self.spot_field].get(self.salience_field, []))
            h_e_tf = term2lm(l_e)
            l_e_tf = sorted(h_e_tf.items(), key=lambda item: -item[1])[:self.max_e_per_doc]
            l_e = [item[0] for item in l_e_tf]
            z = float(sum([item[1] for item in l_e_tf]))
            l_w = [item[1] / z for item in l_e_tf]
            l_label = [1 if e in s_salient_e else -1 for e in l_e]
            ll_e.append(l_e)
            ll_w.append(l_w)
            ll_label.append(l_label)

        ll_e = self._padding(ll_e, 0)
        ll_w = self._padding(ll_w, 0)
        ll_label = self._padding(ll_label, 0)

        m_e = Variable(torch.LongTensor(ll_e)).cuda() if use_cuda else Variable(torch.LongTensor(ll_e))
        m_w = Variable(torch.FloatTensor(ll_w)).cuda() if use_cuda else Variable(torch.FloatTensor(ll_w))
        m_label = Variable(torch.LongTensor(ll_label)).cuda() if use_cuda else Variable(torch.FloatTensor(ll_label))
        return m_e, m_w, m_label

    def _padding(self,ll, filler):
        n = max([len(l) for l in ll])
        for i in xrange(len(ll)):
            ll[i] += [filler] * (n - len(ll[i]))
        return ll


if __name__ == '__main__':
    import sys
    from knowledge4ir.utils import (
        set_basic_log,
        load_py_config,
    )
    set_basic_log(logging.INFO)

    class Main(Configurable):
        train_in = Unicode(help='training data').tag(config=True)
        test_in = Unicode(help='testing data').tag(config=True)
        test_out = Unicode(help='test res').tag(config=True)

    if 2 != len(sys.argv):
        print "unit test model train test"
        print "1 para, config"
        SalienceModelCenter.class_print_help()
        Main.class_print_help()
        sys.exit(-1)

    conf = load_py_config(sys.argv[1])
    para = Main(config=conf)
    model = SalienceModelCenter(config=conf)
    model.train(para.train_in)
    model.predict(para.test_in, para.test_out)