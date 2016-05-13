# -*- coding: utf-8 -*-
#
# This file is part of Glances.
#
# Copyright (C) 2016 Nicolargo <nicolas@nicolargo.com>
#
# Glances is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Glances is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Manage Glances update."""

from datetime import datetime, timedelta
from distutils.version import LooseVersion
import threading
import json
import pickle
import os
try:
    import requests
except ImportError:
    outdated_tag = False
else:
    outdated_tag = True

from glances import __version__, __appname__
from glances.globals import BSD, LINUX, OSX, WINDOWS
from glances.logger import logger


class Outdated(object):

    """
    This class aims at providing methods to warn the user when a new Glances
    version is available on the Pypi repository (https://pypi.python.org/pypi/Glances/).
    """

    PYPI_API_URL = 'https://pypi.python.org/pypi/Glances/json'
    max_refresh_date = timedelta(days=7)

    def __init__(self, args, config):
        """Init the Outdated class"""
        self.args = args
        self.config = config

        # Set default value...
        self.data = {
            u'installed_version': __version__,
            u'latest_version': '0.0',
            u'refresh_date': datetime.now()
        }
        # Read the configuration file
        self.load_config(config)
        logger.debug("Check Glances version up-to-date: {0}".format(not self.args.disable_check_update))

        # And update !
        self.get_pypi_version()

    def load_config(self, config):
        """Load outdated parameter in the global section of the configuration file."""

        global_section = 'global'
        if (hasattr(config, 'has_section') and
                config.has_section(global_section)):
            self.args.disable_check_update = config.get_value(global_section, 'check_update').lower() == 'false'
        else:
            logger.debug("Can not find section {0} in the configuration file".format(global_section))
            return False

        return True

    def installed_version(self):
        return self.data['installed_version']

    def latest_version(self):
        return self.data['latest_version']

    def refresh_date(self):
        return self.data['refresh_date']

    def get_pypi_version(self):
        """Wrapper to get the latest Pypi version (async)
        The data are stored in a cached file
        Only update online once a week
        """
        if not outdated_tag or self.args.disable_check_update:
            return

        # If the cached file exist, read-it
        cached_data = self._load_cache()

        if cached_data == {}:
            # Update needed
            # Update and save the cache
            thread = threading.Thread(target=self._update_pypi_version)
            thread.start()
        else:
            # Update not needed
            self.data['latest_version'] = cached_data['latest_version']
            logger.debug("Get the Glances version from the cache file")

    def is_outdated(self):
        """Return True if a new version is available"""
        if self.args.disable_check_update:
            # Check is disabled by configuration
            return False

        if not outdated_tag:
            logger.debug("Python Request lib is not installed. Can not get last Glances version on Pypi.")
            return False

        logger.debug("Check Glances version (installed: {0} / latest: {1})".format(self.installed_version(), self.latest_version()))
        return LooseVersion(self.latest_version()) > LooseVersion(self.installed_version())

    def _load_cache(self):
        """Load cache file and return cached data"""
        # If the cached file exist, read-it
        cached_data = {}
        try:
            with open(os.path.join(self._cache_path(), 'glances-version.db'), 'rb') as f:
                cached_data = pickle.load(f)
        except IOError as e:
            logger.debug("Can not read the version cache file ({0})".format(e))
        else:
            logger.debug("Read the version cache file")
            if cached_data['installed_version'] != self.installed_version() or \
               datetime.now() - cached_data['refresh_date'] > self.max_refresh_date:
                # Reset the cache if:
                # - the installed version is different
                # - the refresh_date is > max_refresh_date
                cached_data = {}
        return cached_data

    def _save_cache(self):
        """Save data to a file"""
        # If the cached file exist, read-it
        try:
            with open(os.path.join(self._cache_path(), 'glances-version.db'), 'wb') as f:
                pickle.dump(self.data, f)
        except IOError:
            return False
        return True

    def _cache_path(self):
        """Return the cached file path"""
        if LINUX or BSD:
            return os.path.join(os.environ.get('XDG_CONFIG_HOME') or
                                os.path.expanduser('~/.config'),
                                __appname__)
        elif OSX:
            return os.path.join(os.path.expanduser('~/Library/Application Support/'),
                                __appname__)
        elif WINDOWS:
            return os.path.join(os.environ.get('APPDATA'), __appname__)

    def _update_pypi_version(self):
        """Get the latest Pypi version (as a string) via the Restful JSON API"""
        # Get the Nginx status
        logger.debug("Get latest Glances version from the Pypi Restfull API ({0})".format(self.PYPI_API_URL))

        # Update the current time
        self.data[u'refresh_date'] = datetime.now()

        try:
            res = requests.get(self.PYPI_API_URL)
        except Exception as e:
            logger.debug("Can not get the Glances version from the Pypi Restfull API ({0})".format(e))
        else:
            if res.ok:
                # Update data
                self.data[u'latest_version'] = json.loads(res.text)['info']['version']
                logger.debug("Save Glances version to the cache file")
            else:
                logger.debug("Can not get the Glances version from the Pypi Restfull API ({0})".format(res.reason))

        # Save result to the cache file
        # Note: also saved if the Glances Pypi version can not be grabed
        self._save_cache()

        return self.data
