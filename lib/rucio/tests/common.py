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
# - Mario Lassnig <mario.lassnig@cern.ch>, 2012
# - Angelos Molfetas <Angelos.Molfetas@cern.ch>, 2012
# - Vincent Garonne <vgaronne@gmail.com>, 2012-2018
# - Joaquin Bogado <jbogado@linti.unlp.edu.ar>, 2014-2018
# - Fernando Lopez <fernando.e.lopez@gmail.com>, 2015
# - Martin Barisits <martin.barisits@cern.ch>, 2017

from paste.fixture import TestApp
from random import choice
from string import ascii_uppercase

import contextlib
import os
import subprocess
import tempfile

from rucio.client.accountclient import AccountClient
from rucio.common import exception
from rucio.common.utils import generate_uuid as uuid


def execute(cmd):
    """
    Executes a command in a subprocess. Returns a tuple
    of (exitcode, out, err), where out is the string output
    from stdout and err is the string output from stderr when
    executing the command.

    :param cmd: Command string to execute
    """

    process = subprocess.Popen(cmd,
                               shell=True,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    out = ''
    err = ''
    exitcode = 0

    result = process.communicate()
    (out, err) = result
    exitcode = process.returncode

    return exitcode, out, err


def create_accounts(account_list, user_type):
    """ Registers a set of accounts

    :param account_list: the list of accounts to be added
    :param user_type: the type of accounts
    """
    account_client = AccountClient()
    for account in account_list:
        try:
            account_client.add_account(account, user_type, email=None)
        except exception.Duplicate:
            pass  # Account already exists, no need to create it


def get_auth_token(account, username, password):
    """ Get's an authentication token from the server

    :param account: the account authenticating
    :param username:the username linked to the account
    :param password: the password linked to the account
    :returns: the authentication token
    """
    if config_get_bool('common', 'multi_vo', raise_exception=False, default=False):
        vo_header = {'X-Rucio-VO': 'tst'}
    else:
        vo_header = {}

    from rucio.web.rest.authentication import APP as auth_app
    mw = []
    header = {'Rucio-Account': account, 'Rucio-Username': username, 'Rucio-Password': password}
    header.update(vo_header)
    r1 = TestApp(auth_app.wsgifunc(*mw)).get('/userpass', headers=header, expect_errors=True)
    token = str(r1.header('Rucio-Auth-Token'))
    return token


def account_name_generator():
    """ Generate random account name.

    :returns: A random account name
    """
    return 'jdoe-' + str(uuid()).lower()[:16]


def scope_name_generator():
    """ Generate random scope name.

    :returns: A random scope name
    """
    return 'mock_' + str(uuid()).lower()[:16]


def rse_name_generator(size=10):
    """ Generate random RSE name.

    :returns: A random RSE name
    """
    return 'MOCK_' + ''.join(choice(ascii_uppercase) for x in range(size))


def file_generator(size=2, namelen=10):
    """ Create a bogus file and returns it's name.
    :param size: size in bytes
    :returns: The name of the generated file.
    """
    fn = '/tmp/file_' + ''.join(choice(ascii_uppercase) for x in range(namelen))
    execute('dd if=/dev/urandom of={0} count={1} bs=1'.format(fn, size))
    return fn


def make_temp_file(dir, data):
    """
    Creates a temporal file and write `data` on it.
    :param data: String to be writen on the created file.
    :returns: Name of the temporal file.
    """
    fd, path = tempfile.mkstemp(dir=dir)
    with os.fdopen(fd, 'w') as f:
        f.write(data)

    return path


@contextlib.contextmanager
def stubbed(target, replacement):
    """
    Stubs an object inside a with statement, returning to
    the original implementation in the end.

    :param target: Object to be stubbed-out.
    :param replacement: Stub value/function.

    Example:
    with stubbed(module_under_test.fun_x, lambda _, __: StringIO('hello world')):
        value = module_under_test.function_using_fun_x()
    """
    from stub import stub
    stubbed_obj = stub(target, replacement)
    try:
        yield
    finally:
        stubbed_obj.unstub()


@contextlib.contextmanager
def mock_open(module, file_like_object):
    call_info = {}

    def mocked_open(filename, mode='r'):
        call_info['filename'] = filename
        call_info['mode'] = mode
        file_like_object.close = lambda: None
        return contextlib.closing(file_like_object)

    setattr(module, 'open', mocked_open)
    try:
        yield call_info
    finally:
        file_like_object.seek(0)
        delattr(module, 'open')
