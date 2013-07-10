import bisect, math, functools
import scdb, classes, textfunctions

class Ranker:
    def __init__(self, query):
        self.query_cased = query
        self.query = query.casefold()
        self.query_whole = ' ' + self.query.strip() + ' '
        self.query_starts = ' ' + self.query.strip()
        self.query_simple = textfunctions.simplify_pali(self.query)

    def __call__(self, input):
        query = self.query
        sutta = input[0]
        query_simple = self.query_simple
        if self.query_whole in input[1]:
            rank = 100
        elif self.query_starts in input[1]:
            rank = 200
        elif self.query in input[1]:
            rank = 300
        elif ' ' + self.query_simple + ' ' in input[3]:
            rank = 1000
        elif ' ' + self.query_simple in input[3]:
            rank = 1100
        elif self.query_simple in input[3]:
            rank = 1200
        else:
            rank = 10000

        # Add bonus rank for suttas with more parallels.
        pbonus = sum(3 - 2 * t.partial for t in sutta.parallels)
        pbonus += len(sutta.translations)
        bonus = 200 * math.log(2) / math.log(2 + pbonus)

        # Penalize suttas from a subdivision with very many suttas.
        if pbonus < 4:
            bonus += 5 * int(10 / max(1, 25 - sutta.number))

        # Give a boost to suttas from a division with few suttas
        if len(sutta.subdivision.division.subdivisions) == 1:
            bonus -= 50 * math.log(32) / math.log(1 + len(sutta.subdivision.suttas))

        #if self.query_cased in input[2]:
            #bonus -= 25

        rank += bonus

        rank += sutta.subdivision.division.id

        return 10 * int(rank / 10) 

# This is a good place for a cache, since it is quite likely that
# the same results will be requested again, with only the offset changed.
# Results are not large, so there's little harm in caching a lot of them.

@functools.lru_cache(500)
def get_and_rank_results(query):
    results = search_dbr(query)
    if len(results) == 0:
        return ((),())
    ranker = Ranker(query)
    ranks, suttas = zip(*sorted((ranker(s), s[0]) for s in results))
    return (ranks, suttas)

def search(query=None, limit=25, offset=0):
    out = classes.SuttaResultsCategory()
    if len(query) < 3:
        out.total = 0
        out.add("Search term too short.", [])
        return out

    ranks, suttas = get_and_rank_results(query)
    
    count = len(ranks)
    out.total = count
    if count == 0:
        out.add("No results", [])
        return out

    ranks = ranks[offset:offset+limit]
    suttas = suttas[offset:offset+limit]
    
    breakpoint = bisect.bisect(ranks, 700)
    e_results = suttas[:breakpoint]
    s_results = suttas[breakpoint:]

    if count > offset+limit:
        start = limit + offset
        href = '/search/?query={}&target=suttas&limit={}&offset={}'.format(
            query, limit, start)
        out.footurl = '<a href="{}">Results {}–{}</a>'.format(
            href, start + 1, min(count, start + limit))
    
    if e_results:
        out.add("Exact results", e_results)
    if s_results:
        out.add("Similiar results", s_results)
    return out
        
def search_dbr(query):
    dbr = scdb.getDBR()
    # The structure of dbr.searchstrings is :
    # ( sutta, searchstring, searchstring_cased, suttaname simplified)

    # First try matching query as a whole
    cf_query = query.casefold()
    sm_query = textfunctions.simplify_pali(query)
    results = set(s for s in dbr.searchstrings if cf_query in s[1])
    results_s = set(s for s in dbr.searchstrings if sm_query in s[3])

    results.update(results_s)

    return results

def stress(count=1000):
    import time, concurrent.futures, random
    dbr = scdb.getDBR()
    terms = [s.name[:4] for s in dbr.suttas.values()]
    random.shuffle(terms)
    terms = terms[:1000] * int(1 + count / 1000)
    queries = random.sample(terms, count)

    getter = concurrent.futures.ThreadPoolExecutor(4)

    start = time.time()
    for r in getter.map(search, queries):
        pass
    done = time.time()

    print("Performed {} queries in {} seconds.".format(len(queries), done-start))
    print("{} queries per second.".format(len(queries) / (done-start)))
    