# Copyright 2012-2018 CERN for the benefit of the ATLAS collaboration.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Authors:
# - Vincent Garonne <vgaronne@gmail.com>, 2012-2018
# - Ralph Vigne <ralph.vigne@cern.ch>, 2012-2015
# - Mario Lassnig <mario.lassnig@cern.ch>, 2012-2013
# - Martin Barisits <martin.barisits@cern.ch>, 2013-2018
# - Thomas Beermann <thomas.beermann@cern.ch>, 2013
# - Cedric Serfon <cedric.serfon@cern.ch>, 2014-2015
# - Wen Guan <wguan.icedew@gmail.com>, 2014-2015
# - Joaquin Bogado <jbogado@linti.unlp.edu.ar>, 2018
# - Frank Berghaus <frank.berghaus@cern.ch>, 2018
# - Hannes Hansen <hannes.jakob.hansen@cern.ch>, 2018
# - Andrew Lister, <andrew.lister@stfc.ac.uk>, 2019
#
# PY3K COMPATIBLE

from __future__ import print_function

from json import dumps
from nose.tools import raises, assert_equal, assert_true, assert_in, assert_raises
from paste.fixture import TestApp

from rucio.db.sqla import session, models
from rucio.db.sqla.constants import RSEType
from rucio.client.rseclient import RSEClient
from rucio.client.replicaclient import ReplicaClient
from rucio.common.config import config_get_bool
from rucio.common.exception import (Duplicate, RSENotFound, RSEProtocolNotSupported,
                                    InvalidObject, RSEProtocolDomainNotSupported, RSEProtocolPriorityError,
                                    ResourceTemporaryUnavailable, RSEAttributeNotFound, RSEOperationNotSupported)
from rucio.common.utils import generate_uuid
from rucio.core.rse import (add_rse, get_rse_id, del_rse, list_rses, rse_exists, add_rse_attribute, list_rse_attributes,
                            set_rse_transfer_limits, get_rse_transfer_limits, delete_rse_transfer_limits,
                            get_rse_protocols, del_rse_attribute, get_rse_attribute, get_rse, rse_is_empty)
from rucio.rse import rsemanager as mgr
from rucio.tests.common import rse_name_generator
from rucio.web.rest.rse import APP as rse_app
from rucio.web.rest.authentication import APP as auth_app


class TestRSECoreApi(object):

    def setup(self):        
        if config_get_bool('common', 'multi_vo', raise_exception=False, default=False):
            self.vo = {'vo': 'tst'}
        else:
            self.vo = {}

    def test_create_and_check_for_rse(self):
        """ RSE (CORE): Test the creation, query, and deletion of a RSE """
        rse_name = rse_name_generator()
        invalid_rse = 'BLAHBLAH'
        properties = {
            'ASN': 'ASN',
            'availability': 2,
            'deterministic': True,
            'volatile': True,
            'city': 'city',
            'region_code': 'DE',
            'country_name': 'country_name',
            'continent': 'EU',
            'time_zone': 'time_zone',
            'ISP': 'ISP',
            'staging_area': True,
            'rse_type': 'DISK',
            'longitude': 1.0,
            'latitude': 2.0
        }
        properties.update(self.vo)
        rse_id = add_rse(rse_name, **properties)
        assert_equal(rse_exists(rse=rse_name), True)
        rse = get_rse(rse_id=rse_id)
        assert_equal(rse.rse, rse_name)
        assert_equal(rse.deterministic, properties['deterministic'])
        assert_equal(rse.volatile, properties['volatile'])
        assert_equal(rse.city, properties['city'])
        assert_equal(rse.region_code, properties['region_code'])
        assert_equal(rse.country_name, properties['country_name'])
        assert_equal(rse.continent, properties['continent'])
        assert_equal(rse.time_zone, properties['time_zone'])
        assert_equal(rse.ISP, properties['ISP'])
        assert_equal(rse.staging_area, properties['staging_area'])
        assert_equal(rse.rse_type, RSEType.DISK)
        assert_equal(rse.longitude, properties['longitude'])
        assert_equal(rse.latitude, properties['latitude'])
        assert_equal(rse.ASN, properties['ASN'])
        assert_equal(rse.availability, properties['availability'])
        assert_equal(rse_exists(invalid_rse), False)

        with assert_raises(Duplicate):
            add_rse(rse_name, **self.vo)
        del_rse(rse_id=rse_id)
        assert_equal(rse_exists(rse=rse_name), False)

    def test_list_rses(self):
        """ RSE (CORE): Test the listing of all RSEs """
        rse = rse_name_generator()
        rse_id = add_rse(rse, **self.vo)
        assert_equal(rse_exists(rse=rse), True)
        add_rse_attribute(rse_id=rse_id, key='tier', value='1')
        rses = list_rses(filters={'tier': '1'})
        assert_in((rse_id, rse), [(r['id'], r['rse']) for r in rses])
        add_rse_attribute(rse_id=rse_id, key='country', value='us')

        rses = list_rses(filters={'tier': '1', 'country': 'us'})
        assert_in((rse_id, rse), [(r['id'], r['rse']) for r in rses])

        del_rse(rse_id)

    def test_list_rse_attributes(self):
        """ RSE (CORE): Test the listing of RSE attributes """
        rse = rse_name_generator()
        rse_id = add_rse(rse, **self.vo)
        add_rse_attribute(rse_id=rse_id, key='tier', value='1')
        attr = list_rse_attributes(rse_id=rse_id)
        assert_in('tier', list(attr.keys()))
        assert_in(rse, list(attr.keys()))

    def test_create_and_check_rse_transfer_limits(self):
        """ RSE (CORE): Test the creation, query, and deletion of a RSE transfer limit"""
        rse = rse_name_generator()
        activity = 'MOCk'
        max_transfers = 100
        transfers = 90
        waitings = 20
        rse_id = add_rse(rse, **self.vo)

        set_rse_transfer_limits(rse_id=rse_id, activity=activity, max_transfers=max_transfers, transfers=transfers, waitings=waitings)
        limits = get_rse_transfer_limits(rse_id=rse_id, activity=activity)
        assert_in(activity, list(limits.keys()))
        assert_in(rse_id, limits[activity])
        assert_equal(max_transfers, limits[activity][rse_id]['max_transfers'])
        assert_equal(transfers, limits[activity][rse_id]['transfers'])
        assert_equal(waitings, limits[activity][rse_id]['waitings'])

        set_rse_transfer_limits(rse_id=rse_id, activity=activity, max_transfers=max_transfers + 1, transfers=transfers + 1, waitings=waitings + 1)
        limits = get_rse_transfer_limits(rse_id=rse_id, activity=activity)
        assert_in(activity, list(limits.keys()))
        assert_in(rse_id, limits[activity])
        assert_equal(max_transfers + 1, limits[activity][rse_id]['max_transfers'])
        assert_equal(transfers + 1, limits[activity][rse_id]['transfers'])
        assert_equal(waitings + 1, limits[activity][rse_id]['waitings'])

        delete_rse_transfer_limits(rse_id=rse_id, activity=activity)
        limits = get_rse_transfer_limits(rse_id=rse_id, activity=activity)
        deleted = not limits or activity not in limits or rse_id not in limits[activity]
        assert_equal(deleted, True)

        del_rse(rse_id=rse_id)

    def test_delete_rse_attribute(self):
        """ RSE (CORE): Test the deletion of a RSE attribute. """
        rse_name = rse_name_generator()
        rse_id = add_rse(rse_name, **self.vo)
        del_rse_attribute(rse_id=rse_id, key=rse_name)
        assert_equal(get_rse_attribute(key=rse_name, rse_id=rse_id), [])

        with assert_raises(RSEAttributeNotFound):
            del_rse_attribute(rse_id=rse_id, key=rse_name)

    def test_delete_rse(self):
        """ RSE (CORE): Test deletion of RSE """
        # Deletion of not empty RSE
        rse_name = rse_name_generator()
        rse_id = add_rse(rse_name, **self.vo)
        db_session = session.get_session()
        rse_usage = db_session.query(models.RSEUsage).filter_by(rse_id=rse_id, source='rucio').one()
        rse_usage.used = 1
        db_session.commit()
        with assert_raises(RSEOperationNotSupported):
            del_rse(rse_id)

        # Deletion of not found RSE:
        # rse_name = rse_name_generator() #- No longer valid syntax
        # with assert_raises(RSENotFound):
        #     del_rse(rse=rse_name)

    def test_empty_rse(self):
        """ RSE (CORE): Test if RSE is empty """
        rse_name = rse_name_generator()
        rse_id = add_rse(rse_name, **self.vo)
        assert_equal(rse_is_empty(rse_id=rse_id), True)

        db_session = session.get_session()
        rse_usage = db_session.query(models.RSEUsage).filter_by(rse_id=rse_id, source='rucio').one()
        rse_usage.used = 1
        db_session.commit()
        assert_equal(rse_is_empty(rse_id=rse_id), False)


class TestRSE(object):

    def setup(self):        
        if config_get_bool('common', 'multi_vo', raise_exception=False, default=False):
            self.vo_header = {'X-Rucio-VO': 'tst'}
            self.vo = {'vo': 'tst'}
        else:
            self.vo_header = {}
            self.vo = {}

    def test_create_rse_success(self):
        """ RSE (REST): send a POST to create a new RSE """
        mw = []

        headers1 = {'X-Rucio-Account': 'root', 'X-Rucio-Username': 'ddmlab', 'X-Rucio-Password': 'secret'}
        headers1.update(self.vo_header)
        r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=headers1, expect_errors=True)

        assert_equal(r1.status, 200)
        token = str(r1.header('X-Rucio-Auth-Token'))
        rse_name = rse_name_generator()
        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        properties = {
            'ASN': 'ASN',
            'availability': 2,
            'deterministic': True,
            'volatile': True,
            'city': 'city',
            'region_code': 'DE',
            'country_name': 'country_name',
            'continent': 'EU',
            'time_zone': 'time_zone',
            'ISP': 'ISP',
            'staging_area': True,
            'rse_type': 'DISK',
            'longitude': 1.0,
            'latitude': 2.0
        }
        r2 = TestApp(rse_app.wsgifunc(*mw)).post('/' + rse_name, headers=headers2, expect_errors=True, params=dumps(properties))
        assert_equal(r2.status, 201)
        rse = get_rse(rse_id=get_rse_id(rse=rse_name, **self.vo))
        assert_equal(rse.rse, rse_name)
        assert_equal(rse.deterministic, properties['deterministic'])
        assert_equal(rse.volatile, properties['volatile'])
        assert_equal(rse.city, properties['city'])
        assert_equal(rse.region_code, properties['region_code'])
        assert_equal(rse.country_name, properties['country_name'])
        assert_equal(rse.continent, properties['continent'])
        assert_equal(rse.time_zone, properties['time_zone'])
        assert_equal(rse.ISP, properties['ISP'])
        assert_equal(rse.staging_area, properties['staging_area'])
        assert_equal(rse.rse_type, RSEType.DISK)
        assert_equal(rse.longitude, properties['longitude'])
        assert_equal(rse.latitude, properties['latitude'])
        assert_equal(rse.ASN, properties['ASN'])
        assert_equal(rse.availability, properties['availability'])

        headers3 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r3 = TestApp(rse_app.wsgifunc(*mw)).post('/' + rse_name, headers=headers3, expect_errors=True)
        assert_equal(r3.status, 409)

    def xtest_tag_rses(self):
        """ RSE (REST): send a POST to tag a RSE """
        mw = []

        headers1 = {'X-Rucio-Account': 'root', 'X-Rucio-Username': 'ddmlab', 'X-Rucio-Password': 'secret'}
        headers1.update(self.vo_header)
        r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=headers1, expect_errors=True)

        assert_equal(r1.status, 200)
        token = str(r1.header('X-Rucio-Auth-Token'))

        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        data = dumps({'rse': 'MOCK'})
        r2 = TestApp(rse_app.wsgifunc(*mw)).post('/', headers=headers2, params=data, expect_errors=True)
        assert_equal(r2.status, 201)

        headers3 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        data = dumps({'tag': 'MOCK_TAG'})
        r3 = TestApp(rse_app.wsgifunc(*mw)).post('/MOCK/tags', headers=headers3, params=data, expect_errors=True)
        assert_equal(r3.status, 201)

    def xtest_list_rse_tags(self):
        """ RSE (REST): Test the listing of RSE tags """
        mw = []

        headers1 = {'X-Rucio-Account': 'root', 'X-Rucio-Username': 'ddmlab', 'X-Rucio-Password': 'secret'}
        headers1.update(self.vo_header)
        r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=headers1, expect_errors=True)

        assert_equal(r1.status, 200)
        token = str(r1.header('X-Rucio-Auth-Token'))

        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        data = dumps({'rse': 'MOCK'})
        r2 = TestApp(rse_app.wsgifunc(*mw)).post('/', headers=headers2, params=data, expect_errors=True)
        assert_equal(r2.status, 201)

        headers3 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        data = dumps({'tag': 'MOCK_TAG'})
        r3 = TestApp(rse_app.wsgifunc(*mw)).post('/MOCK/tags', headers=headers3, params=data, expect_errors=True)
        assert_equal(r3.status, 201)

        headers4 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r4 = TestApp(rse_app.wsgifunc(*mw)).get('/MOCK/tags', headers=headers4, expect_errors=True)
        assert_equal(r4.status, 200)

    def test_get_rse_account_usage(self):
        """ RSE (REST): Test of RSE account usage and limit """
        mw = []
        headers1 = {'X-Rucio-Account': 'root', 'X-Rucio-Username': 'ddmlab', 'X-Rucio-Password': 'secret'}
        headers1.update(self.vo_header)
        r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=headers1, expect_errors=True)
        assert_equal(r1.status, 200)
        token = str(r1.header('X-Rucio-Auth-Token'))

        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r2 = TestApp(rse_app.wsgifunc(*mw)).get('/MOCK/accounts/usage', headers=headers2, expect_errors=True)
        assert_equal(r2.status, 200)

    def test_delete_rse_attribute(self):
        """ RSE (REST): Test the deletion of a RSE attribute """
        rse_name = rse_name_generator()
        add_rse(rse_name, **self.vo)
        mw = []
        headers1 = {'X-Rucio-Account': 'root', 'X-Rucio-Username': 'ddmlab', 'X-Rucio-Password': 'secret'}
        headers1.update(self.vo_header)
        r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=headers1, expect_errors=True)
        token = str(r1.header('X-Rucio-Auth-Token'))

        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r2 = TestApp(rse_app.wsgifunc(*mw)).delete('/{0}/attr/{0}'.format(rse_name), headers=headers2, expect_errors=True)
        assert_equal(r2.status, 200)

        r2 = TestApp(rse_app.wsgifunc(*mw)).delete('/{0}/attr/{0}'.format(rse_name), headers=headers2, expect_errors=True)
        assert_equal(r2.status, 404)

    def test_delete_rse(self):
        """ RSE (REST): Test the deletion of RSE """
        mw = []
        headers1 = {'X-Rucio-Account': 'root', 'X-Rucio-Username': 'ddmlab', 'X-Rucio-Password': 'secret'}
        headers1.update(self.vo_header)
        r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=headers1, expect_errors=True)
        token = str(r1.header('X-Rucio-Auth-Token'))

        # Normal deletion
        rse_name = rse_name_generator()
        add_rse(rse_name, **self.vo)
        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r2 = TestApp(rse_app.wsgifunc(*mw)).delete('/{0}'.format(rse_name), headers=headers2, expect_errors=True)
        assert_equal(r2.status, 200, r2.body)

        # Second deletion
        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r2 = TestApp(rse_app.wsgifunc(*mw)).delete('/{0}'.format(rse_name), headers=headers2, expect_errors=True)
        assert_equal(r2.status, 404, r2.body)

        # Deletion of not found RSE
        rse_name = rse_name_generator()
        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r2 = TestApp(rse_app.wsgifunc(*mw)).delete('/{0}'.format(rse_name), headers=headers2, expect_errors=True)
        assert_equal(r2.status, 404, r2.body)

        # Deletion of not empty RSE
        rse_name = rse_name_generator()
        rse_id = add_rse(rse_name, **self.vo)
        db_session = session.get_session()
        rse_usage = db_session.query(models.RSEUsage).filter_by(rse_id=rse_id, source='rucio').one()
        rse_usage.used = 1
        db_session.commit()
        headers2 = {'X-Rucio-Type': 'user', 'X-Rucio-Account': 'root', 'X-Rucio-Auth-Token': str(token)}
        r2 = TestApp(rse_app.wsgifunc(*mw)).delete('/{0}'.format(rse_name), headers=headers2, expect_errors=True)


class TestRSEClient(object):

    def setup(self):
        if config_get_bool('common', 'multi_vo', raise_exception=False, default=False):
            self.vo = {'vo': 'tst'}
        else:
            self.vo = {}

        self.client = RSEClient()

    def test_add_rse(self):
        """ RSE (CLIENTS): add a new rse."""
        rse_name = rse_name_generator()
        properties = {
            'ASN': 'ASN',
            'availability': 2,
            'deterministic': True,
            'volatile': True,
            'city': 'city',
            'region_code': 'DE',
            'country_name': 'country_name',
            'continent': 'EU',
            'time_zone': 'time_zone',
            'ISP': 'ISP',
            'staging_area': True,
            'rse_type': 'TAPE',
            'longitude': 1.0,
            'latitude': 2.0
        }
        ret = self.client.add_rse(rse_name, **properties)
        assert_true(ret)
        rse = get_rse(rse_id=get_rse_id(rse=rse_name, **self.vo))
        assert_equal(rse.rse, rse_name)
        assert_equal(rse.deterministic, properties['deterministic'])
        assert_equal(rse.volatile, properties['volatile'])
        assert_equal(rse.city, properties['city'])
        assert_equal(rse.region_code, properties['region_code'])
        assert_equal(rse.country_name, properties['country_name'])
        assert_equal(rse.continent, properties['continent'])
        assert_equal(rse.time_zone, properties['time_zone'])
        assert_equal(rse.ISP, properties['ISP'])
        assert_equal(rse.staging_area, properties['staging_area'])
        assert_equal(rse.rse_type, RSEType.TAPE)
        assert_equal(rse.longitude, properties['longitude'])
        assert_equal(rse.latitude, properties['latitude'])
        assert_equal(rse.ASN, properties['ASN'])
        assert_equal(rse.availability, properties['availability'])

        with assert_raises(Duplicate):
            self.client.add_rse(rse_name)

        bad_rse = 'MOCK_$*&##@!'
        with assert_raises(InvalidObject):
            ret = self.client.add_rse(bad_rse)

    def test_update_rse(self):
        """ RSE (CLIENTS): update rse."""
        rse = rse_name_generator()
        renamed_rse = 'renamed_rse%s' % rse
        ret = self.client.add_rse(rse)
        assert_true(ret)

        ret = self.client.update_rse(rse, {'name': renamed_rse})
        assert_true(ret)
        dict2 = self.client.get_rse(renamed_rse)
        assert_equal(renamed_rse, dict2['rse'])

        tmp_scope = 'mock'
        nbfiles = 5
        files1 = [{'scope': tmp_scope, 'name': 'file_%s' % generate_uuid(), 'bytes': 1,
                   'adler32': '0cc737eb', 'meta': {'events': 10}} for i in range(nbfiles)]
        replica_client = ReplicaClient()
        replica_client.add_replicas(rse=renamed_rse, files=files1)

        ret = self.client.update_rse(renamed_rse, {'availability_write': False, 'availability_delete': False})
        assert_true(ret)
        dict2 = self.client.get_rse(renamed_rse)
        assert_equal(dict2['availability_write'], False)
        assert_equal(dict2['availability_delete'], False)

        files2 = [{'scope': tmp_scope, 'name': 'file_%s' % generate_uuid(), 'bytes': 1,
                   'adler32': '0cc737eb', 'meta': {'events': 10}} for i in range(nbfiles)]
        with assert_raises(ResourceTemporaryUnavailable):
            replica_client.add_replicas(rse=renamed_rse, files=files2, ignore_availability=False)

    def test_list_rses(self):
        """ RSE (CLIENTS): try to list rses."""
        rse_list = [rse_name_generator() for i in range(5)]
        for rse in rse_list:
            self.client.add_rse(rse)

        svr_list = [r['rse'] for r in self.client.list_rses()]

        for rse in rse_list:
            assert_in(rse, svr_list)

    def test_get_rse(self):
        """ RSE (CLIENTS): Get a RSE."""
        id = 'MOCK'
        props = self.client.get_rse(rse=id)
        assert props['rse'] == id

    # ADD PROTOCOLS

    def test_add_protocol(self):
        """ RSE (CLIENTS): add three protocols to rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 4,
                                  'write': 1,
                                  'delete': 0}
                      },
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 18,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 20,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 2,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)
        resp = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        for p in resp['protocols']:
            if ((p['port'] == 19) and (p['domains']['lan']['read'] != 1)) or \
               ((p['port'] == 20) and (p['domains']['lan']['read'] != 2)) or \
               ((p['port'] == 18) and (p['domains']['lan']['read'] != 1)) or \
               ((p['port'] == 17) and (p['domains']['lan']['read'] != 4)):
                print(resp)
                assert False

        self.client.delete_protocols(protocol_rse, scheme='MOCK')
        self.client.delete_rse(protocol_rse)

    @raises(RSENotFound)
    def test_add_protocol_rse_not_found(self):
        """ RSE (CLIENTS): add a protocol to an rse that does not exist (RSENotFound)."""
        self.client.add_protocol('The One that shouldn\'t be here',
                                 {'hostname': 'localhost',
                                  'scheme': 'MOCK_Fail',
                                  'port': 17,
                                  'prefix': '/the/one/with/all/the/files',
                                  'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                  'domains': {
                                      'lan': {'read': 1,
                                              'write': 1,
                                              'delete': 1}},
                                  'extended_attributes': 'TheOneWithAllTheRest'})

    @raises(InvalidObject)
    def test_add_protocol_missing_values(self):
        """ RSE (CLIENTS): add a protocol with insufficient parameters (InvalidObject)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        try:
            self.client.add_protocol(protocol_rse,
                                     {'hostname': 'localhost',
                                      'scheme': 'MOCK_Fail',
                                      'port': 17,
                                      'prefix': '/the/one/with/all/the/files',
                                      # 'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}},
                                      'extended_attributes': 'TheOneWithAllTheRest'})

            self.client.delete_protocols(protocol_rse, 'Mock_Insuff_Params')
            self.client.delete_rse(protocol_rse)
        except Exception:  # explicity raise the correct Exception for MySQL
            raise InvalidObject

    @raises(Duplicate)
    def test_add_protocol_duplicate(self):
        """ RSE (CLIENTS): add duplicate protocol to rse (Duplicate)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        for i in range(2):
            try:
                self.client.add_protocol(protocol_rse,
                                         {'hostname': 'localhost',
                                          'scheme': 'MOCK_Duplicate',
                                          'port': 17,
                                          'prefix': '/the/one/with/all/the/files',
                                          'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                          'domains': {
                                              'lan': {'read': 1,
                                                      'write': 1,
                                                      'delete': 1}},
                                          'extended_attributes': 'TheOneWithAllTheRest'})
            except Exception as e:
                self.client.delete_protocols(protocol_rse, 'MOCK_Duplicate')
                self.client.delete_rse(protocol_rse)
                raise e
        self.client.delete_protocols(protocol_rse, 'MOCK_Duplicate')
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolDomainNotSupported)
    def test_add_protocol_not_suppotred_domain(self):
        """ RSE (CLIENTS): add a protocol with unsupported domain parameters (RSEProtocolDomainNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        self.client.add_protocol(protocol_rse,
                                 {'hostname': 'localhost',
                                  'scheme': 'Mock_Insuff_Params',
                                  'port': 17,
                                  'prefix': '/the/one/with/all/the/files',
                                  # 'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                  'domains': {
                                      'FIRENDS': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}},
                                  'extended_attributes': 'TheOneWithAllTheRest'})
        self.client.delete_protocols(protocol_rse, 'Mock_Insuff_Params')
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolPriorityError)
    def test_add_protocol_wrong_priority(self):
        """ RSE (CLIENTS): Add a protocol with an invalid priority for ranking. """
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocol_ports = [17, 29, 42]
        for i in range(3):
            self.client.add_protocol(protocol_rse,
                                     {'hostname': 'localhost',
                                      'scheme': 'MOCK',
                                      'port': protocol_ports[i],
                                      'prefix': '/the/one/with/all/the/files',
                                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}},
                                      'extended_attributes': 'TheOneWithAllTheRest'})
        try:
            self.client.add_protocol(protocol_rse,
                                     {'hostname': 'localhost',
                                      'scheme': 'MOCK',
                                      'port': 815,
                                      'prefix': '/the/one/with/all/the/files',
                                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 4,
                                                  'write': 99,
                                                  'delete': -1}},
                                      'extended_attributes': 'TheOneWithAllTheRest'})
        except RSEProtocolPriorityError:
            self.client.delete_protocols(protocol_rse, scheme='MOCK')
            self.client.delete_rse(protocol_rse)
            raise
        self.client.delete_protocols(protocol_rse, scheme='MOCK')
        self.client.delete_rse(protocol_rse)

    # DELETE PROTOCOLS

    @raises(RSENotFound)
    def test_del_protocol_rse_not_found(self):
        """ RSE (CLIENTS): delete a protocol from an rse that does not exist (RSENotFound)."""
        self.client.delete_protocols('The One that shouldn\'t be here', 'MOCK_Fail')

    def test_del_protocol_id(self):
        """ RSE (CLIENTS): delete multiple protocols with the same identifier from an rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocol_id = 'MOCK_DEL_ID_SUCCESS'
        protocol_ports = [17, 29, 42]
        for i in range(3):
            self.client.add_protocol(protocol_rse,
                                     {'hostname': 'localhost',
                                      'scheme': protocol_id,
                                      'port': protocol_ports[i],
                                      'prefix': '/the/one/with/all/the/files',
                                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}}})
        self.client.delete_protocols(protocol_rse, protocol_id)

        # check if empty
        resp = None
        try:
            resp = mgr.get_rse_info(rse=protocol_rse, **self.vo)
            mgr.select_protocol(resp, 'read', scheme=protocol_id)
        except RSEProtocolNotSupported:
            self.client.delete_rse(protocol_rse)
            return

        self.client.delete_protocols(protocol_rse, protocol_id)
        self.client.delete_rse(protocol_rse)
        raise Exception('Protocols not deleted. Remaining: %s' % resp)

    @raises(RSEProtocolNotSupported)
    def test_del_protocol_id_protocol_not_supported(self):
        """ RSE (CLIENTS): delete a none-existing protocol from an rse (RSEProtocolNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        try:
            self.client.delete_protocols(protocol_rse, 'MOCK_Fail')
        except Exception as e:
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_rse(protocol_rse)

    def test_del_protocol_hostname(self):
        """ RSE (CLIENTS): delete multiple protocols with the same identifier, and the same hostname from an rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocol_id = 'MOCK_DEL_HOST_SUCCESS'
        protocol_hostname = ['localhost', 'an_other_host', 'localhost']
        protocol_ports = [17, 29, 42]
        for i in range(3):
            self.client.add_protocol(protocol_rse,
                                     {'hostname': protocol_hostname[i],
                                      'scheme': protocol_id,
                                      'port': protocol_ports[i],
                                      'prefix': '/the/one/with/all/the/files',
                                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}},
                                      'extended_attributes': 'TheOneWithAllTheRest'})
        self.client.delete_protocols(protocol_rse, scheme=protocol_id, hostname='localhost')

        # check if protocol for 'other_host' are still there
        resp = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        for r in resp['protocols']:
            if r['hostname'] == 'localhost':
                self.client.delete_rse(protocol_rse)
                raise Exception('Protocols not deleted. Remaining: %s' % resp)

        self.client.delete_protocols(protocol_rse, scheme=protocol_id, hostname='an_other_host')
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolNotSupported)
    def test_del_protocol_hostname_protocol_not_supported(self):
        """ RSE (CLIENTS): delete a none-existing protocol from an rse with given hostname (RSEProtocolNotSupported)."""
        protocol_rse = rse_name_generator()
        protocol_id = 'MOCK_PROTOCOL_DEL_HOST_FAIL'
        self.client.add_rse(protocol_rse)
        self.client.add_protocol(protocol_rse,
                                 {'hostname': 'localhost',
                                  'scheme': protocol_id,
                                  'port': 42,
                                  'prefix': '/the/one/with/all/the/files',
                                  'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                  'domains': {
                                      'lan': {'read': 1,
                                              'write': 1,
                                              'delete': 1}},
                                  'extended_attributes': 'TheOneWithAllTheRest'})
        try:
            self.client.delete_protocols(protocol_rse, 'MOCK_Fail', hostname='an_other_host')
        except Exception as e:
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, 'MOCK_Fail', hostname='localhost')
        self.client.delete_rse(protocol_rse)

    def test_del_protocol_port(self):
        """ RSE (CLIENTS): delete a specific protocol from an rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocol_id = 'MOCK_DEL_PORT_SUCCESS'
        protocol_hostname = ['localhost', 'an_other_host', 'localhost']
        protocol_ports = [17, 29, 42]
        for i in range(3):
            self.client.add_protocol(protocol_rse,
                                     {'hostname': protocol_hostname[i],
                                      'scheme': protocol_id,
                                      'port': protocol_ports[i],
                                      'prefix': '/the/one/with/all/the/files',
                                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}},
                                      'extended_attributes': 'TheOneWithAllTheRest'})
        self.client.delete_protocols(protocol_rse, scheme=protocol_id, hostname='localhost', port=17)

        # check remaining protocols
        resp = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        for r in resp['protocols']:
            if r['port'] == 17:
                self.client.delete_protocols(protocol_rse, protocol_id)
                self.client.delete_rse(protocol_rse)
                raise Exception('Protocols not deleted. Remaining: %s' % resp)
        self.client.delete_protocols(protocol_rse, protocol_id)
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolNotSupported)
    def test_del_protocol_port_protocol_not_supported(self):
        """ RSE (CLIENTS): delete a specific protocol from an rse. (RSEProtocolNotSupported)."""
        protocol_rse = rse_name_generator()
        protocol_id = 'MOCK_PROTOCOL_DEL_PORT_FAIL'
        self.client.add_rse(protocol_rse)
        self.client.add_protocol(protocol_rse,
                                 {'hostname': 'localhost',
                                  'scheme': protocol_id,
                                  'port': 42,
                                  'prefix': '/the/one/with/all/the/files',
                                  'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                  'domains': {
                                      'lan': {'read': 1,
                                              'write': 1,
                                              'delete': 1}},
                                  'extended_attributes': 'TheOneWithAllTheRest'})
        try:
            self.client.delete_protocols(protocol_rse, 'MOCK_Fail', hostname='localhost', port=17)
        except Exception as e:
            self.client.delete_protocols(protocol_rse, protocol_id)
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, protocol_id)
        self.client.delete_rse(protocol_rse)

    # GET PROTOCOLS

    def test_get_protocols(self):
        """ RSE (CLIENTS): get protocols of rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK_READ',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 1},
                          'wan': {'read': 0,
                                  'write': 0,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_WRITE',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1},
                          'wan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_DELETE',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 0,
                                  'delete': 1},
                          'wan': {'read': 1,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)
        # GET all = 3
        resp = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        if len(resp['protocols']) != 3:
            for p in protocols:
                self.client.delete_protocols(protocol_rse, p['scheme'])
            self.client.delete_rse(protocol_rse)
            raise Exception('Unexpected protocols returned: %s' % resp)
        for p in protocols:
            self.client.delete_protocols(protocol_rse, p['scheme'])
        self.client.delete_rse(protocol_rse)

    @raises(RSENotFound)
    def test_get_protocols_rse_not_found(self):
        """ RSE (CLIENTS): get all protocols of rse (RSENotFound)."""
        mgr.get_rse_info(rse="TheOnethatshouldnotbehere", **self.vo)

    def test_get_protocols_operations(self):
        """ RSE (CLIENTS): get protocols for operations of rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK_READ_WRITE_DELETE',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_WRITE_DELETE',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_DELETE',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 0,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        # Protocol identifier include supported operations
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        ops = {'read': 1, 'write': 2, 'delete': 3}
        rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        for op in ops:
            # resp = self.client.get_protocols(protocol_rse, operation=op, protocol_domain='lan')
            p = mgr.select_protocol(rse_attr, op, domain='lan')
            if op not in p['scheme'].lower():
                for p in protocols:
                    self.client.delete_protocols(protocol_rse, p['scheme'])
                self.client.delete_rse(protocol_rse)
                raise Exception('Unexpected protocols returned for %s: %s' % (op, p))
        for p in protocols:
            self.client.delete_protocols(protocol_rse, p['scheme'])
        self.client.delete_rse(protocol_rse)

    def test_get_protocols_defaults(self):
        """ RSE (CLIENTS): get default protocols for operations of rse."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK_READ',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1},
                          'wan': {'delete': 1}
                      },
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_WRITE',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'write': 1},
                          'wan': {'read': 1}
                      },
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_DELETE',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'delete': 1},
                          'wan': {'write': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        for op in ['delete', 'read', 'write']:
            # resp = self.client.get_protocols(protocol_rse, operation=op, default=True, protocol_domain='lan')
            p = mgr.select_protocol(rse_attr, op, domain='lan')
            print(p['scheme'])
            print(op)
            if op not in p['scheme'].lower():
                for p in protocols:
                    self.client.delete_protocols(protocol_rse, p['scheme'])
                self.client.delete_rse(protocol_rse)
                raise Exception('Unexpected protocols returned for %s: %s' % (op, p))
        for op in ['delete', 'read', 'write']:
            # resp = self.client.get_protocols(protocol_rse, operation=op, default=True, protocol_domain='wan')
            p = mgr.select_protocol(rse_attr, op, domain='wan')
            if ((op == 'delete') and (p['port'] != 17)) or ((op == 'read') and (p['port'] != 42)) or ((op == 'write') and (p['port'] != 19)):
                for p in protocols:
                    self.client.delete_protocols(protocol_rse, p['scheme'])
                self.client.delete_rse(protocol_rse)
                raise Exception('Unexpected protocols returned for %s: %s' % (op, p))
        for p in protocols:
            self.client.delete_protocols(protocol_rse, p['scheme'])
        self.client.delete_rse(protocol_rse)

    def test_get_protocols_nested_attributes(self):
        """ RSE (CLIENTS): get nested extended_attributes."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK_READ',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1},
                          'wan': {'delete': 1}
                      },
                      'extended_attributes': {'Some': 'value', 'more': {'value1': 1, 'value2': 0}}}]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        resp = mgr.get_rse_info(rse=protocol_rse, **self.vo)['protocols']
        assert((not resp[0]['extended_attributes']['more']['value2']) and resp[0]['extended_attributes']['more']['value1'])

    @raises(RSEProtocolNotSupported)
    def test_get_protocols_operations_not_supported(self):
        """ RSE (CLIENTS): get protocols for operations of rse (RSEOperationNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK_WRITE_DELETE',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_WRITE_DELETE',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_DELETE',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 0,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        # Protocol for read is undefined
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        try:
            rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
            rse_attr['domain'] = ['lan']
            mgr.select_protocol(rse_attr, 'read')
        except Exception as e:
            self.client.delete_protocols(protocol_rse, 'MOCK_WRITE_DELETE')
            self.client.delete_protocols(protocol_rse, 'MOCK_DELETE')
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, 'MOCK_WRITE_DELETE')
        self.client.delete_protocols(protocol_rse, 'MOCK_DELETE')
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolDomainNotSupported)
    def test_get_protocols_domain_not_exist(self):
        """ RSE (CLIENTS): get protocols for operations of rse in not existing domain (RSEProtocolDomainNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        # Protocol for read is undefined
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        try:
            rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
            mgr.select_protocol(rse_attr, 'write', domain='FRIENDS')
        except Exception as e:
            self.client.delete_protocols(protocol_rse, 'MOCK')
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, 'MOCK')
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolNotSupported)
    def test_get_protocols_domain_not_supported(self):
        """ RSE (CLIENTS): get protocols for operations of rse in unsupported domain (RSEOperationNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        # Protocol for read is undefined
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        try:
            rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
            rse_attr['domain'] = ['wan']
            mgr.select_protocol(rse_attr, 'write')
        except Exception as e:
            self.client.delete_protocols(protocol_rse, 'MOCK')
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, 'MOCK')
        self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolNotSupported)
    def test_get_protocols_defaults_not_supported(self):
        """ RSE (CLIENTS): get default protocols for operations of rse (RSEOperationNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK_WRITE_DELETE',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_WRITE_DELETE',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_DELETE',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 0,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        # Protocol for read is undefined
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        try:
            rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
            rse_attr['domain'] = ['lan']
            mgr.select_protocol(rse_attr, 'read')
        except Exception as e:
            self.client.delete_protocols(protocol_rse, 'MOCK_WRITE_DELETE')
            self.client.delete_protocols(protocol_rse, 'MOCK_DELETE')
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, 'MOCK_WRITE_DELETE')
        self.client.delete_protocols(protocol_rse, 'MOCK_DELETE')
        self.client.delete_rse(protocol_rse)

    # UPDATE PROTOCOLS

    @raises(Duplicate)
    def test_update_protocols_port_exist(self):
        """ RSE (CLIENTS): set new values for various protocol attributes."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'wan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 11,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'wan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'}]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        try:
            self.client.update_protocols(protocol_rse, scheme='MOCK', hostname='localhost', port=17, data={'prefix': 'where/the/files/are', 'extended_attributes': 'Something else', 'port': '11'})
        except Exception as e:
            self.client.delete_protocols(protocol_rse, 'MOCK')
            self.client.delete_rse(protocol_rse)
            raise e
        self.client.delete_protocols(protocol_rse, 'MOCK')
        self.client.delete_rse(protocol_rse)

    def test_update_protocols_various_attributes(self):
        """ RSE (CLIENTS): set new values for various protocol attributes."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'}]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        self.client.update_protocols(protocol_rse, scheme='MOCK', hostname='localhost', port=17, data={'prefix': 'where/the/files/are', 'extended_attributes': 'Something else', 'port': '12'})
        rse_attr = mgr.get_rse_info(rse=protocol_rse, **self.vo)
        p = mgr.select_protocol(rse_attr, 'read', scheme='MOCK', domain='lan')
        if p['prefix'] != 'where/the/files/are' and p['extended_attributes'] != 'Something else':
            raise Exception('Update gave unexpected results: %s' % p)
        self.client.delete_protocols(protocol_rse, 'MOCK')
        self.client.delete_rse(protocol_rse)

    def test_swap_protocol(self):
        """ RSE (CLIENTS): swaps the priority of two protocols by scheme. """
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCKA',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCKB',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 2,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCKC',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 3,
                                  'write': 0,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        self.client.swap_protocols(protocol_rse, 'lan', 'read', 'MOCKA', 'MOCKC')
        prots = self.client.get_protocols(protocol_rse)
        for p in prots:
            if p['scheme'] == 'MOCKA':
                if p['domains']['lan']['read'] != 3:
                    print('MOCKA with unexpected priority')
                    print(prots)
                    assert(False)
            if p['scheme'] == 'MOCKC':
                if p['domains']['lan']['read'] != 1:
                    print('MOCKC with unexpected priority')
                    print(prots)
                    assert(False)
        assert(True)

    @raises(RSENotFound)
    def test_update_protocols_rse_not_found(self):
        """ RSE (CLIENTS): update all protocols with specific identifier of rse (RSENotFound)."""
        self.client.update_protocols('The One that shouldn\'t be here', scheme='MOCK_Fail', hostname='localhost', port=17, data={'prefix': 'where/the/files/are'})

    @raises(RSEProtocolNotSupported)
    def test_update_protocols_not_supported(self):
        """ RSE (CLIENTS): update all protocols with specific identifier of rse (RSEProtocolNotSupported)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 1,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 42,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 1,
                                  'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'},
                     {'scheme': 'MOCK_DELETE',
                      'hostname': 'localhost',
                      'port': 19,
                      'prefix': '/the/one/with/all/the/files',
                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {
                          'lan': {'read': 0,
                                  'write': 0,
                                  'delete': 1}},
                      'extended_attributes': 'TheOneWithAllTheRest'}, ]
        for p in protocols:
            self.client.add_protocol(protocol_rse, p)

        try:
            self.client.update_protocols(protocol_rse, scheme='MOCK_UNDEFINED', hostname='localhost', port=17, data={'delete_lan': 1})
        except Exception as e:
            for p in protocols:
                self.client.delete_protocols(protocol_rse, p['scheme'])
            self.client.delete_rse(protocol_rse)
            raise e
        for p in protocols:
            self.client.delete_protocols(protocol_rse, p['scheme'])
        self.client.delete_rse(protocol_rse)

    @raises(InvalidObject)
    def test_update_protocols_invalid_value(self):
        """ RSE (CLIENTS): update all protocol with invalid value (InvalidObject)."""
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocols = [{'scheme': 'MOCK',
                      'hostname': 'localhost',
                      'port': 17,
                      'prefix': '/the/one/with/all/the/files',
                      # 'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                      'domains': {'lan': {'read': 1,
                                          'write': 1,
                                          'delete': 0}},
                      'extended_attributes': 'TheOneWithAllTheRest'}]

        try:
            for p in protocols:
                self.client.add_protocol(protocol_rse, p)
                self.client.update_protocols(protocol_rse, scheme='MOCK', hostname='localhost', port=17, data={'impl': None})
        except Exception:
            raise InvalidObject  # explicity raise the correct Exception for MySQL
        finally:
            try:
                self.client.delete_protocols(protocol_rse, 'MOCK')
            except Exception:
                pass  # for MySQL
            finally:
                self.client.delete_rse(protocol_rse)

    @raises(RSEProtocolPriorityError)
    def test_update_protocol_wrong_priority(self):
        """  RSE (CLIENTS): Add a protocol with an invalid priority for ranking. """
        protocol_rse = rse_name_generator()
        self.client.add_rse(protocol_rse)
        protocol_ports = [17, 29, 42]
        for i in range(3):
            self.client.add_protocol(protocol_rse,
                                     {'hostname': 'localhost',
                                      'scheme': 'MOCK',
                                      'port': protocol_ports[i],
                                      'prefix': '/the/one/with/all/the/files',
                                      'impl': 'rucio.rse.protocols.SomeProtocol.SomeImplementation',
                                      'domains': {
                                          'lan': {'read': 1,
                                                  'write': 1,
                                                  'delete': 1}},
                                      'extended_attributes': 'TheOneWithAllTheRest'})
        try:
            self.client.update_protocols(protocol_rse, scheme='MOCK', hostname='localhost', port=42, data={'domains': {'lan': {'read': 4}}})
        except RSEProtocolPriorityError:
            self.client.delete_protocols(protocol_rse, scheme='MOCK')
            self.client.delete_rse(protocol_rse)
            raise
        self.client.delete_protocols(protocol_rse, scheme='MOCK')
        self.client.delete_rse(protocol_rse)

    def test_get_rse_usage(self):
        """ RSE (CLIENTS): Test getting the RSE usage. """
        usages = self.client.get_rse_usage(rse='MOCK', filters={'per_account': True})
        for usage in usages:
            assert_true(usage['account_usages'])
        usages = self.client.get_rse_usage(rse='MOCK')
        for usage in usages:
            assert_true('account_usages' not in usage)

    def test_set_rse_usage(self):
        """ RSE (CLIENTS): Test the update of RSE usage."""
        assert_equal(self.client.set_rse_usage(rse='MOCK', source='srm', used=999200, free=800), True)
        usages = self.client.get_rse_usage(rse='MOCK')
        for usage in usages:
            if usage['source'] == 'srm':
                assert_equal(usage['total'], 1000000)
        assert_equal(self.client.set_rse_usage(rse='MOCK', source='srm', used=999920, free=80), True)
        for usage in self.client.list_rse_usage_history(rse='MOCK'):
            assert_equal(usage['free'], 80)
            break

    def test_set_rse_limits(self):
        """ RSE (CLIENTS): Test the update of RSE limits."""
        assert_equal(self.client.set_rse_limits(rse='MOCK', name='MinFreeSpace', value=1000000), True)
        limits = self.client.get_rse_limits(rse='MOCK')
        assert_equal(limits['MinFreeSpace'], 1000000)

    def test_rsemgr_possible_protocols(self):
        """ RSE (MANAGER): Test of possible protocols."""
        rse_settings = {'availability_delete': True,
                        'availability_read': True,
                        'availability_write': True,
                        'credentials': None,
                        'deterministic': True,
                        'domain': ['lan', 'wan'],
                        'protocols': [{'domains': {'lan': {'delete': 2, 'read': 0, 'write': 0},
                                                   'wan': {'delete': 2, 'read': 2, 'write': 0}},
                                       'extended_attributes': None,
                                       'hostname': u'atlas-xrd.gridpp.rl.ac.uk',
                                       'impl': u'rucio.rse.protocols.gfal.Default',
                                       'port': 1094,
                                       'prefix': u'//castor/ads.rl.ac.uk/prod/atlas/stripInput/atlasdatadisk/rucio/',
                                       'scheme': u'root'},
                                      {'domains': {'lan': {'delete': 0, 'read': 1, 'write': 0},
                                                   'wan': {'delete': 0, 'read': 0, 'write': 0}},
                                       'extended_attributes': None,
                                       'hostname': u'catlasdlf.ads.rl.ac.uk',
                                       'impl': u'rucio.rse.protocols.gfal.Default',
                                       'port': 1094,
                                       'prefix': u'//castor/ads.rl.ac.uk/prod/atlas/stripInput/atlasdatadisk/rucio/',
                                       'scheme': u'root'},
                                      {'domains': {'lan': {'delete': 1, 'read': 0, 'write': 1},
                                                   'wan': {'delete': 1, 'read': 1, 'write': 1}},
                                       'extended_attributes': {u'space_token': u'ATLASDATADISK',
                                                               u'web_service_path': u'/srm/managerv2?SFN='},
                                       'hostname': u'srm-atlas.gridpp.rl.ac.uk',
                                       'impl': u'rucio.rse.protocols.gfal.Default',
                                       'port': 8443,
                                       'prefix': u'/castor/ads.rl.ac.uk/prod/atlas/stripInput/atlasdatadisk/rucio/',
                                       'scheme': u'srm'}],
                        'rse': u'MOCK',
                        'rse_type': 'DISK',
                        'staging_area': False,
                        'volatile': False}
        assert_equal(len(mgr._get_possible_protocols(rse_settings, 'read')), 3)

    def test_add_distance(self):
        """ RSE (CLIENTS): add/get/update RSE distances."""
        source, destination = rse_name_generator(), rse_name_generator()
        self.client.add_rse(source)
        self.client.add_rse(destination)
        self.client.add_distance(source=source,
                                 destination=destination,
                                 parameters={'distance': 1})

        for distance in self.client.get_distance(source=source, destination=destination):
            assert_equal(distance['distance'], 1)

        self.client.update_distance(source=source,
                                    destination=destination,
                                    parameters={'distance': 0})

        for distance in self.client.get_distance(source=source, destination=destination):
            print(distance)
            assert_equal(distance['distance'], 0)

    def test_get_rse_protocols_includes_verify_checksum(self):
        """ RSE (CORE): Test validate_checksum in RSEs info"""
        rse = rse_name_generator()
        rse_id = add_rse(rse, **self.vo)
        add_rse_attribute(rse_id=rse_id, key='verify_checksum', value=False)
        info = get_rse_protocols(rse_id)

        assert_in('verify_checksum', info)
        assert_equal(info['verify_checksum'], False)

        del_rse(rse_id)

        rse = rse_name_generator()
        rse_id = add_rse(rse, **self.vo)
        add_rse_attribute(rse_id=rse_id, key='verify_checksum', value=True)
        info = get_rse_protocols(rse_id)

        assert_in('verify_checksum', info)
        assert_equal(info['verify_checksum'], True)
        del_rse(rse_id)

    def test_delete_rse_attribute(self):
        """ RSE (CLIENT): Test the deletion of a RSE attribute. """
        rse_name = rse_name_generator()
        self.client.add_rse(rse_name)
        self.client.delete_rse_attribute(rse=rse_name, key=rse_name)
        assert_equal(get_rse_attribute(key=rse_name, rse_id=get_rse_id(rse_name, **self.vo)), [])

        with assert_raises(RSEAttributeNotFound):
            self.client.delete_rse_attribute(rse=rse_name, key=rse_name)

    def test_delete_rse(self):
        """ RSE (CLIENTS): delete RSE """
        # Deletion of not empty RSE
        rse_name = rse_name_generator()
        add_rse(rse_name, **self.vo)
        rse_id = get_rse_id(rse_name, **self.vo)
        db_session = session.get_session()
        rse_usage = db_session.query(models.RSEUsage).filter_by(rse_id=rse_id, source='rucio').one()
        rse_usage.used = 1
        db_session.commit()
        db_session = session.get_session()
        print(db_session.query(models.RSEUsage).filter_by(rse_id=rse_id).one())
        with assert_raises(RSEOperationNotSupported):
            self.client.delete_rse(rse=rse_name)

        # Deletion of not found RSE:
        rse_name = rse_name_generator()
        with assert_raises(RSENotFound):
            self.client.delete_rse(rse=rse_name)
