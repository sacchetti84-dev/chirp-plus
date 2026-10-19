# Copyright 2026 CHIRP contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Program the same image into several radios, one after the other.

No UI here: the caller gives a function that opens the serial port, and
gets one Result per radio.
"""

import dataclasses
import logging
import time

from chirp import radio_compare

LOG = logging.getLogger(__name__)

# Seconds of silence a Baofeng needs to leave program mode after a clone
SETTLE_SECONDS = 3.5


@dataclasses.dataclass
class Result:
    number: int
    uploaded: bool = False
    verified: bool = None    # None: not checked
    error: str = ''
    problems: int = 0
    seconds: float = 0.0

    @property
    def ok(self):
        return self.uploaded and self.verified is not False and \
            not self.error


@dataclasses.dataclass
class Batch:
    radio: object            # the image to program, a CloneModeRadio
    open_pipe: object        # fn() -> open serial port
    verify: bool = True
    results: list = dataclasses.field(default_factory=list)

    @property
    def done(self):
        return len(self.results)

    @property
    def good(self):
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self):
        return self.done - self.good

    def program_next(self, status=None, sleep=time.sleep):
        """Upload (and verify) the radio connected now"""
        result = Result(self.done + 1)
        started = time.monotonic()
        try:
            self._upload(status)
            result.uploaded = True
            if self.verify:
                sleep(SETTLE_SECONDS)
                method, problems = self._verify(status)
                result.problems = len(problems)
                result.verified = not problems
        except Exception as e:
            LOG.exception('Radio %i failed: %s', result.number, e)
            result.error = str(e) or e.__class__.__name__
        result.seconds = time.monotonic() - started
        self.results.append(result)
        return result

    def _upload(self, status):
        pipe = self.open_pipe()
        try:
            self.radio.set_pipe(pipe)
            if status:
                self.radio.status_fn = status
            self.radio.sync_out()
        finally:
            _close(pipe)

    def _verify(self, status):
        pipe = self.open_pipe()
        try:
            readback = type(self.radio)(pipe)
            if status:
                readback.status_fn = status
            readback.sync_in()
        finally:
            _close(pipe)
        return radio_compare.verify_upload(self.radio, readback)


def _close(pipe):
    try:
        pipe.close()
    except Exception:
        pass
