from unittest import TestCase

from keywords import search_keywords
from xml_parser import *


class Test(TestCase):

    def test_ui(self):
        repo_path = "D:\\A-work\\pullrecommend\\tmp\\nextcloud"
        ui_data = get_ui_descript(repo_path)

        # with open("tmp5709.data", 'r', encoding='utf8') as f:
        #     tmp_corpus = f.read()

        # example
        # 
        # # iss_link = 'https://github.com/nextcloud/android/issues/6212'
        # from persontoken import MY_TOKEN
        # g = Github(MY_TOKEN)
        # repo = g.get_repo("nextcloud/android")
        # iss_ob = repo.get_issue(number=6212)

        # with open("tmp6212.data", 'w', encoding='utf8', newline='') as f:
        #     print(iss_ob.body, file=f)
        # tmp_corpus = iss_ob.body

        with open("tmp6212.data", 'r', encoding='utf8') as f:
            tmp_corpus = f.read()

        out = search_keywords(tmp_corpus, ui_data, mode='ui')
        logger.debug(out)
