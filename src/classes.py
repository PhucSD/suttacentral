import regex
from collections import namedtuple

TranslationBase = namedtuple('Translation',
                                     'seq_nbr, lang, url, abstract, sutta')

ParallelBase = namedtuple('ParallelBase',
                                  'sutta, partial, indirect, footnote')

BiblioEntry = namedtuple('BiblioEntry', 'name, text')

DivisionBase = namedtuple('DivisionBase', '''
    id, uid, collection, name, coded_name, plain_name, acronym,
    subdiv_ind, note_text, subdivisions''')
    
SubdivisionBase = namedtuple('SubdivisionBase',
    'id, uid, division, name, coded_name, plain_name, acronym, vagga_numbering_ind, vaggas, suttas')

VaggaBase = namedtuple('VaggaBase', ('id', 'subdivision', 'name', 'coded_name', 'plain_name', 'suttas') )

CollectionBase = namedtuple('CollectionBase', ('id', 'name', 'abbrev_name', 'lang', 'note_text', 'divisions') )

SuttaBase = namedtuple('SuttaBase', (
        'id', 'uid', 'acronym', 'alt_acronym', 'name',
        'coded_name', 'plain_name', 'number', 'lang', 'subdivision',
        'vagga', 'number_in_vagga', 'volpage_info', 'alt_volpage_info',
        'biblio_entry', 'url', 'url_info', 'translations', 'parallels',) )
CollectionLanguage = namedtuple('CollectionLanguage', 'id, name, abbrev, code, collections')
ReferenceLanguage = namedtuple('ReferenceLanguage', 'id, name, abbrev, code')

class SearchString(str):
    __slots__ = ('target')
    def __new__(cls, value, target, **kwargs):
        obj = str.__new__(cls, value, **kwargs)
        obj.target = target
        return obj

# Because a Sutta contains references to other complete objects which
# each have their own verbose default __repr__, it is necessary to make
# a custom __repr__ which summarises the enclosed objects.
class Sutta(SuttaBase):
    __slots__ = ()
    def __repr__(self):
        return """< Sutta: "{self.name}"
    id={self.id},
    uid={self.uid},
    subdivision=<{self.subdivision.uid}>,
    number={self.number},
    lang=<{self.lang.code}>,
    acronym={self.acronym},
    alt_acronym={self.alt_acronym},
    name={self.name},
    coded_name={self.coded_name},
    plain_name={self.plain_name},
    vagga=vagga,
    number_in_vagga={self.number_in_vagga},
    volpage_info={self.volpage_info}, alt_volpage_info={self.alt_volpage_info},
    biblio_entry={self.biblio_entry},
    url={self.url},
    url_info={self.url_info},
    translations={translations},
    parallels={parallels} >\n""".format(
        self=self,
        vagga="<{}>".format(self.vagga.name) if self.vagga else '',
        translations="[{}]".format(", ".join(
        "<{}>".format(a.lang.code) for a in self.translations)),
        parallels="[{}]".format(", ".join(
            "<{}{}>".format(a.sutta.uid, '*' if a.partial else '')
                for a in self.parallels)),
        )
    def __hash__(self):
        return self.id

    def canon_filename(self):
        return '/{lang}/{uid}.html'.format(lang=self.lang.code, uid=self.uid)
    
    def canon_url(self):
        return '/{uid}/{lang}/'.format(uid=self.uid, lang=self.lang.code)

class Vagga(VaggaBase):
    __slots__ = ()
    def __repr__(self):
        return """<Vagga: "{self.name}"
    id={self.id},
    subdivision=<{self.subdivision.uid}>,
    name={self.name},
    coded_name={self.coded_name},
    plain_name={self.plain_name},
    suttas=[{suttas}]\n""".format(self=self,
        suttas=", ".join("<{}>".format(sutta.uid) for sutta in self.suttas))
    

class Parallel(ParallelBase):
    __slots__ = ()
    def __repr__(self):
        return ("<Parallel: sutta={self.sutta.uid}, "
        "partial={self.partial}, "
        "footnote={self.footnote}>").format(self=self)

    @staticmethod
    def sort_key(p):
        """The canonical ordering as follows:
            1) full, then partial
            2) sutta language id,
            3) sutta subdivision id,
            4) sutta number.
        To be used with sort() or sorted()."""
        def langhack(lang_id):
            if lang_id == 2:
                return 1
            if lang_id == 1:
                return 2
            return lang_id
        s = p.sutta
        return (langhack(s.lang.id),
                p.partial,
                s.subdivision.id,
                s.number)

class Translation(TranslationBase):
    __slots__ = ()

    @staticmethod
    def sort_key(t):
        """The canonical ordering as follows:
            1) language id
            2) sequence number
        To be used with sort() or sorted()."""
        return (not t.url.startswith('/'), t.lang.id, t.seq_nbr)

class Collection(CollectionBase):
    __slots__ = ()
    def __repr__(self):
        return """<Collection: "{self.name}",
    id={self.id},
    name={self.name},
    abbrev_name={self.abbrev_name},
    lang=<{self.lang.code}>,
    note_text={self.note_text},
    divisions={divisions}\n""".format(
        self=self,
        divisions="[{}]".format(", ".join(
            "<{}>".format(a.name) for a in self.divisions)))
        
    

class Division(DivisionBase):
    __slots__ = ()
    def __repr__(self):
        return """<Division: "{self.name}"
    id={self.id},
    uid={self.uid},
    collection={collection},
    name={self.name},
    coded_name={self.coded_name},
    plain_name={self.plain_name},
    acronym={self.acronym},
    subdiv_ind={self.subdiv_ind},
    note_text={self.note_text},
    subdivisions={subdivisions}\n""".format(self=self,
        collection="<Collection>",
        subdivisions="[{}]".format(
            ", ".join("<{}>".format(a.uid)
                for a in self.subdivisions)),
        )
    def has_subdivisions(self):
        return len(self.subdivisions) > 1

class Subdivision(SubdivisionBase):
    __slots__ = ()
    def __repr__(self):
        return """<Subdivision: "{self.name}"
    id={self.id}
    uid={self.uid}
    division=<{self.division.uid}>
    name={self.name}
    coded_name={self.coded_name}
    plain_name={self.plain_name}
    acronym={self.acronym}
    vagga_numbering_ind={self.vagga_numbering_ind},
    vaggas=[{vaggas}],
    suttas=[{suttas}]\n""".format(
        self=self,
        vaggas=", ".join(str(len(a)) for a in self.vaggas),
        suttas=", ".join("<{}>".format(a.uid) for a in self.suttas),
        )



class SearchResults:
    def __init__(self, query, categories=None):
        self.query = query
        self.categories = categories or []
    def add(self, category):
        self.categories.append(category)

ResultSection = namedtuple('ResultSection', 'title, results')
class ResultsCategory:
    type = None # Stringly typing :).
    caption = None
    def __init__(self, sections=None, total=None):
        self.sections = sections or []
        self.total = total
    def add(self, title, entries):
        self.sections.append( ResultSection(title, entries) )
    def add_row(self, row):
        "Add a row to the most recently added section"
        self.sections[-1][1].append(row)
        
SuttaSection = namedtuple('SuttaSection', 'title, suttas')
class SuttaResultsCategory(ResultsCategory):
    type = 'sutta'
    caption = 'Suttas:'
    def add(self, title, suttas):
        self.sections.append( SuttaSection(title, suttas) )

class DictionaryResultsCategory(ResultsCategory):
    type = 'dict'
    caption = 'Dictionaries:'

class FulltextResultsCategory(ResultsCategory):
    type = 'fulltext'
    caption = 'Texts:'

class HTMLRow:
    """Insert a row of arbitary HTML code into a results listing.

    It is the responsibility of the template to put it in the correct
    containing element (i.e. a <li>, or a <tr><td>...)

    """
    def __init__(self, html):
        self.html=html

class InvalidTextCollectionPathException(Exception):
    pass

class TextCollection(dict):
    """A dictionary of lists of internally hosted suttas or translations
       keyed by their internally hosted path."""

    def add(self, obj):
        """Adds a Sutta or Translation if possible."""
        url = obj.url
        if url and url.startswith('/'):
            path = self._normalize_path(url)
            if self._valid_path(path):
                self.setdefault(path, []).append(obj)
            else:
                raise InvalidTextCollectionPathException(
                    'Unexpected path {}'.format(path))

    def sort_lists(self):
        """Sorts each list of suttas or translations."""
        for lst in self.values():
            lst.sort(key=self.list_sort_key)

    def _normalize_path(self, path):
        """Strip the leading / and any trailing / or fragment"""
        return regex.sub(r'/?(#.+)?$', '', path[1:])

    def _valid_path(self, path):
        return regex.match(r'^[-.a-z0-9]+/[a-z]+$', path)

class SuttaTextCollection(TextCollection):

    @staticmethod
    def list_sort_key(sutta):
        return sutta.number

class TranslationTextCollection(TextCollection):

    @staticmethod
    def list_sort_key(translation):
        # The only reasonable differentiator seems to be the url
        # fragment, which will (hopefully) be of the form <number> or
        # <number>-<number>, so we use that for now..."""
        matches = regex.match(r'^.+#([0-9]+)(?:-([0-9]+))?$', translation.url)
        if matches:
            return (int(matches[1]), int(matches[2] or 0))
        else:
            return (0, 0)