# Copyright 2016 Toyota Research Institute
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The tree structure representing work to be estimated."""

from collections import namedtuple

from distributions.distribution import ZERO
from distributions.log_logistic import LogLogistic
from distributions.point_distribution import PointDistribution
from distributions.operations import dist_add, dist_scale


CostConfig = namedtuple(
    "CostConfig", [
        "unit_name",      # the name of the cost unit; e.g. "hours", "dollars"
        "resource_costs"  # map of {resource, cost_units_per_resource_unit}
    ])


class Node(object):
    """
    Node represents a point in an estimates tree.  It contains a number of
    child nodes and optionally a cost; the cost is a (resource, distribution)
    pair.

    The mapping of (resource, distribution) pairs to node costs is specified
    via a distribution config.
    """

    # TODO(ggould) this class is a bit of a dumping ground; individual parsers
    # should subclass it.
    # pylint: disable = too-many-instance-attributes

    # pylint is not smart enough to recognize private calls on the subtree:
    # pylint: disable = protected-access

    def __init__(self):
        self.tag = ''
        self.c_class = 0
        self.parent = None
        self.children = []
        self.data = ''
        self.resource = ""
        self.distribution = None
        self._memoized_cost = {}
        self.parser_diag = None

    def is_root(self):
        """True iff this is the root node."""
        return self.parent is None

    def check_valid(self):
        """Checks structural validity of the node tree; asserts if the tree
        is invalid."""
        for child in self.children:
            assert child.parent == self
            child.check_valid()
        # TODO(ggould) Check for additional validity constraints, if any.

    def format_distribution(self):
        """Writes out a human-readable string describing the distribution
        for this node."""
        if self.distribution is None:
            return ''

        def fmt(x):
            """Format the given value for display."""
            if x is None:
                return ''
            return '%.0f' % x
        return '(%s,%s,%s)' % tuple(fmt(self.distribution.quantile(p))
                                    for p in [0.1, 0.5, 0.9])

    def has_cost(self):
        """Return True iff this node has any cost."""
        self.check_valid()
        if self.distribution is not None:
            return True
        return any(child.has_cost() for child in self.children)

    def final_cost(self, config=None):
        """Like 'cost', but assumes that no changes can be made after a call,
        and thus memoizes the result."""
        self.check_valid()
        return self._cost_raw(config, final=True)

    def cost(self, config=None):
        """Computes the cost of this node."""
        self.check_valid()
        return self._cost_raw(config, final=False)

    def _cost_raw(self, config, final):
        """Return the "cost" of this node, with resource costs defined by the
        given config.  If no config is given, all resources are treated as
        cost 1.  Memoizes (and uses memos) iff @p final is True."""
        if final:
            if config in self._memoized_cost:
                return self._memoized_cost[config]

        cost_so_far = self.distribution
        if config:
            multiplier = config.resource_costs.get(self.resource, 0)
            if multiplier > 0:
                cost_so_far = dist_scale(cost_so_far, multiplier)
            else:
                cost_so_far = None
        for child in self.children:
            child_cost = child._cost_raw(config, final)
            if cost_so_far is None or child_cost is None:
                cost_so_far = cost_so_far or child_cost
            else:
                cost_so_far = dist_add(cost_so_far, child_cost)

        result = cost_so_far or ZERO
        if final:
            self._memoized_cost[config] = result
        return result

    def pretty_print(self, prefix=""):
        """Print a human-readable view of this node.  Lines are prefixed with
        the provided @p prefix, if any."""
        self.check_valid()
        node_str = prefix
        node_str += ("* " if self.is_root()
                     else "+ " if len(self.parent.children) > 1
                     else "- ")
        node_str += "{%s} " % self.tag
        if self.parser_diag:
            node_str += " [%s] " % self.parser_diag
        data_len = 78 - len(node_str)
        data_text = (self.data if len(self.data) <= data_len
                     else (self.data[:(data_len - 3)] + "..."))
        node_str += data_text
        print(node_str)
        for child in self.children:
            child.pretty_print(prefix + "  ")


def fit_curve(value_10, value_75):
    """Generates a log-logistic curve fit to the provided 10% and 75% quantile
    values."""
    return LogLogistic.fit(0.1, value_10, 0.75, value_75)


def make_distribution(data):
    """Constructs the distribution corresponding to the estimate expression
    string in @p data."""
    values = data[1:-1].split('-')
    if len(values) == 1:
        return PointDistribution({float(values[0]): 1.0})

    # For now, assume always log_logistic if we have a range.
    return fit_curve(float(values[0]), float(values[1]))
