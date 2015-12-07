import urllib2
import pprint
from BeautifulSoup import BeautifulSoup
from lxml.builder import E
from lxml import etree

DASHBOARD_URL = 'http://www.csn.ul.ie/~mel/results/suse/marvin/dashboard-SLE11SP3User-Mainline-smart.html'

def getsoup(url):
    request = urllib2.Request(url)
    opener = urllib2.build_opener()
    html = opener.open(request).read()
    return BeautifulSoup(html)

columns = lambda x: [elem for elem in x
                     if hasattr(elem, 'name') and elem.name == 'td']
rows = lambda x: [elem for elem in x
                  if hasattr(elem, 'name') and elem.name == 'tr']

headercols = lambda x: [elem for elem in x
                        if hasattr(elem, 'name') and elem.name == 'th']

getmaintable = lambda s: s.contents[0].contents[2].contents[7].contents

def slurpbuildslave(node):
    tables = [elem for elem in node
              if hasattr(elem, 'name') and elem.name == 'table']
    assert(len(tables) == 1 or node.text == 'None')
    # The absence of a workload is better characterized by an empty list
    # than a {'name': None, 'result': None} dict, because
    # later I'll handle a variable number of workloads per config
    # and will need to do some <table> rowspan gymnastic
    if node.text == 'None': return []
    table = tables[0]
    out = []
    for row in rows(table):
        workload = {}
        for cnt, column in enumerate(columns(row)):
            if cnt == 0:
                # first column is the name of the workload:
                workload['name'] = column.text
            else:
                # the following columns are the results:
                result = {'value': column.text,
                          'color': column['bgcolor'],
                          'link': column.contents[0].contents[0]['href'],
                          'info': column.contents[0].contents[0]['title']}
                workload['result'] = result
        out.append(workload)
    return out

def slurpheaders(node):
    headers = []
    for cnt, column in enumerate(columns(node.contents)):
        if cnt == 0:
        # first column says "config"
            continue
        else:
            headers.append(column.contents[0].text)
    return headers

def slurprow(node, headers):
    out = {'config': None, 'workloadsets': []}
    for cnt, column in enumerate(columns(node)):
        if cnt == 0:
            # first column is the config name
            # I need the special case for "global-dhp__io-filebench-varmail-ext4"
            config = (column.contents[0].text if hasattr(column.contents[0], 'text')
                      else column.text)
            out['config'] = config
        else:
            workloadset = {'machine': headers[cnt-1],
                           'workloadset': slurpbuildslave(column)}
            out['workloadsets'].append(workloadset)
    return out

def slurpmaintable(node):
    workloadsdata = []
    for cnt, row in enumerate(rows(node)):
        if cnt == 0:
            # first row is headers
            headers = slurpheaders(row)
        else:
            workloadsdata.append(slurprow(row, headers))
    return {'headers': headers,
            'data': workloadsdata}

gettop10table = lambda s: s.contents[0].contents[2].contents[3].contents

def slurptop10(data):
    out = {'headers': None, 'data': []}
    for cnt, row in enumerate(rows(data)):
        if cnt == 0:
            # headers
            headers = map(lambda x: x.text, headercols(row))
            out['headers'] = headers
        else:
            out['data'].append(
                dict(zip(headers,
                         map(lambda x: (x.contents[0].text
                                        if hasattr(x, 'contents')
                                        and hasattr(x.contents[0], 'name')
                                        and x.contents[0].name == 'a'
                                        else x.text),
                             columns(row)))))
    return out

def getdata():
    soup = getsoup(DASHBOARD_URL)
    maintable = getmaintable(soup)
    top10table = gettop10table(soup)
    maindata = slurpmaintable(maintable)
    top10data = slurptop10(top10table)
    return {'top10': top10data,
            'main': maindata}

flatten = lambda listlist: [elem for list_ in listlist for elem in list_]

def maketwocellsifdata(data, n):
    # create the cells "name" and "result" for the n-th workload
    # from a machine/config.
    if len(data['workloadset']) >= n+1:
        
        out = [E.td({'class': 'right'},
                    data['workloadset'][n]['name']),
               # need special case for global-dhp__scheduler-unbound
               # which have no 'result'
               E.td(data['workloadset'][n]['result']['value'])
               if 'result' in data['workloadset'][n]
               else E.td('')]
    else:
        out = [E.td('', colspan = '2')]
    return out

def makefatrow(data):
    # I need to alternate light and dark at each "block row"
    # so this keeps a state that flips at each resume of the generator
    dark = True    
    for elem in data:
        largestworkloadset = max([len(x['workloadset']) for x in elem['workloadsets']])
        if largestworkloadset == 0:
            # special case, since rowspan == 0 has a special meaning:
            # the cell takes up to the end of the table
            largestworkloadset = 1
        rowlist = (
            # the first row for each "block" is special because the first cell
            # is the config name, which have a rowspan equal to the largest
            # set of workloads of the "block"
            [E.tr(
                {'class': "alt" if dark else ""},
                E.td({'class': 'left', 'rowspan': str(largestworkloadset)},
                     elem['config']),
                *flatten(map(lambda x: maketwocellsifdata(x, 0),
                             elem['workloadsets'])))]
            +
            # then I create all other rows of the block, from the 2nd on
            [E.tr(
                {'class': "alt" if dark else ""},
                *flatten(map(lambda x: maketwocellsifdata(x, n),
                               elem['workloadsets']))
            )
             for n in range(1, largestworkloadset)]
        )
        yield rowlist
        dark = not(dark)

def makemaintable(data):
    return (
        E.table(
            {'class': "info"},
            E.tbody(
                E.tr(
                    E.th('Config'),
                    *map(lambda x: E.th(x, colspan = '2'), data['headers'])
                ),
                *flatten(list(makefatrow(data['data'])))
            )
        )
    )

def maketop10row(data):
    dark = True
    rows = map(lambda datarow:
               map(E.td,
                   # here the list data['headers'] forces the order
                   # of elements in the row
                   map(lambda x: datarow[x], data['headers'])
               ),
               data['data']
           )
    for row in rows:
        yield E.tr({'class': "alt" if dark else ""}, *row)
        dark = not(dark)
    

def maketop10table(data):
    return (
        E.table(
            {'class': "info"},
            E.tbody(
                E.tr(
                    *map(E.th, data['headers'])
                ),
                *list(maketop10row(data))
            )
        )
    )
