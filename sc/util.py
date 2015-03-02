import babel.dates
import errno
import fcntl
import os
import pathlib
import textwrap
import time
import regex
from collections import deque
import itertools
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

class ConciseRepr:
    __slots__ = ()
    def __repr__(self):
        from numbers import Number
        details = []
        
        for attr in sorted(self._fields, key=lambda s: '' if s == 'uid' else s):
            details.append('\n    {}='.format(attr))
            value = getattr(self, attr)
            if isinstance(value, str):
                details[-1] += repr(value)
            elif isinstance(value, Number):
                details[-1] += str(value)
            elif isinstance(value, ConciseRepr):
                if hasattr(value, 'uid'):
                    details[-1] += '<{} {}>'.format(type(value).__qualname__, value.uid)
                else:
                    details[-1] += '<{}>'.format(type(value).__qualname__)
            else:
                try:
                    details[-1] += self._repr_len(value)
                except TypeError:
                    details[-1] += repr(value)
        
        return '<{} {}>'.format(type(self).__qualname__,
            ''.join(details))
    
    def _repr_len(self, value):

        if len(value) == 0:
            return "{}()".format(type(value).__qualname__)
        
        if isinstance(value, dict):
            content = value.values()
        else:
            content = value
        
        types = {type(e) for e in content}
        
        if len(types) == 1:
            typestring = 'of type <{}>'.format(
                type(next(iter(content))).__qualname__)
        else:
            typestring = 'of mixed type'
        
        return '{}({} {})'.format(
            type(value).__qualname__, len(value), typestring)

def recursive_merge(dict1, dict2):
    """ Merge dict2 into dict1

    where both dict2 and dict1 have the same key, and the value
    are both dicts, then the dicts are recusively merged.
    where the values can otherwise be meaningfully merged such
    as sets or lists, merge in a sensible way.
    Where both have the same key, but the values cannot be merged
    then clobber dict1's value with dict2's value.

    dict1 provides the default values
    """
    
    for key in set(dict1.keys()) | set(dict2.keys()):
        if key in dict1 and key in dict2:
            val1, val2 = dict1[key], dict2[key]
            if isinstance(val1, dict) and isinstance(val2, dict):
                recursive_merge(val1, val2)
            elif isinstance(val1, set) and isinstance(val2, set):
                val1.update(val2)
            elif isinstance(val1, list) and isinstance(val2, list):
                val1set = set(val1)
                for val in val2:
                    if val not in val1set:
                        val1.append(val)
            else:
                dict1[key] = val2
        elif key in dict1:
            pass
        elif key in dict2:
            dict1[key] = dict2[key]

    return dict1
    
def grouper(n, iterable, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)

def unique(iterable, key=None):
    "List unique elements, preserving order. Remember all elements ever seen."
    # unique_everseen('AAAABBBCCDAABBB') --> A B C D
    # unique_everseen('ABBCcAD', str.lower) --> A B C D
    seen = set()
    seen_add = seen.add
    if key is None:
        for element in itertools.filterfalse(seen.__contains__, iterable):
            seen_add(element)
            yield element
    else:
        for element in iterable:
            k = key(element)
            if k not in seen:
                seen_add(k)
                yield element
