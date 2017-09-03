#    Copyright (c) 2017 Christian Mollekopf <mollekopf@kolabsystems.com>
#
#    This library is free software; you can redistribute it and/or modify it
#    under the terms of the GNU Library General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or (at your
#    option) any later version.
#
#    This library is distributed in the hope that it will be useful, but WITHOUT
#    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
#    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Library General Public
#    License for more details.
#
#    You should have received a copy of the GNU Library General Public License
#    along with this library; see the file COPYING.LIB.  If not, write to the
#    Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#    02110-1301, USA.

import asyncio
import time
import logging
import re
import shlex
import json
from aioimaplib import aioimaplib

# Typical routine:
# LIST all
# LSUB all
# For every folder:
# * Search last two weeks
# * Fetch full body for the searched messages
# * Fetch all headers

# FIXME Not implemented (missing in aioimaplib):
# * METADATA
# * NAMESPACE
# * GETACL
# * MYRIGHTS
# * SORT

aioimaplib_logger = logging.getLogger('aioimaplib.aioimaplib')
sh = logging.StreamHandler()
sh.setLevel(logging.DEBUG)
sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s"))
aioimaplib_logger.addHandler(sh)

log = logging.getLogger(__name__)

class Error(Exception):
    def __init__(self, reason):
        super().__init__(reason)

def extractSelectableFolders(folderData):
    folders = []
    #The last line is reports the completed state
    for line in folderData[0:-1]:
        # print(line)
        parts = shlex.split(line)
        if not 'noselect' in parts[0].lower():
            folders.append(parts[-1])
    return folders

def checkResult(res):
    if res != 'OK':
        raise Error("Command failed")

def quote(s):
    return '"' + s + '"'

@asyncio.coroutine
def check_mailbox(host, port, user, password):
    start = time.time()
    timeout = 8

    #We retry in case of failure
    for i in range(3):
        try:
            #Establish a connection
            imap_client = aioimaplib.IMAP4(host=host, port=port, timeout=timeout)
            yield from imap_client.wait_hello_from_server()
        except asyncio.TimeoutError:
            # print("Retrying connection")
            log.warning('Retrying connection')
            continue
        else:
            break
    else:
        print("Failed to connect")
        log.error('Failed to connect')
        return {}

    yield from imap_client.login(user, password)

    #Get all folders
    res, folderData = yield from imap_client.list('*', '%')
    checkResult(res)
    folders = extractSelectableFolders(folderData)

    res, data = yield from imap_client.lsub('*', '%')
    checkResult(res)

    for folder in folders:
        # print("Checking folder ", folder)
        # Select folder if we can, otherwise skip
        try:
            res, data = yield from imap_client.select(quote(folder))
            checkResult(res)
        except Error:
            log.warning("Failed to select folder: %s" % quote(folder))
            print(data)
            continue

        # Search in subject
        res, data = yield from imap_client.uid_search('SUBJECT "subject"')
        checkResult(res)

        # Search in to
        res, data = yield from imap_client.uid_search('TO "doe"')
        checkResult(res)

        # Search in body
        res, data = yield from imap_client.uid_search('BODY "body"')
        checkResult(res)

        # Header or body
        res, data = yield from imap_client.uid_search('TEXT "body"')
        checkResult(res)

        # Search in body
        res, data = yield from imap_client.uid_search('SINCE 1-Feb-2017')
        checkResult(res)

        res, data = yield from imap_client.uid_search('UNSEEN')
        checkResult(res)

        # Search and fetch searched messages
        res, data = yield from imap_client.uid_search('ALL')
        checkResult(res)
        resultSet = data[0]
        if resultSet:
            res, data = yield from imap_client.uid('fetch', resultSet, '(UID RFC822.SIZE BODY.PEEK[])')

        # Fetch all headers
        res, data = yield from imap_client.uid('fetch', '1:*', '(UID RFC822.SIZE BODY.PEEK[])')
        checkResult(res)

        # Fetch all flags
        res, data = yield from imap_client.uid('fetch', '1:*', 'FLAGS')
        checkResult(res)

    yield from imap_client.logout()
    return {
            'id': "UserId",
            'totalTime': time.time() - start
           }


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    totalNumberOfRuns = 2

    tasks = []
    for i in range(totalNumberOfRuns):
        tasks.append(check_mailbox('localhost', 143, 'doe', 'pw'))

    resulttuple = loop.run_until_complete(asyncio.wait(tasks))

    results = []
    for resultset in resulttuple:
        for result in resultset:
            results.append(result.result())

    print("Results:")
    print(json.dumps(results, indent=4))
