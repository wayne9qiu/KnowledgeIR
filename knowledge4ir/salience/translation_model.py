"""
graph translation model
or basic page rank model
"""

import logging

import torch
import torch.nn as nn
from knowledge4ir.salience.utils import SalienceBaseModel

use_cuda = torch.cuda.is_available()


class EmbPageRank(SalienceBaseModel):
    """
    input: matrix's |doc||v_e|, |doc||v_score| of these v_e
        e=-1 is padding
    output: p(target e id is salient)
    """

    def __init__(self, para, pre_embedding=None):
        super(EmbPageRank, self).__init__(para, pre_embedding)
        vocab_size = para.entity_vocab_size
        self.embedding = nn.Embedding(para.entity_vocab_size,
                                      para.embedding_dim, padding_idx=0)
        self.linear = nn.Linear(1, 1, bias=True)
        if pre_embedding is not None:
            self.embedding.weight.data.copy_(torch.from_numpy(pre_embedding))
        if use_cuda:
            logging.info('copying parameter to cuda')
            self.embedding.cuda()
            self.linear.cuda()
        self.layer = para.nb_hidden_layers
        return

    def forward(self, mtx_e, mtx_score):
        """
        return probability of each one being salient
        :param mtx_e: the input entity id's, has to be Variable()
        :param mtx_score: the initial weights on each entity, has to be Variable()
        :return: score for each one
        """
        mtx_embedding = self.embedding(mtx_e)
        mtx_embedding = mtx_embedding.div(
            torch.norm(mtx_embedding, p=2, dim=-1, keepdim=True).expand_as(mtx_embedding) + 1e-8
        )

        trans_mtx = torch.matmul(mtx_embedding, mtx_embedding.transpose(-2, -1)).clamp(min=0)
        trans_mtx = trans_mtx.div(
            torch.norm(trans_mtx, p=1, dim=-2, keepdim=True).expand_as(trans_mtx) + 1e-8
        )
        output = mtx_score.unsqueeze(-1)
        for p in xrange(self.layer):
            output = torch.matmul(trans_mtx, output)

        output = self.linear(output)
        output = output.squeeze(-1)
        if use_cuda:
            return output.cuda()
        else:
            return output


class EdgeCNN(SalienceBaseModel):
    """
    input: matrix's |doc||v_e|, |doc||v_score| of these v_e
        e=-1 is padding
    output: p(target e id is salient)
    """

    def __init__(self, para, pre_embedding=None):
        super(EdgeCNN, self).__init__(para, pre_embedding)
        self.embedding = nn.Embedding(para.entity_vocab_size,
                                      para.embedding_dim, padding_idx=0)
        if pre_embedding is not None:
            self.embedding.weight.data.copy_(torch.from_numpy(pre_embedding))
        self.projection = nn.Linear(para.embedding_dim, para.embedding_dim, bias=False)
        self.linear = nn.Linear(1, 1, bias=True)
        if use_cuda:
            logging.info('copying parameter to cuda')
            self.embedding.cuda()
            self.projection.cuda()
            self.linear.cuda()
        self.layer = para.nb_hidden_layers
        return

    def forward(self, mtx_e, mtx_score):
        """
        return probability of each one being salient
        :param mtx_e: the input entity id's, has to be Variable()
        :param mtx_score: the initial weights on each entity, has to be Variable()
        :return: score for each one
        """
        mtx_embedding = self.embedding(mtx_e)
        projected_emb = self.projection(mtx_embedding)

        trans_mtx = torch.matmul(projected_emb, projected_emb.transpose(-2, -1)).clamp(min=0)
        trans_mtx = trans_mtx.div(
            torch.norm(trans_mtx, p=1, dim=-2, keepdim=True).expand_as(trans_mtx) + 1e-8
        )

        output = mtx_score.unsqueeze(-1)
        for p in xrange(self.layer):
            output = torch.matmul(trans_mtx, output)

        output = self.linear(output)
        output = output.squeeze(-1)
        if use_cuda:
            return output.cuda()
        else:
            return output
