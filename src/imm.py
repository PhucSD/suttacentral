#!/usr/bin/env python3.3

# Import user modules.
import config, textfunctions
from classes import *

import collections, functools, itertools, time, regex, hashlib, os, threading, math, datetime, pickle, cherrypy
from collections import OrderedDict, defaultdict, namedtuple

import csv
import uid

import logging
logger = logging.getLogger(__name__)

class ScCsvDialect(csv.Dialect):
    """ Make it explicit. This happens to be exactly what LibreOffice calc
    outputs on my Ubuntu machine. """
    quoting = csv.QUOTE_MINIMAL
    delimiter = ','
    quotechar = '"'
    doublequote = True
    lineterminator = '\n'
    strict=True

def numsortkey(input, index=0):
    """ Numerical sort. Handles identifiers well.

    If variable lengths ranges are involved (i.e. 1.2 vs 1.11.111) see
    'natsortkey', which is about 20x slower but handles such cases
    gracefully.
    """
    if type(input) is str:
        string = input
    else:
        string = input[index]
        if string is None:
            return []
    return ( [int(a) if a.isnumeric() else a
                   for a in regex.split(r'(\d+)', string)] )



def table_reader(tablename):
    """ Like csv.DictReader but returns named tuples (2x faster also) """
    with open(os.path.join(config.data, tablename + '.csv'), 'r', newline='') as f:
        reader = csv.reader(f, dialect=ScCsvDialect)
        field_names = next(reader)
        NtName = '_' + tablename.title()
        NT = namedtuple(NtName, field_names)
        globals()[NtName] = NT
        for row in reader:
            yield NT._make(row)

class _IMM:
    def __init__(self, timestamp):
        self.build_suttas(db)
        self.build_references(db)
        self.build_parallels_data(db)
        self.timestamp = timestamp
        self.build_stage2()
        
    def build_stage2(self):
        self.sort_translations()
        self.build_parallels()
        self.build_search_data()
        self.build_text_paths()        
    
    def __call__(self, uid):
        if uid in self.collections:
            return self.collections[uid]
        elif uid in self.divisions:
            return self.divisions[uid]
        elif uid in self.subdivisions:
            return self.subdivisions[uid]
        elif uid in self.suttas:
            return self.suttas[uid]
    
    def build_suttas(self, db):
        """ Build the sutta central database representation

        This starts from the highest level (i.e. collection) and works to
        the lowest level (i.e. parallels - the relationship between suttas)
        Since it is fully navigitable both up and down this means some
        elements can't be populated initially. This means that suttas
        insert themselves into the subdivision where they belong.

        Some attribute names undergo transformation (DRY). For example:
        sutta.sutta_uid -> sutta.uid

        Some attributes are transformed from a name into an object
        correspondence.sutta_uid -> parallel.sutta.uid
        
        Some tables are indexed as dicts, with the key being id or uid.
        These include:
        collection, division, subdivision, vagga, sutta
        
        When classes are contained within a class, for example, suttas in
        a subdivision, this is always represented by a list. That list will
        be sorted appropriately and can be directly outputted, generally
        without any need for filtering or sorting.

        When an attribute is a list or dict, the name always end in an 's'
        for example:
        dbr.suttas['sn1.1'].subdivision.division.subdivisions[0].suttas[0]

        lists always use zero-based indexing, while dicts are generally
        based on the table data, generally starting at 1. This inconsitency
        is not a problem since for lists only the ordering is meaningful,
        they are intended to be printed out as a whole unit using "for in"

        Some things, such as parallels, are not indexed at all, and are
        only accessable as attributes of the relevant suttas.
        
        The dbr also examines the file system. The fully qualified path to a 
        text can be acquired using:
        dbr.text_paths[lang][uid]

        """

        # Build Languages (indexed by id)
        
        self.languages = OrderedDict()
        for row in table_reader('language'):
            self.languages[row.uid] = Language(
                uid=row.uid,
                name=row.name,
                iso_code=row.iso_code,
                is_root=row.is_root)
                
        self.collections = OrderedDict()
        for row in table_reader('collection'):
            self.collections[row.uid] = Collection(
                uid=row.uid,
                name=row.name,
                abbrev_name=row.abbrev_name,
                language=self.languages[row.language],
                divisions=[] # Populate later
                )
        
        # Build divisions (indexed by uid)
        self.divisions = OrderedDict()
        for row in table_reader('division'):
            self.divisions[row.uid] = Division(
                uid=row.uid,
                name=row.name,
                acronym=row.acronym,
                subdiv_ind=row.subdiv_ind,
                collection=self.collections[row.collection_uid],
                subdivisions=[], # Populate later
            )
            self.collections[row.uid].divisions.append(self.divisions[-1])

        # Build subdivisions (indexed by uid)
        self.subdivisions = OrderedDict()
        for row in table_reader('subdivision'):
            self.subdivisions[row.uid] = Subdivision(
                uid=row.uid,
                name=row.name,
                vagga_ind=row.vagga_ind,
                vaggas=[], # Populate later
                suttas=[] # Populate later
            )
            # populate divisions.subdivisions
            div_uid = uid.subdiv_to_div(row.uid)
            self.divisions[div_uid].subdivisions.append(self.subdivisions[-1])

        # Build vaggas (indexed by id)
        self.vaggas = OrderedDict()
        for row in table_reader('vagga'):
            self.vaggas[row.vagga_id] = Vagga(
                uid=row.uid,
                subdivision=self.subdivisions[uids.vagga_to_subdiv(row.uid)],
                name=row.name,
                suttas=[], # Populate later
            )
        
        # Build suttas (indexed by uid)

        suttas = []
        for sutta in db.sutta.values():
            sutta_uid = sutta.sutta_uid
            subdivision = db.subdivision[sutta.subdivision_id]
            division_id = db.division[subdivision.division_id].division_id
            subdivision_uid = subdivision.subdivision_uid
            try:
                biblio_entry = BiblioEntry(
                    name=db.biblio_entry[sutta.biblio_entry_id].biblio_entry_name,
                    text=db.biblio_entry[sutta.biblio_entry_id].biblio_entry_text,)
            except KeyError:
                if sutta.biblio_entry_id:
                    logger.error('Database: Invalid biblio id {} for sutta {}'.format(sutta.biblio_entry_id, sutta_uid))
                biblio_entry = None
            try:
                vagga = self.vaggas[sutta.vagga_id]
            except KeyError:
                if sutta.vagga_id:
                    logger.error('Invalid vagga id {} for sutta {}'.format(sutta.vagga_id, sutta_uid))
                vagga = None
            try:
                lang = self.collection_languages[sutta.collection_language_id]
            except KeyError:
                logger.error('Invalid language id {} for sutta {}'.format(sutta.collection_language_id, sutta_uid))
                lang = None #Hack
            try:
                new_sutta = Sutta(
                    id=sutta.sutta_id,
                    uid=sutta_uid,
                    acronym=sutta.sutta_acronym,
                    alt_acronym=sutta.alt_sutta_acronym,
                    name=sutta.sutta_name,
                    coded_name=sutta.sutta_coded_name,
                    plain_name=sutta.sutta_plain_name,
                    number=sutta.sutta_number,
                    lang=lang,
                    subdivision=self.subdivisions[subdivision_uid],
                    vagga=vagga,
                    number_in_vagga=sutta.sutta_in_vagga_number,
                    volpage_info=sutta.volpage_info,
                    alt_volpage_info=sutta.alt_volpage_info,
                    biblio_entry=biblio_entry,
                    url=sutta.sutta_text_url_link,
                    url_info=sutta.url_extra_info_text,
                    translations=[],
                    parallels=[],
                )
                suttas.append( (sutta_uid, new_sutta) )
            except:
                print("Sutta: " + str(sutta))
                raise

        suttas = sorted(suttas, key=numsortkey)
        suttas = sorted(suttas, key=lambda t: t[1].subdivision.division.id)
        
        self.suttas = OrderedDict(suttas)
        # Populate subdivisions.suttas
        for sutta in self.suttas.values():
            sutta.subdivision.suttas.append(sutta)
        
        # Populate sutta_texts
        self.sutta_texts = SuttaTextCollection()
        for sutta in self.suttas.values():
            try:
                self.sutta_texts.add(sutta)
            except InvalidTextCollectionPathException:
                logger.warning('Could not add sutta {} to texts with url {}'.format(sutta.uid, sutta.url))
        self.sutta_texts.sort_lists()

        # Build tree from bottom up:

        for sutta in self.suttas.values():
            if sutta.vagga is None:
                try:
                    vagga = sutta.subdivision.vaggas[0]
                except IndexError:
                    null_vagga = Vagga(
                        id=0,
                        subdivision=sutta.subdivision,
                        name=None,
                        coded_name=None,
                        plain_name=None,
                        suttas=[],
                        )
                    sutta.subdivision.vaggas.append(null_vagga)
                    vagga = null_vagga
            else:
                vagga = sutta.vagga
            vagga.suttas.append(sutta)

        # Attach vaggas to subdivisions.
        for vagga in self.vaggas.values():
            # This is more reliable
            try:
                subdivision = vagga.suttas[0].subdivision
            except IndexError:
                logger.warning("Vagga id={} has no suttas.".format(vagga.id))
                subdivision = vagga.subdivision
            try:
                assert subdivision is vagga.subdivision
            except AssertionError:
                logger.warning("{} thinks it is in {}, but the vagga thinks it is in {}".format(vagga.suttas[0].uid, vagga.suttas[0].subdivision.uid, vagga.subdivision.uid))
                
            subdivision.vaggas.append(vagga)
        
        # Attach collections to collection_languages
        for collection in self.collections.values():
            collection.lang.collections.append(collection)

    def build_references(self, db):

        self.translation_texts = TranslationTextCollection()

        for key, row in db.reference.items():
            try:
                uid = db.sutta[row.sutta_id].sutta_uid
            except KeyError:
                self.errors.append('{} missing in sutta ({})'.format(
                    row.sutta_id, key))
            lang = (self.reference_languages[                                    row.reference_language_id])
            seq_nbr = row.reference_seq_nbr
            url = row.reference_url_link
            abstract = row.abstract_text
            sutta = self.suttas[uid]
            translation = Translation(seq_nbr, lang, url, abstract, sutta)
            sutta.translations.append(translation)

            # Populate translation_texts
            try:
                self.translation_texts.add(translation)
            except InvalidTextCollectionPathException:
                logger.warning(('Could not add translation {} {} to ' +
                    'translation texts with url {}').format(
                    translation.seq_nbr, translation.lang, url))

        self.translation_texts.sort_lists()

    def build_parallels_data(self, db):
        db = db
        fulls = defaultdict(set)
        partials = defaultdict(set)
        indirects = defaultdict(set)
        # initially we operate purely on ids using id, footnote tuples

        #Populate partial and full parallels
        for row in db.correspondence.values():
            if row.partial_corresp_ind == 'Y':
                partials[row.entry_id].add( (row.corresp_entry_id, row.footnote_text) )
                partials[row.corresp_entry_id].add( (row.entry_id, row.footnote_text) )
            else:
                fulls[row.entry_id].add( (row.corresp_entry_id, row.footnote_text) )
                fulls[row.corresp_entry_id].add( (row.entry_id, row.footnote_text) )

        # Populate indirect full parallels
        for id, parallels in fulls.items():
            for pid, footnote in parallels:
                if pid in fulls:
                    indirects[id].update(fulls[pid])

        for id, parallels in indirects.items():
            
            # Remove self and fulls
            indirects[id] -= set(a for a in indirects[id] if a[0] == id)
            #indirects[id] -= fulls[id]

        def test():
            class CaseSutta:
                def __init__(self, id, fulls, partials):
                    self.id = id
                    self.fulls = fulls
                    self.partials = partials

            case_suttas = (
                CaseSutta(id=16,
                        fulls={4155, 4187, 4188, 4189, 6036, 6099, 6100, 6105,
                            6106, 6156, 6205, 6283, 6289, 6291, 6297, 6301, 6312},
                        partials={2770, 3327, 3432, 4051, 6381, 6382,
                                6385, 6386, 6387, 8553, 8577, 8578, 2325}),
                CaseSutta(id=4218,
                        fulls={36, 3940, 4436, 5932, 6071},
                        partials=set()),
                )
            for case_sutta in case_suttas:
                id = case_sutta.id
                full_ids = set(a[0] for a in fulls[id].union(indirects[id]))
                part_ids = set(a[0] for a in partials[id])
            
                if full_ids == case_sutta.fulls and part_ids == case_sutta.partials:
                    logger.info("Parallels generation for id = {} passes test.".format(case_sutta.id))
                else:
                    logger.warning("Parallel generation anonomly id = {}:\n    missing: {}\n    extras: {}".format(
                        case_sutta.id,
                        (case_sutta.fulls - full_ids,
                         case_sutta.partials - part_ids),
                        (full_ids - case_sutta.fulls,
                         part_ids - case_sutta.partials)))
        test()

        # Nested list comprehensions for the sheer joy of it.
        self.parallels_data = {
            'fulls': [(db.sutta[s_id].sutta_uid,
                        [(db.sutta[p_id].sutta_uid, note) for p_id, note in parallels])
                        for (s_id, parallels) in fulls.items()],
            'indirects': [(db.sutta[s_id].sutta_uid,
                        [(db.sutta[p_id].sutta_uid, note) for p_id, note in parallels])
                        for (s_id, parallels) in indirects.items()],
            'partials': [(db.sutta[s_id].sutta_uid,
                        [(db.sutta[p_id].sutta_uid, note) for p_id, note in parallels])
                        for (s_id, parallels) in partials.items()],
            }

    def sort_translations(self):
        for sutta in self.suttas.values():
            sutta.translations.sort(key=Translation.sort_key)

    def build_parallels(self):
        fulls = self.parallels_data['fulls']
        indirects = self.parallels_data['indirects']
        partials = self.parallels_data['partials']
        del self.parallels_data
        
        for sutta_uid, parallels in fulls:
            sutta = self.suttas[sutta_uid]
            for p_uid, note in parallels:
                p_sutta = self.suttas[p_uid]
                sutta.parallels.append(Parallel(p_sutta, False, False, note))
                
        for sutta_uid, parallels in indirects:
            sutta = self.suttas[sutta_uid]
            for p_uid, note in parallels:
                p_sutta = self.suttas[p_uid]
                sutta.parallels.append(Parallel(p_sutta, False, True, note))

        for sutta_uid, parallels in partials:
            sutta = self.suttas[sutta_uid]
            for p_uid, note in parallels:
                p_sutta = self.suttas[p_uid]
                sutta.parallels.append(Parallel(p_sutta, True, False, note))

        for sutta in self.suttas.values():
            sutta.parallels.sort(key=Parallel.sort_key)

    def build_search_data(self):
        """ Build useful search data.

        Note that the size of the data is somewhat less than 2mb """

        suttastringsU = (["  {}  ".format("  ".join(
                                [sutta.uid,
                                sutta.lang.code,
                                sutta.acronym,
                                sutta.alt_acronym or '',
                                sutta.name,
                                sutta.coded_name,
                                sutta.plain_name,
                                sutta.volpage_info,
                                sutta.alt_volpage_info or '',
                                "  ".join( t.lang.code
                                    for t in sutta.translations,) or '',]))
                            for sutta in self.suttas.values()])
        suttastrings = [s.lower() for s in suttastringsU]
        # Only simplify the name.
        suttanamesimplified = (["  {}  ".format(
            textfunctions.simplify(sutta.name, sutta.lang.code))
            for sutta in self.suttas.values()])

        self.searchstrings = list(zip(self.suttas.values(), suttastrings, suttastringsU, suttanamesimplified))
       
    def build_text_paths(self):
        """ Provides fully qualified paths for all texts.
        
        Texts are keyed [lang][uid]
        Note that subfolders within a langroot are ignored. For example a file:
        text_root/pi/sn/56/sn56.11.html would be found by the key ('pi', 'sn56.11'),
        thus subfolders exist solely for ease of file organization.
        """
        import glob
        self.text_paths = collections.defaultdict(dict)
        
        for langroot in glob.glob(config.text_root + '/*'):
            lang = os.path.basename(langroot)
            for basedir, subdirs, filenames in os.walk(langroot):
                for filename in filenames:
                    uid = filename.replace('.html', '')
                    assert uid not in self.text_paths[lang]
                    self.text_paths[lang][uid] = os.path.join(basedir, filename)      

    def deep_md5(self, ids=False):
        """ Calculate a md5 for the data. Takes ~0.5s on a fast cpu.

        This will detect most inconsistencies in the contents of strings,
        ints, tuples, dicts and so on. As is always the case, carefully
        crafted different inputs could produce identical md5s, but this
        is highly unlikely to occur by chance.

        If ids is True, it additionally generates a md5 checksum on the
        id of every object encountered. The return value will be a tuple,
        (data_md5, id_md5). The data_md5 should be identical across
        different invocations of the program but the id_md5 will change.
        The id_md5 can detect some corruptions which the data_md5 won't,
        particularly when circular references are involved. For example
        data_md5 might not notice when the order of a list of parallels
        changes (if it has already seen each invidivudal parallel before),
        but id_md5 certainly will. On the other hand, at least in principle
        a change to an objects id need not invalidate the data - altough
        such things should not need to happen.
        
        """
        stack = []
        #md5 = hashlib.md5()
        #for b in atomicfy(self.collections, stack=stack):
            #md5.update(b)
        md5 = hashlib.md5(b"".join(atomicfy(self.collections, stack=stack)))
        if ids:
            md5ids = hashlib.md5(b"".join([str(id(a)).encode() for a in stack]))
            return (md5.hexdigest(), md5ids.hexdigest())
        return md5.hexdigest()

    def check_md5(self, exception=None):
        new_md5 = self.deep_md5(ids=True)
        if not hasattr(self, 'dbr_md5'):
            self.dbr_md5 = new_md5
            logger.info('Generating md5 {}.'.format(new_md5))
        else:
            if self.dbr_md5 == new_md5:
                logger.debug('md5s match')
            else:
                logger.error('md5 mismatch')
                if exception:
                    raise exception

def atomicfy(start, stack=None):
    """ Slice a unit into 'atomic' units (strs, bytes and ints)

    The individuals 'atoms' are yielded as bytes objects, suitable for
    consumption by a hashlib md5, sha or other function.

    If called with the stack attribute, stack must be a list. After the
    function as run, it will be populated with every object the function
    has seen. This has two purposes, first a stack of starting points
    can be entered, secondly you can perform further manupulations on the
    contents of the passed in stack.

    """

    if stack is None:
        stack = [start]
    elif start is not None and start not in stack:
        stack.append(start)
    touched = set()

    # Iterating over an object which is getting longer is fine in python.
    for obj in stack:
        oid = id(obj)
        try:
            if oid in touched:
                continue
            touched.add(oid)
        except TypeError:
            touched = set([oid])

        try:
            length = len(obj)
            # Object has length
            if length == 0:
                #For empty container, yield the type
                yield b't' + str(type(obj)).encode()
                continue
            
            try:
                yield obj.encode() # String?
                continue
            except AttributeError:
                try:
                    yield b'b' + obj # Bytes or btye-like?
                    continue
                except TypeError:
                    pass
            
            # Yield the length as an additional check
            yield b'l' + str(length).encode()
            
            try:
                for pair in obj.items(): # Dict-like?
                    stack.extend(pair)
                continue
            except AttributeError:
                pass

            try:
                stack.extend(obj) # List-like?
                continue
            except AttributeError:
                pass

        except TypeError:
            # Atomic (length-less) object.
            pass

        try:
            test = int(obj)
            yield b'n' + str(obj).encode()
            #intobj = abs(int(obj))
            #yield 'n' + intobj.tobytes(math.ceil(math.log(intobj+1, 2) / 8), 'big')
            continue
        except TypeError:
            pass

        # Yield the type. Useful for user classes.
        yield b't' + str(type(obj)).encode()

def getDBR():
    """ Get an instance of the DBR.

    Use only this function to get an instance of the DBR. For most intents
    and purposes the DBR should be considered a singleton. However it can
    be regenerated, and while being regenerated, a 'stale' copy can be be
    served, hence multiple versions can exist for a short time. (The stale
    copies will be garbage collected when they fall out of scope)
    
    If the dbr is being generated, this function will block until it is
    ready. If the dbr has already been generated, it is virtually free to
    call.

    """

    try:
        assert _dbr, _dbr.timestamp
        return _dbr
    except NameError:
        updater.build_completed.wait()
        return _dbr

class Updater(threading.Thread):
    """ Ensures the dbr is available and up to date.

    The Updater is responsible for detecting changes in the mysql database
    when changes are detected, it rebuilds the sqlite database. The sqlite
    database is then used as the basis for building the dbr. It will also
    notice if the sqlite database has been replaced with a new one with a
    new timestamp but otherwise does not expect the sqlite database to
    change.

    While this may seem like a slightly convoluted approach, it does have
    benefits:
    1) sqlite3 is built into the python standard library, which makes
       possible a lightweight distribution which doesn't require mysql.
    2) In general, sqlite3 is faster than mysql, this is particulary so
       for python3 which is backwards in it's mysql support.
    3) Other subsystems (such as search and text analysis) rely heavily
       on sqlite3, so rather than introducing a new dependency, it is
       reducing an external one.

    """
    
    build_completed = threading.Event() # Signal that the dbr is ready.
    
    def get_sqlite_timestamp(self):
        with sqlite3.connect(config.sqlite['db']) as con:
            try:
                return con.execute('SELECT value FROM dbr_info WHERE label=?', ('mysql_timestamp', )).fetchone()[0]
            except (TypeError, sqlite3.OperationalError):
                return 'NOTFOUND'

    def get_mysql_timestamp(self):
        """ Return the timestamp of the last modification.

        This is a fast function, it only takes a few milliseconds"""
        con = mysql.connect(**config.mysql)
        cur = con.cursor(raw=True)
        cur.execute("""
            SELECT MAX(Update_time)
            FROM information_schema.tables
            WHERE table_schema = '%s';
        """ % config.mysql['db'])
        timestamp = cur.fetchone()[0].decode()
        con.close()
        return timestamp

    def set_sqlite_timestamp(self, timestamp):
        with sqlite3.connect(config.sqlite['db']) as con:
            con.execute('CREATE TABLE dbr_info (label UNIQUE, value)')
            con.execute('INSERT INTO dbr_info VALUES (?, ?)', ('mysql_timestamp', timestamp) )
    
    def convertdb(self, mysql_timestamp):
        from mysql2sqlite3 import convert
        convert(config.mysql, lite_db=config.sqlite['db'], cull_list=('timestamp', 'login'), no_index=True)
        self.set_sqlite_timestamp(mysql_timestamp)

    def run(self):
        global _dbr
        while True:
            # Check if sqlite db is up to date
            start=time.time()
            sqlite_timestamp = self.get_sqlite_timestamp()
            try:
                mysql_timestamp = self.get_mysql_timestamp()
                if mysql_timestamp != sqlite_timestamp:
                    logger.info(('SQLite database (t=%s) out of sync with' +
                                ' MySQL database (t=%s); converting...') %
                                (sqlite_timestamp, mysql_timestamp))
                    start_build=time.time()
                    self.convertdb(mysql_timestamp)
                    sqlite_timestamp = mysql_timestamp
                    logger.info('Conversion took {} seconds'.format(time.time()-start_build))
            except:
                # We can continue if mysql is not available, but sqlite
                # is. But for the moment, we will raise here.
                if config.debug:
                    raise
            # Check if dbr is up to date
            try:
                if _dbr.timestamp != sqlite_timestamp:
                    raise ValueError
            except (NameError, ValueError) as e:
                # _dbr doesn't exist, or is out of date.
                logger.info('dbr requires rebuilding because {}'.format(e))
                start=time.time()
                try:
                    new_dbr = _DBR(sqlite_timestamp)
                except Exception as e:
                    logger.error("Critical Error: DBR buid failed.")
                    raise e

                # Make the fresh copy available
                _dbr = new_dbr
                self.build_completed.set()

                logger.info('dbr build took {} seconds'.format(time.time()-start))

            # Do consistency checking.
            _dbr.check_md5()
            time.sleep(config.db_refresh_interval)

updater = Updater(name='dbr_updater', daemon=True)
updater.start()

def stress_test(count=10):
    import random
    def get_a():
        time.sleep(random.random()/10)
        print("Getting a DBR")
        dbr = getDBR()
        print("Got a DBR")
        time.sleep(random.random() * 10)

    threads = [threading.Thread(target=get_a) for i in range(1, count)]
    for t in threads:
        print("Starting thread")
        t.start()