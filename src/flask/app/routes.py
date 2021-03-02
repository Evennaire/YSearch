from app import app
from flask import render_template, request, flash, redirect, url_for

from elasticsearch import Elasticsearch

import time
import jieba
import sys
import codecs

import nltk
from nltk.corpus import wordnet as wn
from nltk.corpus import sentiwordnet as swn

def load_net():
    lines = codecs.open("./app/static/cow-not-full.txt", "rb", "utf-8")
    net = dict()
    for line in lines:
        if line.startswith('#') or not line.strip():
            continue
        splited = line.strip().split("\t")
        if len(splited) == 3:
            (synset, lemma, status) = splited
        elif len(splited) == 2:
            (synset, lemma) = splited
            status = 'Y'
        if '+' in lemma:
            lemma = lemma.split('+')[0]
        if status in ['Y', 'O']:
            if not lemma.strip() in net.keys():
                net[lemma.strip()] = [synset.strip()]
            else:
                net[lemma.strip()].append(synset.strip())
    return net

# Elastic search configuation
es = Elasticsearch(HOST="http://localhost", PORT=9200)
es = Elasticsearch()
es.indices.put_settings(index='sentences', body={'index':{'max_result_window':500}})
net = load_net()

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
        
        adj = request.form.get('adjacent')
        if adj == 'y':
            adj = True
        else:
            adj = False
        
        
        res = get_data(query, page, adj)

        if res == None:
            if page > 1: # 超出页面范围
                return None # invalid
            flash("输入不合法！")
            return redirect(url_for('index'))

    return render_template('result.html', res=res, query=query)


def getSenti(word):
    if word in ['开心', '甜蜜', '轻松']:
        return 0, 0.6

    # wordNet: dict{ word: [index, index, ...] }
    l = []
    if word in net.keys():
        l = net[word]

    if len(l) > 0:
        n = 0.0
        p = 0.0
        for index in l:
            info = wn.synset_from_pos_and_offset(str(index[-1:]), int(index[:8]))
            info = swn.senti_synset(info.name())
            p += info.pos_score()
            n += info.neg_score()
        return n / len(l), p / len(l) # average sentiment
    else:
        return 0, 0


def get_data(query, page, adjacent):
    tik = time.time()

    # number of results for one page
    ITEMS_PER_PAGE = 50

    # parse query
    # w1(p1) w2(p2) ... wn(pn) (p)[s]
    if query == '':
        return None

    query = query.split()
    if len(query) == 0:
        return None

    # parse words
    word = {}
    part = {}
    word_part = {}
    np = {}
    for pos in range(len(query)):
        word_query = query[pos]
        # parse query item: w, w*p, *p, *, *p&s, *&s
        
        if word_query[0] == '*':                            # *, *p, *p&s, *&s
            adjacent = True
            if '|' in word_query:                           # *p&s, *&s
                word_query_split = word_query.split('|')
                np[pos] = word_query_split[1]
                word_query = word_query_split[0]
            part[pos] = word_query.strip('*')               # *p, *
        elif '*' in word_query:                             # w*p
            split = word_query.split('*')
            word_part[pos] = split[0]+'_'+split[1]
        else:                                               # w
           word[pos] = word_query

    from_ = (page-1) * ITEMS_PER_PAGE
    size_ = ITEMS_PER_PAGE
    
    if adjacent:
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
    #print(total)
    #time = res['took']
    contents = res['hits']['hits'][:10000] # number of results before filtering

    # for adjacent
    # first query
    group_index = -1
    value = ""
    base_pos_query = -1

    if adjacent:
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
        if adjacent:                     # filter for +a
            groups = [onlycontent, onlypart, mix]

            # find all positions that match first query
            pos_in_sentence = []
            
            for i in range(leng):
                if groups[group_index][i] == value:
                    pos_in_sentence.append(i)

            for pos_query, value_query in word_part.items(): # for each query
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy:
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng or mix[p] != value_query:
                        pos_in_sentence.remove(pos_sentence)

            for pos_query, value_query in word.items():
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy:
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng or onlycontent[p] != value_query:
                        pos_in_sentence.remove(pos_sentence)
            
            for pos_query, value_query in part.items():
                if value_query == '':                                       # ()
                    continue
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy:
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng or onlypart[p] != value_query:
                        pos_in_sentence.remove(pos_sentence)

            for pos_query, value_query in np.items():                       # (p)[s] / ()[s]
                pos_in_sentence_copy = pos_in_sentence.copy()
                for pos_sentence in pos_in_sentence_copy:
                    p = pos_query + pos_sentence - base_pos_query
                    if p < 0 or p >= leng:
                        pos_in_sentence.remove(pos_sentence)
                    word_p = onlycontent[p]
                    neg, pos = getSenti(word_p)

                    if (value_query == 'n' and neg <= pos) or (value_query == 'p' and neg >= pos): # not qualified
                        if pos_sentence in pos_in_sentence:                 # exclude comma and other stop words
                            pos_in_sentence.remove(pos_sentence)
                    else:
                        #print(word_p, "n =", neg, "p =", pos)
                        pass
            
            if len(pos_in_sentence) == 0: # no possible positions
                add = False


        if add:
            doc = {'score':item['_score'], 'content': ''.join(onlycontent), 'mix': ' '.join(mix)}
            l.append(doc)

    if adjacent:
        total = len(l)
        start = (page - 1) * ITEMS_PER_PAGE
        l = l[start:start+ITEMS_PER_PAGE]

    if total > 300:
        total = 300

    total_page = (total - 1) // ITEMS_PER_PAGE + 1

    if total != 0 and page > total_page:
        return None

    tok = time.time()

    return {'time': round((tok - tik) * 1000), 'total': total, 'total_page': total_page, 'page': page, 'res': l, 'adj': adjacent}
