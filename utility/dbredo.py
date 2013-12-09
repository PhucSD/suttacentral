import os, csv, regex, collections
import env
import scdb, config

collection_fields = ('uid', 'name', 'abbrev_name', 'language')

division_fields = ('uid', 'collection_uid', 'name', 'acronym', 'subdiv_ind')

subdivision_fields = ('uid', 'name', 'vagga_ind')

vagga_fields = ('uid', 'name')

sutta_fields = ('name', 'uid', 'language', 'vagga', 'acronym', 'volpage')

external_text_fields = ('sutta_uid', 'language', 'abstract', 'url')

correspondence_fields = ('sutta_uid', 'other_uid', 'partial', 'footnote')

biblio_fields = ('sutta_uid', 'name', 'text')

collection_uids = {1: 'pi.su', 2: 'pi.vi', 3: 'pi.ab', 4: 'zh.su', 5: 'zh.vi', 6: 'zh.ab', 7: 'bo.su', 8: 'skt.su', 9: 'prk', 10: 'gandh', 11: 'khot', 12: 'uigh'}

language_fields = ('uid', 'iso_code', 'name', 'root')

class ScDialect(csv.Dialect):
    quoting = csv.QUOTE_MINIMAL
    delimiter = ','
    quotechar = '"'
    doublequote = True
    lineterminator = '\n'

def openforwriter(filename):
    return open(os.path.join(outdir, filename), 'w', newline='')

def scwriter(fp):
    return csv.writer(fp, dialect=ScDialect)

dbr = scdb.getDBR()
db = scdb.db_grab(scdb.sqlite3.connect(config.sqlite['db']))

outdir = config.app['data']

def decompose_uid(uid):
    if '.' in uid:
        m = regex.match(r'(\p{alpha}+(?:-\d+)?)(\d*)\.(.*)', uid)
    else:
        m = regex.match(r'(\p{alpha}+(?:-\d+)?)()', uid)
    division = m[1]
    if m[2]:
        subdivision = division + m[2]
    else:
        subdivision = division + '-nosub'
    return (division, subdivision)


used_lang = set()
references = []
biblio_entries = []
vaggas = collections.OrderedDict()
def add_references(sutta):
    if sutta.url:
        references.append((sutta.uid, sutta.lang.code, sutta.url_info, sutta.url))
    
    references.extend((sutta.uid, tr.lang.code, tr.abstract, tr.url)
                            for tr in sutta.translations)
    used_lang.update(tr.lang.code for tr in sutta.translations)

def add_biblio_entry(sutta):
    if sutta.biblio_entry:
        biblio_entries.append((sutta.uid, sutta.biblio_entry.name, sutta.biblio_entry.text))

with openforwriter('sutta.csv') as sutfile:
    sut_writer = scwriter(sutfile)
    sut_writer.writerow(sutta_fields)


    for sutta in dbr.suttas.values():
        try:
            divi, subd = decompose_uid(sutta.uid)
        except TypeError:
            print(sutta.uid)
            continue
        
        add_references(sutta)
        add_biblio_entry(sutta)
        
        if sutta.vagga:
            vagga_uid = '{}/{}'.format(subd,
                db.vagga[sutta.vagga.id].vagga_number)
            vaggas[vagga_uid] = sutta.vagga.name
            vagga_uid += '/{}'.format(sutta.number_in_vagga)
        else:
            vagga_uid = None
        
        acronym = sutta.acronym
        if sutta.alt_acronym:
            acronym += '//' + sutta.alt_acronym
        volpage = sutta.volpage_info
        if sutta.alt_volpage_info:
            volpage += '//' + sutta.alt_volpage_info
        sut_writer.writerow([sutta.name,
            sutta.uid, 
            sutta.lang.code, 
            vagga_uid, 
            acronym,
            volpage])

with openforwriter('external_text.csv') as etfile:
    et_writer = scwriter(etfile)
    et_writer.writerow(external_text_fields)
    et_writer.writerows(references)

with openforwriter('correspondence.csv') as corrfile:
    writer = scwriter(corrfile)
    writer.writerow(correspondence_fields)
    for corr in db.correspondence.values():
        writer.writerow([
            db.sutta[corr.entry_id].sutta_uid,
            db.sutta[corr.corresp_entry_id].sutta_uid,
            1 if corr.partial_corresp_ind == 'Y' else None,
            corr.footnote_text])

with openforwriter('biblio.csv') as bibfile:
    writer = scwriter(bibfile)
    writer.writerow(biblio_fields)
    writer.writerows(biblio_entries)

with openforwriter('collection.csv') as colfile:
    writer = scwriter(colfile)
    writer.writerow(collection_fields)
    for coll in dbr.collections.values():
        writer.writerow([
            collection_uids[coll.id],
            coll.name,
            coll.abbrev_name,
            coll.lang.code])

with openforwriter('division.csv') as divfile:
    writer = scwriter(divfile)
    writer.writerow(division_fields)
    for div in dbr.divisions.values():
        writer.writerow([
            div.uid,
            collection_uids[div.collection.id],
            div.name,
            div.acronym,
            1 if div.subdiv_ind == 'Y' else None])
        
with openforwriter('subdivision.csv') as sdfile:
    writer = scwriter(sdfile)
    writer.writerow(subdivision_fields)
    for sd in dbr.subdivisions.values():
        writer.writerow([
            sd.uid,
            sd.name,
            sd.vagga_numbering_ind])

with openforwriter('vagga.csv') as vagfile:
    writer = scwriter(vagfile)
    writer.writerow(vagga_fields)
    writer.writerows(vaggas.items())

def fix_lang_uid(uid):
    if uid in ('sa', 'sk'):
        return 'skt'
    elif uid in ('ot'):
        return 'oth'
    
    return uid

with openforwriter('language.csv') as langfile:
    writer = scwriter(langfile)
    writer.writerow(language_fields)
    languages = []
    seen = set()
    for lang in dbr.collection_languages.values():
        uid = fix_lang_uid(lang.code)
        seen.add(uid)
        languages.append([uid, lang.code, lang.name, 1])
    
    for lang in dbr.reference_languages.values():
        if lang.code not in used_lang:
            continue
        uid = fix_lang_uid(lang.code)
        if uid in seen:
            uid = 'm' + uid
        languages.append([uid, lang.code, lang.name, None])
    
    languages.sort(key=lambda t: (t[1], not t[3]))
    writer.writerows(languages)
    
language_fields = ('uid', 'iso_code', 'name')