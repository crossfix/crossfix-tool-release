import copy
import re
# from nltk.stem import PorterStemmer
# Porter2 is Snowball
from string import punctuation

from humps import decamelize as decam
from nltk.corpus import stopwords
from nltk.stem.snowball import SnowballStemmer
from nltk.tokenize import TreebankWordTokenizer

import work_path


def _get_stops():
    # stop words set
    punct = set(punctuation)
    stop_words = set(stopwords.words('english'))
    rt = punct.union(stop_words)
    rt = rt.union({"''", '``', "```", "--"})
    return rt


def _get_common_meanless():
    # common meanless word set
    word = set()
    with open('common.txt', 'r', encoding='utf8') as f:
        for row in f.readlines():
            tmp = row.strip()
            if tmp:
                word.add(tmp)
    return word


def get_hot_keys():
    hot_k = set()
    with open(work_path.in_project("./conf/hotkey.dat"), 'r', encoding='utf8') as f:
        for row in f.readlines():
            tmp = row.strip()
            if tmp != "":
                tmp = stem_word(tmp)
                hot_k.add(tmp)
    return hot_k


def get_concern_label():
    c_label = set()
    with open(work_path.in_project("./conf/concern_label.dat"), 'r', encoding='utf8') as f:
        for row in f.readlines():
            tmp = row.strip()
            if tmp != "":
                c_label.add(tmp)
    return c_label


def full_name_token(full_name):
    full_name = decamelize(full_name)
    full_name = re.split(r'\/|-|_', full_name)
    return list(filter(lambda item: item != "", full_name))


def tokenize(corpus):
    # tk = RegexpTokenizer('[a-zA-Z0-9\'\'.]+')
    tk = TreebankWordTokenizer()
    corpus_tokens = tk.tokenize(corpus.lower())
    return corpus_tokens

def remove_numeric(text):
    pass

def remove_meanless(corpus, ignore_tokens=None):
    # remove ignore_tokens, stopwords, common words from corpus
    meanless = _get_stops()
    meanless = meanless.union(_get_common_meanless())
    if ignore_tokens:
        meanless = meanless.union(ignore_tokens)
    filtered_words = []
    for w in corpus:
        if (w not in meanless) and (not w.isnumeric()):
            filtered_words.append(w)
    return filtered_words


def stemming(token_corpus) -> list:
    ess = SnowballStemmer('english', ignore_stopwords=True)
    stemmed_corpus = [ess.stem(w) for w in token_corpus]
    return stemmed_corpus


def stem_word(word):
    # stem single words
    corpus = [word, ]
    return stemming(corpus)[0]


def nlp_process(raw_corpus):
    # print(tokenize("I'm working on jobs"))
    # print(remove_meanless(tokenize("I'm working on jobs")))
    # print(stemming(remove_meanless(tokenize("I'm working on jobs"))))
    tmp_corpus = copy.deepcopy(raw_corpus)
    tmp_corpus = tokenize(tmp_corpus)
    tmp_corpus = remove_meanless(tmp_corpus)
    tmp_corpus = stemming(tmp_corpus)
    return tmp_corpus


def word_count(text):
    return len(tokenize(text))


def decamelize(w, mode='humps'):
    """
        camle to underline namming
    Args:
        w: word
        mode: 1 use pyhumps, 2 use regex

    Returns:
        word using underline naming
    """
    if mode == 'humps':
        return decam(w)
    elif mode == 'regex':
        return "_".join(re.findall('[A-Z][^A-Z]*', w))


def split_under(w):
    # split underline string to list
    return re.split('_+', w)


def unif_name(w, stem=False):
    tmp = decamelize(w)
    tmp = split_under(tmp)
    if stem:
        return stemming(tmp)
    else:
        return tmp


def last_dot(w, stem=False):
    tmp = w.split(".")[-1].lower()
    if stem:
        return stemming([tmp])[0]
    else:
        return tmp


def split_dot(w):
    # com.google.android.material.button.MaterialButton  ------>  ['material', 'button']
    tmp = last_dot(w)
    tmp = unif_name(tmp)
    return tmp


def process_xsv(xsv_output):
    output = copy.deepcopy(xsv_output)
    for i in range(len(output)):
        output[i][0] = unif_name(output[i][0])
        output[i][1] = split_dot(output[i][1])
        output[i][2] = unif_name(output[i][2])
    return output


def split_label(label_list):
    out = []
    for i in range(len(label_list)):
        tmp = list(filter(lambda item: item != "", label_list[i].split("#")))
        tmp = " ".join(tmp)
        tmp = tmp.lower()
        out.append(tmp)
    return out


# nlp = spacy.load('en_core_web_sm', disable=['ner', 'parser'])

# def lema(word):
#     doc = nlp(word)
#     return " ".join([token.lemma_ for token in doc])
#
#
# def lema_for_list(same_list):
#     ps = PorterStemmer()
#     same_list2 = copy.deepcopy(same_list)
#     for i in range(len(same_list2)):
#         for j in range(len(same_list2[i])):
#             same_list2[i][j] = ps.stem((lema(same_list2[i][j])).lower())
#     return same_list2

if __name__ == "__main__":
    print(tokenize("I'm working on jobs"))
    print(remove_meanless(tokenize("I'm working on jobs")))
    print(stemming(remove_meanless(tokenize("I'm working on jobs"))))
    print(stem_word("working"))
    print(word_count("I'm working on jobs"))
    print(decamelize("AfvsdfgbBsdfafv"))  # afvsdfgb_bsdfafv
    print(split_dot("com.google.android.material.button.MaterialButton"))
    a = '"Collection not opened" - Deck With Invalid Deck Options'
    a = tokenize(a)
    a = remove_meanless(a)
    print(a)

    a = 'persian-calendar/DroidPersianCalendar/D_sdasd'
    print(full_name_token(a))
