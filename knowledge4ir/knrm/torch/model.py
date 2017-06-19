"""
model class
KernelPooling: the kernel pooling layer
KNRM: base class of KNRM, can choose to:
    learn distance metric
    learn entity attention
"""

import knowledge4ir.knrm.torch
from knowledge4ir.knrm.torch.autogram import Variable
import knowledge4ir.knrm.torch.nn.functional as F


class KernelPooling(knowledge4ir.knrm.torch.nn.Module):
    """
    kernel pooling layer
    """
    def __init__(self, mu, sigma):
        """

        :param mu: |d| * 1 dimension mu
        :param sigma: |d| * 1 dimension sigma
        """
        super(KernelPooling, self).__init__()
        self.mu = Variable(mu)
        self.sigma = Variable(sigma)

    def forward(self, x):
        """
        exp((x - mu)^2 / (2 * sigma^2))
        :param x:
        :return: a mu size kernel score
        """

        return

