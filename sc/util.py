import babel.dates
import errno
import fcntl
import os
import pathlib
import textwrap
import time
import regex
from collections import deque
from contextlib import contextmanager
from datetime import datetime

from . import config

@contextmanager
def filelock(path, block=True):
    """A simple, file-based exclusive-lock pattern.

    Blocking Example:
        >>> with filelock('mylock'):
        >>>     print('Lock acquired.')

    Non-blocking Example:
        >>> with filelock('mylock', block=False) as acquired:
        >>>     if acquired:
        >>>         print('Sweet! Lock acquired.')
        >>>     else:
        >>>         print('Bummer. Could not acquire lock.')
    """
    path = pathlib.Path(path)
    with path.open('w') as f:
        operation = fcntl.LOCK_EX
        if not block:
            operation |= fcntl.LOCK_NB
        try:
            fcntl.flock(f, operation)
            acquired = True
        except OSError as e:
            if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
                acquired = False
            else:
                raise
        yield acquired

def format_date(value, format='short', locale=config.default_locale):
    return babel.dates.format_date(value, format=format, locale=locale)

def format_datetime(value, format='short', locale=config.default_locale):
    rfc3339 = format == 'rfc3339'
    if rfc3339:
        format = 'yyyy-MM-ddTHH:mm:ssZ'
    datetime = babel.dates.format_datetime(value, format=format, locale=locale)
    if rfc3339:
        datetime = datetime[:-2] + ':' + datetime[-2:]
    return datetime

def format_time(value, format='short', locale=config.default_locale):
    return babel.dates.format_time(value, format=format, locale=locale)

def format_timedelta(value, locale=config.default_locale):
    delta = datetime.now() - value
    return babel.dates.format_timedelta(delta, locale=locale)

def wrap(text, width=80, indent=0):
    """Returns text wrapped and indented."""
    text = '\n'.join([
        textwrap.fill(line, width - indent, break_long_words=False,
            break_on_hyphens=False) for line in text.splitlines()
    ])
    return textwrap.indent(text.strip(), ' ' * indent)

def numericsortkey(string, _rex=regex.compile(r'(\d+)')):
    """ Intelligently sorts most kinds of data.
    
    Should work on absolutely any configuration of characters in a string
    this doesn't mean it'll always order sensibly, just that it wont throw
    any 'TypeError: unorderable types' exceptions.
    Also works on all unicode decimal characters, not just ASCII 0-9.
    
    Does not handle dotted ranges unless the string ends with the range.
    >>> sorted(['1', '1.1', '1.1.1'], key=numericsortkey)
    ['1', '1.1', '1.1.1']
    
    >>> sorted(['1.txt', '1.1.txt', '1.1.1.txt'], key=numericsortkey)
    ['1.1.1.txt', '1.1.txt', '1.txt']
    
    """
    
    # if regex.fullmatch('\d+', s) then int(s) is valid, and vice-verca.
    return [int(s) if i % 2 else s for i, s in enumerate(_rex.split(string))]

def humansortkey(string, _rex=regex.compile(r'(\d+(?:[.-]\d+)*)')):
    """ Properly sorts more constructions than numericsort
    
    Should generally be preferred to numericsort unless a simpler ordering
    is required.
    
    >>> sorted(['1.txt', '1.1.txt', '1.1.1.txt'], key=humansortkey)
    ['1.txt', '1.1.txt', '1.1.1.txt']
    
    """
    # With split, every second element will be the one in the capturing group.
    return [numericsortkey(s) if i % 2 else s 
            for i, s in enumerate(_rex.split(string))]

class TimedCache:
    """ A lightweight cache which removes content after a given time
    
    Useful for when you anticipate multiple calls to a function with the
    same parameters, but want the guarantee the returned object wont be older
    than lifetime seconds.
    
    Must be used in a Try/Catch clause:
    >>> try: cache[key]
    >>> except KeyError:
    
    """
    
    __slots__ = ('_values', '_lifetime', '_added', '_maxsize')
    def __init__(self, lifetime=300, maxsize=100):
        self._lifetime = lifetime
        self._added = deque()
        self._values = {}
        self._maxsize = maxsize
    
    def __getitem__(self, key):
        now = time.time()
        try:
            while True:
                append_time, doomed_key = self._added.popleft()
                if now - append_time > self._lifetime or len(self._added) > self._maxsize:
                    del self._values[doomed_key]
                else:
                    # pop and put back is for thread safety
                    self._added.appendleft([append_time, doomed_key])
                    break
        except IndexError:
            pass
        
        return self._values.__getitem__(key)
    
    def __setitem__(self, key, value):
        # This isn't perfect, if a key is added multiple times in succession
        # it wont work properly, but it also wont break catastrophically.
        # Desired performance is only obtained when using the cache normally.
        # (i.e. setting an item only when the key isn't in the cache)
        self._added.append((time.time(), key))
        self._values.__setitem__(key, value)
        
    def __contains__(self, key):
        raise RuntimeError("Inappropriate operation, use Try/Catch.")