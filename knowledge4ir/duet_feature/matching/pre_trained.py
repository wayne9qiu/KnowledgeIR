"""
read pre-trained salience features
in each entity' predict_features field
get feature for each q e
sum up for the final feature
"""

import json
import logging
import numpy as np
from knowledge4ir.duet_feature import LeToRFeatureExtractor
from traitlets import (
    Unicode,
    Int,
    List,
    Bool,
    Float,
)
from knowledge4ir.utils import (
    TARGET_TEXT_FIELDS,
    log_sum_feature,
    max_pool_feature,
    sum_pool_feature,
    mean_pool_feature,
    exp_feature,
    body_field,
)
from copy import deepcopy


class LeToRBOEPreTrainedFeatureExtractor(LeToRFeatureExtractor):
    tagger = Unicode('spot', help='tagger used, as in q info and d info'
                     ).tag(config=True)
    l_target_fields = List(Unicode,
                           default_value=TARGET_TEXT_FIELDS,
                           help='doc fields to use'
                           ).tag(config=True)

    feature_name_pre = Unicode('Pretrain')
    default_feature_value = Float(-30, help='filling for empty feature').tag(config=True)
    feature_dim = Int(22,
                      help='number of features in pre-trained').tag(config=True)
    pretrain_feature_field = Unicode('salience_feature', help='field of trained features').tag(config=True)
    l_normalize_feature = List(
        Unicode,
        default_value=[''],
        help='whether and how to normalize feature. Currently supports softmax, minmax, uniq, doclen, expuniq, docuniq'
    ).tag(config=True)
    normalize_feature = Unicode(
        help='back-supporting'
    ).tag(config=True)
    l_normalize_field = List(
        Unicode,
        default_value=TARGET_TEXT_FIELDS,
    ).tag(config=True)

    with_stat_feature = Bool(
        False,
        help='whether add stats as a feature'
    ).tag(config=True)

    l_q_level_pooling = List(
        Unicode,
        default_value=['sum'],
        help='pooling at query level, sum, max, mean'
    ).tag(config=True)

    h_pool_func = {
        'log_sum': log_sum_feature,
        'max': max_pool_feature,
        'mean': mean_pool_feature,
        'sum': sum_pool_feature,
    }

    def __init__(self, **kwargs):
        super(LeToRBOEPreTrainedFeatureExtractor, self).__init__(**kwargs)
        self.h_norm = {
            '': self._no_norm,
            "softmax": self._softmax_feature,
            'minmax': self._minmax_feature,
            'uniq': self._uniq_e_normalize_feature,
            'doclen': self._doc_len_normalize_feature,
            'expuniq': self._exp_uniq_e_normalize_feature,
            'docuniq': self._doc_uniq_normalize_feature,
            'boelen': self._boe_len_normalize_feature,
            'log_boelen': self._log_boe_len_normalize_feature,
        }
        if self.normalize_feature:
            logging.warn('overide l_normalize_feature by [%s]', self.normalize_feature)
            self.l_normalize_feature = [self.normalize_feature]

    def extract(self, qid, docno, h_q_info, h_doc_info):
        l_q_e = [ana['entities'][0]['id'] for ana in h_q_info[self.tagger]['query']]
        h_feature = dict()
        h_stat_feature = {}
        for field, l_ana in h_doc_info[self.tagger].items():
            if field not in self.l_target_fields:
                continue
            h_q_e_feature = {}
            h_info = dict()
            h_info['boe_len'] = len(l_ana)
            h_stat_feature['%s_BoeLen' % field.title()] = len(l_ana)
            for q_e in l_q_e:
                h_q_e_feature[q_e] = [self.default_feature_value] * self.feature_dim
            h_e_feature = dict()
            for ana in l_ana:  # get features for all entities
                e_id = ana['entities'][0]['id']
                l_feature = ana['entities'][0].get(self.pretrain_feature_field, [])
                if l_feature:
                    assert len(l_feature) == self.feature_dim
                    h_e_feature[e_id] = l_feature
            l_norm_names = ['']
            if field in self.l_normalize_field:
                l_norm_names = self.l_normalize_feature
            for norm_name in l_norm_names:
                l_e_ll_feature = h_e_feature.items()
                ll_feature = deepcopy([item[1] for item in l_e_ll_feature])
                l_e = [item[0] for item in l_e_ll_feature]
                ll_feature = self._normalize_feature(ll_feature, h_info, norm_name)
                h_e_feature = dict(zip(l_e, ll_feature))
                for q_e in l_q_e:
                    if q_e in h_e_feature:
                        h_q_e_feature[q_e] = h_e_feature[q_e]
                        logging.debug('q e [%s] has feature %s', q_e, json.dumps(h_q_e_feature[q_e]))
                l_q_feature = [item[1] for item in h_q_e_feature.items()]
                l_name = ['%s_%s%s_%03d' % (field, self.pretrain_feature_field, norm_name.title(), p)
                          for p in range(self.feature_dim)]
                l_h_q_feature = []
                for l_feature in l_q_feature:
                    h_this_f = dict(zip(l_name, l_feature))
                    l_h_q_feature.append(h_this_f)
                h_feature.update(self._pool_feature(l_h_q_feature))

        if self.with_stat_feature:
            h_feature.update(h_stat_feature)
        return h_feature

    def _pool_feature(self, l_h_q_feature):
        """
        exp the feature first
        then pool it
        :param l_h_q_feature:
        :return:
        """
        # l_h_q_feature = [exp_feature(h_q_feature) for h_q_feature in l_h_q_feature]
        logging.debug('pooling with %s', json.dumps(l_h_q_feature))
        h_pooled_feature = dict()
        for pool in self.l_q_level_pooling:
            logging.debug('[%s] pooling', pool)
            h_pooled_feature.update(self.h_pool_func[pool](l_h_q_feature))
        logging.debug('pooled to %s', json.dumps(h_pooled_feature))
        return h_pooled_feature

    def _normalize_feature(self, ll_feature, h_info, norm_name):
        """
        normalize feature
        :param ll_feature: features to normalize. e * feature
        :param h_info: additional information
        :return:
        """
        if not ll_feature:
            return ll_feature
        if norm_name not in self.h_norm:
            logging.info('normalize via [%s] not implemented', norm_name)
            raise NotImplementedError
        return self.h_norm[norm_name](ll_feature, h_info)

    def _no_norm(self, ll_feature, h_info=None):
        return ll_feature

    def _softmax_feature(self, ll_feature, h_info=None):
        m_feature = np.array(ll_feature)
        exp_feature = np.exp(m_feature)
        sum_norm = np.sum(exp_feature, axis=0)
        normalized_e = exp_feature / sum_norm
        ll_normalized_feature = np.log(normalized_e).tolist()
        return ll_normalized_feature

    def _minmax_feature(self, ll_feature, h_info=None):
        m_feature = np.array(ll_feature)
        max_feature = np.amax(m_feature, axis=0)
        min_feature = np.amin(m_feature, axis=0)
        z_feature = np.maximum(max_feature - min_feature, 1e-10)
        normalized_feature = (m_feature - min_feature) / z_feature
        return normalized_feature.tolist()

    def _uniq_e_normalize_feature(self, ll_feature, h_info=None):
        m_feature = np.array(ll_feature)
        m_feature /= float(m_feature.shape[0])
        return m_feature.tolist()

    def _exp_uniq_e_normalize_feature(self, ll_feature, h_info=None):
        m_feature = np.array(ll_feature)
        z = float(m_feature.shape[0])
        m_feature = np.log(np.exp(m_feature) / float(z))
        return m_feature.tolist()

    def _doc_len_normalize_feature(self, ll_feature, h_info=None):
        m_feature = np.array(ll_feature)
        z = np.sum(np.exp(m_feature[:, 0]))
        m_feature = np.log(np.exp(m_feature) / float(z))
        return m_feature.tolist()

    def _doc_uniq_normalize_feature(self, ll_feature, h_info=None):
        m_feature = np.array(ll_feature)
        z = np.sum(np.exp(m_feature[:, 0]))
        m_feature = np.log(np.exp(m_feature) / float(z) / float(m_feature.shape[0]))
        return m_feature.tolist()

    def _boe_len_normalize_feature(self, ll_feature, h_info):
        m_feature = np.array(ll_feature)
        z = h_info.get('boe_len', 1.0)
        m_feature -= np.log(float(z))
        return m_feature.tolist()

    def _log_boe_len_normalize_feature(self, ll_feature, h_info):
        m_feature = np.array(ll_feature)
        z = h_info.get('boe_len', 1.0)
        m_feature /= float(z)
        return m_feature.tolist()
