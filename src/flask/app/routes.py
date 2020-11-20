from app import app
from flask import render_template, request, flash, redirect, url_for

from elasticsearch import Elasticsearch

import time


# Elastic search configuation
es = Elasticsearch(HOST="http://localhost", PORT=9200)
es = Elasticsearch()
es.indices.put_settings(index='sentences', body={'index':{'max_result_window':500}}) 

@app.route('/')
@app.route('/index')
def index():
    return render_template('search.html')

@app.route('/result', methods=['POST'])
def search():
    if request.method == 'POST':
        query = request.form.get('query')
        if query == '': # 搜索为空，返回首页
            return render_template('search.html')

        page = request.form.get('page')
        if page == None:
            page = 1
        else:
            page = int(page)
        
        res = get_data(query, page)

        if res == None:
            if page > 1: # 超出页面范围
                return None # invalid
            flash("输入不合法！")
            return redirect(url_for('index'))

    return render_template('result.html', res=res, query=query)



def get_data(query, page):
    tik = time.time()

    # number of results for one page
    ITEMS_PER_PAGE = 50

    # parse query
    # w1(p1) w2(p2) ... wn(pn) +a
    adjcent = False
    if query == '':
        return None

    query = query.split(' ')
    if query[-1] == '+a':
        adjcent = True
        del(query[-1])
    if len(query) == 0:
        return None

    # parse words
    word = {}
    part = {}
    word_part = {}
    for pos in range(len(query)):
        word_query = query[pos]
        if word_query[0] == '(':    # (p)
            if not adjcent:         # only for +a
                return None
            part[pos] = word_query.strip('(').strip(')')
        elif '(' in word_query:  # w(p)
            split = word_query.split('(')
            word_part[pos] = split[0]+'_'+split[1].strip(')')
        else:                       # w
            word[pos] = word_query

    from_ = (page-1) * ITEMS_PER_PAGE
    size_ = ITEMS_PER_PAGE
    
    if adjcent:
        from_ = 0
        size_ = 500

    body = {
        "from": from_,
        "size": size_,
        "query": {
            "bool": {
                "should": []
            }
        }
    }
    if len(word) > 0:
        body["query"]["bool"]["should"].append({"match": { "content"   : " ".join(word.values())}})
    if len(word_part) > 0:
        body["query"]["bool"]["should"].append({"match": { "mix": " ".join(word_part.values())}})
    if len(part) > 0:
        body["query"]["bool"]["should"].append({"match": { "part": " ".join(part.values())}})

    res = es.search(index="sentences", body=body)


    # parse res
    total = res['hits']['total']['value']
    print(total)
    #time = res['took']
    contents = res['hits']['hits'][:10000] # number of results before filtering

    # for adjcent
    # first query
    group_index = -1
    value = ""
    base_pos_query = -1

    if adjcent:
        if len(word_part) > 0:
            group_index = 2
            base_pos_query = list(word_part.keys())[0]
            value = word_part[base_pos_query]
            word_part.pop(base_pos_query)
        elif len(word) > 0:
            group_index = 0
            base_pos_query = list(word.keys())[0]
            value = word[base_pos_query]
            word.pop(base_pos_query)
        elif len(part) > 0:
            group_index = 1
            base_pos_query = list(part.keys())[0]
            value = part[base_pos_query]
            part.pop(base_pos_query)

    l = []
    for item in contents:
        onlycontent = item['_source']['content'].split()
        onlypart = item['_source']['part'].split()
        mix = item['_source']['mix'].split()
        leng = len(onlycontent)

        add = True
        if adjcent:                     # filter for +a
            groups = [onlycontent, onlypart, mix]

            # find all positions that match first query
            pos_in_sentence = []
            
            for i in range(leng):
                if groups[group_index][i] == value:
                    pos_in_sentence.append(i)

            for pos_query, value_query in word_part.items(): # for each query
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy: # filtering
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng or mix[p] != value_query:
                        pos_in_sentence.remove(pos_sentence)

            for pos_query, value_query in word.items():
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy: # filtering
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng or onlycontent[p] != value_query:
                        pos_in_sentence.remove(pos_sentence)
            
            for pos_query, value_query in part.items():
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy: # filtering
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng or onlypart[p] != value_query:
                        pos_in_sentence.remove(pos_sentence)
            
            if len(pos_in_sentence) == 0: # no possible positions
                add = False
            

        if add:
            doc = {'score':item['_score'], 'content': ''.join(onlycontent), 'mix': ' '.join(mix)}
            l.append(doc)

    if adjcent:
        total = len(l)
        start = (page - 1) * ITEMS_PER_PAGE
        l = l[start:start+ITEMS_PER_PAGE]

    if total > 300:
        total = 300

    total_page = (total - 1) // ITEMS_PER_PAGE + 1

    if total != 0 and page > total_page:
        return None

    tok = time.time()

    return {'time': round((tok - tik) * 1000), 'total': total, 'total_page': total_page, 'page': page, 'res': l}
