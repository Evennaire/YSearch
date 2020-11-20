from elasticsearch import Elasticsearch
from elasticsearch import helpers

import requests
import json


# Elastic search configuation
es = Elasticsearch(HOST="http://localhost", PORT=9200)
es = Elasticsearch()


#创建映射
_index_mappings = {
    "mappings" : {
        "properties" : {
            "content" : {
                "type" : "text",
                "analyzer": "whitespace",
                "search_analyzer": "whitespace"
            },
            "part": {
                "type": "text",
                "analyzer": "whitespace",
                "search_analyzer": "whitespace"
            },
            "mix": {
                "type": "text",
                "analyzer": "whitespace",
                "search_analyzer": "whitespace"
            }
        }
    }
}
#if es.indices.exists(index="sentences"):
#    es.indices.delete(index="sentences")
#es.indices.create(index="sentences", body=_index_mappings)


batch = []
# add files
files = ["./rmrb_output.txt", "./sogou_output.txt"]
for path in files:
    cnt = 1
    f = open(path)
    lines = f.readlines()
    print(path, " has ", len(lines), " lines.")
    length = len(lines)
    for line in lines:
        line = line.strip('\n')
        split = line.split(" ")
        content = ""
        part = ""
        for word in split:
            word_part = word.partition("_")
            if len(word_part) == 3: # filter invalid item
                content += word_part[0] + " "
                part += word_part[2] + " "
        doc = {"content": content, "part": part, "mix": line}
        item = {"_index": "sentences", "_source": doc}
        batch.append(item)
        if cnt % 20000 == 0:
            helpers.bulk(es, batch)
            batch = []
            print("\r%d"%cnt, end="")
        cnt += 1
    f.close()
    print("")

# bulk
helpers.bulk(es, batch)



# body = {
#     "from": 0,
#     "size": 10,
#     "query": {
#         "match": {
#             "content":"衣物"
#         }
#     }
# }

# # res = es.search(index="sentences", body=body)
# # print(res)
# url = 'http://localhost:9200/sentences/_doc/_search?pretty'

# headers = {'content-type': "application/json"}
# response = requests.get(url, data = json.dumps(body), headers = headers)
# res = json.loads(response.text)
# print(res)