"""
knrm with attention
"""
import numpy as np
from keras import Input
from keras.engine import Model
from keras.layers import Dense, concatenate, Reshape, multiply
from keras.legacy.layers import Merge
from keras.models import Sequential
from traitlets import Bool, Int

from knowledge4ir.knrm.distance_metric import DiagnalMetric
from knowledge4ir.knrm.kernel_pooling import KernelPooling, KpLogSum
from knowledge4ir.knrm.model import KNRM
import logging


class AttKNRM(KNRM):
    """
    attention version of KNRM
    will directly take input of the calculated translation matrix
        q-d field matrix
    can config whether to use attention or not
    q att and d att is to be multiplied to the kernel pooled raw score tensors,
        alone corresponding dimension (q:1, d:2)
    attention mechanism is a dense layer with input features for now (06/22/2017)
    """
    translation_mtx_in = 'translation_mtx'
    with_attention = Bool(False, help='whether to use attention').tag(config=True)
    att_dim = Int(7, help='attention feature dimension').tag(config=True)

    def __init__(self, **kwargs):
        super(AttKNRM, self).__init__(**kwargs)
        self.s_target_inputs = set(
            [self.q_att_name, self.ltr_feature_name, 'y'] +
            [self.translation_mtx_in + '_' + self.d_name + '_' + field for field in self.l_d_field] +
            [self.aux_pre + self.translation_mtx_in + '_' + self.d_name + '_' + field for field in self.l_d_field] +
            [self.d_att_name + '_' + field for field in self.l_d_field] +
            [self.aux_pre + self.d_att_name + '_' + field for field in self.l_d_field] +
            ['qid', 'docno', 'docno_pair']
        )

    def set_embedding(self, pretrained_emb):
        logging.warn('att knrm does not use embedding')
        pass

    def _init_inputs(self):
        l_field_translation = self._init_translation_input()
        l_aux_field_translation = self._init_translation_input(aux=True)

        ltr_input, aux_ltr_input = None, None
        if self.ltr_feature_dim > 0:
            ltr_input = Input(shape=(self.ltr_feature_dim,),
                              name=self.ltr_feature_name)
            aux_ltr_input = Input(shape=(self.ltr_feature_dim,),
                                  name=self.aux_pre + self.ltr_feature_name)
        q_att_input = None
        l_field_att_input = []
        l_aux_field_att_input = []
        if self.with_attention:
            q_att_input, l_field_att_input = self._init_att_input()
            __, l_aux_field_att_input = self._init_att_input(aux=True)
        l_inputs = [
            l_field_translation, l_aux_field_translation,
            ltr_input, aux_ltr_input,
            q_att_input, l_field_att_input, l_aux_field_att_input
        ]
        return l_inputs

    def _init_att_input(self, aux=False):
        pre = ""
        if aux:
            pre = self.aux_pre
        q_att_input = Input(shape=(self.att_dim,), name=pre + self.q_att_name)
        l_field_att_input = [Input(shape=(self.att_dim,), name=pre + self.d_att_name + '_' + field) for field in self.l_d_field]
        return q_att_input, l_field_att_input

    def _init_translation_input(self, aux=False):
        pre = ""
        if aux:
            pre = self.aux_pre
        l_field_translation = []
        for field in self.l_d_field:
            l_field_translation.append(
                Input(shape=(None,),
                      name=pre + self.translation_mtx_in + '_' + self.d_name + '_' + field,
                      dtype='int32')
            )
        return l_field_translation

    def _init_layers(self):
        to_train = False
        # if self.metric_learning:
        #     to_train = True
        self.kernel_pool = KernelPooling(np.array(self.mu), np.array(self.sigma), use_raw=True, name='kp')
        self.kp_logsum = KpLogSum()
        self.ltr_layer = Dense(
            1,
            name='letor',
            use_bias=False,
            input_dim=len(self.l_d_field) * len(self.mu) + self.ltr_feature_dim
        )
        if self.metric_learning == 'diag':
            self.distance_metric = DiagnalMetric(input_dim=self.embedding_dim)
        if self.metric_learning == 'dense':
            self.distance_metric = Dense(50, input_dim=self.embedding_dim, use_bias=False)
        if self.with_attention:
            self.q_att = Dense(1, use_bias=False,
                               input_dim=self.att_dim,
                               name='q_att')
            self.l_field_att = [
                Dense(1, use_bias=False,
                      input_dim=self.att_dim,
                      name='d_%s_att' % field
                      )
                for field in self.l_d_field
                ]

    def _init_translation_ranker(self, l_field_translate, ltr_input=None,
                                 q_att_input=None, l_field_att_input=None,
                                 aux=False):
        """
        construct ranker for given inputs
        :param q_input:
        :param l_field_translate: translaiton matrices
        :param ltr_input: if use ltr features to combine
        :param q_att_input: q attention input
        :param l_field_att_input: field attention input
        :param aux:
        :return:
        """
        pre = ""
        if aux:
            pre = self.aux_pre
        q_att = None
        l_field_att = []
        if self.with_attention:
            q_att = self.q_att(q_att_input)
            l_field_att = [self.l_field_att[p](l_field_att_input[p]) for p in xrange(len(self.l_field_att))]
        # perform kernel pooling (TODO test)
        l_kp_features = []
        for p in xrange(self.l_d_field):
            field = self.l_d_field[p]
            f_in = l_field_translate[p]
            d_layer = self.kernel_pool(f_in)
            # TODO test
            if self.with_attention:
                # need custom multiple layer to do * along target axes
                # use broadcast reshape attention to targeted dimensions, and then use multiply
                q_att = Reshape(target_shape=(-1, 1, 1))(q_att)
                d_layer = multiply([d_layer, q_att])
                l_field_att[p] = Reshape(target_shape=(1, -1, 1))(l_field_att[p])
                d_layer = multiply([d_layer, l_field_att[p]])
            d_layer = self.kp_logsum(d_layer, name=pre + 'kp' + field)
            l_kp_features.append(d_layer)

        # put features to one vector
        if len(l_kp_features) > 1:
            ranking_features = concatenate(l_kp_features, name=pre + 'ranking_features')
        else:
            ranking_features = l_kp_features[0]

        if ltr_input:
            ranking_features = concatenate([ranking_features, ltr_input],
                                           name=pre + 'ranking_features_with_ltr')

        ranking_layer = self.ltr_layer(ranking_features)
        l_full_inputs = l_field_translate
        if ltr_input:
            l_full_inputs.append(ltr_input)
        ranker = Model(inputs=l_full_inputs,
                       outputs=ranking_layer,
                       name=pre + 'ranker')

        return ranker

    def construct_model_via_translation(self, l_field_translation, l_aux_field_translation, ltr_input, aux_ltr_input):
        ranker = self._init_translation_ranker(l_field_translation, ltr_input)
        aux_ranker = self._init_translation_ranker(l_aux_field_translation, aux_ltr_input, True)
        trainer = Sequential()
        trainer.add(
            Merge([ranker, aux_ranker],
                  mode=lambda x: x[0] - x[1],
                  output_shape=(1,),
                  name='training_pairwise'
                  )
        )
        return ranker, trainer

    def build(self):
        assert self.emb is not None
        l_field_translation, l_aux_field_translation, ltr_input, aux_ltr_input = self._init_inputs()
        self._init_layers()
        self.ranker, self.trainer = self.construct_model_via_translation(
            l_field_translation, l_aux_field_translation, ltr_input, aux_ltr_input
        )
        return self.ranker, self.trainer

