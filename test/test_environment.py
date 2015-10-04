# -*- coding: utf-8 -*-
# Licensed under a 3-clause BSD style license - see LICENSE.rst

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import sys
import six
import pytest

from asv import config
from asv import environment
from asv import util


WIN = (os.name == "nt")


try:
    util.which('python2.7')
    HAS_PYTHON_27 = True
except (RuntimeError, IOError):
    HAS_PYTHON_27 = (sys.version_info[:2] == (2, 7))


try:
    util.which('python3.4')
    HAS_PYTHON_34 = True
except (RuntimeError, IOError):
    HAS_PYTHON_34 = (sys.version_info[:2] == (3, 4))


try:
    # Conda can install Python 2.7 and 3.4 on demand
    util.which('conda')
    HAS_CONDA = True
except (RuntimeError, IOError):
    HAS_CONDA = False


@pytest.mark.skipif(not ((HAS_PYTHON_27 and HAS_PYTHON_34) or HAS_CONDA),
                    reason="Requires Python 2.7 and 3.4")
def test_matrix_environments(tmpdir):
    conf = config.Config()

    conf.env_dir = six.text_type(tmpdir.join("env"))

    conf.pythons = ["2.7", "3.4"]
    conf.matrix = {
        "six": ["1.4", None],
        "colorama": ["0.3.1", "0.3.3"]
    }
    environments = list(environment.get_environments(conf))

    assert len(environments) == 2 * 2 * 2

    # Only test the first two environments, since this is so time
    # consuming
    for env in environments[:2]:
        env.create()

        output = env.run(
            ['-c', 'import six, sys; sys.stdout.write(six.__version__)'],
            valid_return_codes=None)
        if 'six' in env._requirements:
            assert output.startswith(six.text_type(env._requirements['six']))

        output = env.run(
            ['-c', 'import colorama, sys; sys.stdout.write(colorama.__version__)'])
        assert output.startswith(six.text_type(env._requirements['colorama']))


@pytest.mark.skipif(not (HAS_PYTHON_27 or HAS_CONDA),
                    reason="Requires Python 2.7")
def test_large_environment_matrix(tmpdir):
    # As seen in issue #169, conda can't handle using really long
    # directory names in its environment.  This creates an environment
    # with many dependencies in order to ensure it still works.

    conf = config.Config()

    conf.env_dir = six.text_type(tmpdir.join("env"))
    conf.pythons = ["2.7"]
    for i in range(25):
        conf.matrix['foo{0}'.format(i)] = []

    environments = list(environment.get_environments(conf))

    for env in environments:
        # Since *actually* installing all the dependencies would make
        # this test run a long time, we only set up the environment,
        # but don't actually install dependencies into it.  This is
        # enough to trigger the bug in #169.
        env._install_requirements = lambda *a: None
        env.create()


@pytest.mark.skipif(not (HAS_PYTHON_27 or HAS_CONDA),
                    reason="Requires Python 2.7")
@pytest.mark.xfail(WIN,
                   reason=("Fails on some Windows installations; the Python DLLs "
                           "in the created environments are apparently not unloaded "
                           "properly so that removing the environments fails. This is "
                           "likely not a very common occurrence in real use cases."))
def test_presence_checks(tmpdir):
    conf = config.Config()

    conf.env_dir = six.text_type(tmpdir.join("env"))

    conf.pythons = ["2.7"]
    conf.matrix = {}
    environments = list(environment.get_environments(conf))

    for env in environments:
        env.create()
        assert env.check_presence()

        # Check env is recreated when info file is clobbered
        info_fn = os.path.join(env._path, 'asv-env-info.json')
        data = util.load_json(info_fn)
        data['python'] = '3.4'
        data = util.write_json(info_fn, data)
        env._is_setup = False
        env.create()
        data = util.load_json(info_fn)
        assert data['python'] == '2.7'
        env.run(['-c', 'import os'])

        # Check env is recreated if crucial things are missing
        pip_fns = [
            os.path.join(env._path, 'bin', 'pip')
        ]
        if WIN:
            pip_fns += [
                os.path.join(env._path, 'bin', 'pip.exe'),
                os.path.join(env._path, 'Scripts', 'pip'),
                os.path.join(env._path, 'Scripts', 'pip.exe')
            ]

        some_removed = False
        for pip_fn in pip_fns:
            if os.path.isfile(pip_fn):
                some_removed = True
                os.remove(pip_fn)
        assert some_removed

        env._is_setup = False
        env.create()
        assert os.path.isfile(pip_fn)
        env.run(['-c', 'import os'])


def _sorted_dict_list(lst):
    return list(sorted(lst, key=lambda x: list(sorted(x.items()))))


def test_matrix_expand_basic():
    conf = config.Config()
    conf.environment_type = 'something'
    conf.pythons = ["2.6", "2.7"]
    conf.matrix = {
        'pkg1': None,
        'pkg2': '',
        'pkg3': [''],
        'pkg4': ['1.2', '3.4'],
        'pkg5': []
    }

    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = _sorted_dict_list([
        {'python': '2.6', 'pkg2': '', 'pkg3': '', 'pkg4': '1.2', 'pkg5': ''},
        {'python': '2.6', 'pkg2': '', 'pkg3': '', 'pkg4': '3.4', 'pkg5': ''},
        {'python': '2.7', 'pkg2': '', 'pkg3': '', 'pkg4': '1.2', 'pkg5': ''},
        {'python': '2.7', 'pkg2': '', 'pkg3': '', 'pkg4': '3.4', 'pkg5': ''},
    ])
    assert combinations == expected


def test_matrix_expand_include():
    conf = config.Config()
    conf.environment_type = 'something'
    conf.pythons = ["2.6"]
    conf.matrix = {'a': '1'}
    conf.include = [
        {'python': '3.4', 'b': '2'}
    ]

    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = _sorted_dict_list([
        {'python': '2.6', 'a': '1'},
        {'python': '3.4', 'b': '2'}
    ])
    assert combinations == expected

    conf.include = [
        {'b': '2'}
    ]
    with pytest.raises(util.UserError):
        list(environment.iter_requirement_matrix(conf))


def test_matrix_expand_exclude():
    conf = config.Config()
    conf.environment_type = 'something'
    conf.pythons = ["2.6", "2.7"]
    conf.matrix = {
        'a': '1',
        'b': ['1', None]
    }
    conf.include = [
        {'python': '2.7', 'b': '2', 'c': None}
    ]

    # check basics
    conf.exclude = [
        {'python': '2.7', 'b': '2'},
        {'python': '2.7', 'b': None},
        {'python': '2.6', 'a': '1'},
    ]
    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = _sorted_dict_list([
        {'python': '2.7', 'a': '1', 'b': '1'},
        {'python': '2.7', 'b': '2'}
    ])
    assert combinations == expected

    # check regexp
    conf.exclude = [
        {'python': '.*', 'b': None},
    ]
    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = _sorted_dict_list([
        {'python': '2.6', 'a': '1', 'b': '1'},
        {'python': '2.7', 'a': '1', 'b': '1'},
        {'python': '2.7', 'b': '2'}
    ])
    assert combinations == expected

    # check environment_type as key
    conf.exclude = [
        {'environment_type': 'some.*'},
    ]
    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = [
        {'python': '2.7', 'b': '2'}
    ]
    assert combinations == expected

    # check sys_platform as key
    conf.exclude = [
        {'sys_platform': sys.platform},
    ]
    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = [
        {'python': '2.7', 'b': '2'}
    ]
    assert combinations == expected

    # check inverted regex
    conf.exclude = [
        {'python': '(?!2.6).*'}
    ]
    combinations = _sorted_dict_list(environment.iter_requirement_matrix(conf))
    expected = _sorted_dict_list([
        {'python': '2.6', 'a': '1', 'b': '1'},
        {'python': '2.6', 'a': '1'},
        {'python': '2.7', 'b': '2'}
    ])
    assert combinations == expected
