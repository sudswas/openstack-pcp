# Copyright 2015 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_log import log as logging
from oslo_utils import importutils

from nova import exception
from nova.i18n import _
from nova.i18n import _LE

PMAPI = None
C_API = None

LOG = logging.getLogger(__name__)


class PCPDriver(object):

    _instance = None

    def __init__(self):
        global PMAPI
        global C_API
        if PMAPI is None:
            try:
                PMAPI = importutils.import_module('pcp.pmapi')
            except ImportError as e:
                msg = _('Cannot load pmapi: (%s)') % e
                raise exception.NovaException(msg)
        if C_API is None:
            try:
                C_API = importutils.import_module('cpmapi')
            except ImportError as e:
                msg = _('Cannot load cpmapi: (%s)') % e
                raise exception.NovaException(msg)
        self._connect_to_pcp_daemon()

    def _connect_to_pcp_daemon(self):
        """Get a connection to PCP"""
        # TODO(sbiswas7): We are assuming that there's a pcpd running
        # on the system. This needs to be better handled.
        try:
            self.context = PMAPI.pmContext(C_API.PM_CONTEXT_HOST, "local:")
        except PMAPI.pmErr as ex:
            msg = _("There was an error initializing PCP: %(exc)s "
                    "Please ensure pcpd is running"), {'exc': ex}
            raise exception.NovaException(msg)

    @classmethod
    def get_instance(cls):
        """To implement singleton"""
        if cls._instance is None:
            cls._instance = PCPDriver()

        return cls._instance

    def get_metric_value(self, metric_name):
        """Obtains a metric value based upon the metric name
        :param metric_name: Requested metric name

        :returns: A dictionary with the metric values in various
                  instance domains.
        """
        try:
            metric_id = self.context.pmLookupName(metric_name)
            descs = self.context.pmLookupDescs(metric_id)
            results = self.context.pmFetch(metric_id)
        except PMAPI.pmErr as ex:
            if ex.args[0] == C_API.PM_ERR_NAME:
                LOG.exception(_LE("The metric %(metric)s is not available"),
                              {'metric': metric_name})
            else:
                LOG.exception(_LE("Something bad happened, Returning"))
            return
        # This tuple define the types of the value fields. The indexing
        # is strict and hence the order should be maintained.
        value_fields = ("l", "ul", "ll", "ull", "f", "d")
        values_to_return = {}
        # again the assumption is that there would be one descriptor
        # returned. We'd none the less have a check.
        if len(descs) > 0:
            try:
                for j in xrange(results.contents.get_numval(0)):
                    inst_id = results.contents.get_inst(0, j)
                    value_format = results.contents.get_valfmt(0)
                    vlist = results.contents.get_vlist(0, j)
                    content_type = descs[0].contents.type
                    type = descs[0].type
                    atom = self.context.pmExtractValue(value_format,
                                                       vlist,
                                                       content_type,
                                                       type)
                    values_to_return[inst_id] = getattr(atom,
                                                        value_fields[type])
            except PMAPI.pmErr as e:
                LOG.exception(_LE("There was an error in retrieving"
                              "the metric %(metric)s due to %(exc)s"),
                              {'metric': metric_name, 'exc': e})
                return
        return values_to_return
