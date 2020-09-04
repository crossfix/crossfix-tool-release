import re
import unittest

from crawlermy import *
from keywords import *
from xml_parser import *


class TestKeywords(unittest.TestCase):

    def test1(self):
        body = """java.lang.NullPointerException {sadfasdfasdf}: Attempt to re-invoke virtual method 'java.lang.Object android.widget.FrameLayout.getTag(int)' on a null object reference"""
        open_iss_body = body
        open_iss_body = nlp_util.tokenize(open_iss_body)
        open_iss_body = nlp_util.remove_meanless(open_iss_body)
        print(open_iss_body)

    def test1(self):
        # a bug in unidiff
        import urllib.request
        from unidiff import PatchSet
        diff = urllib.request.urlopen('https://patch-diff.githubusercontent.com/raw/eXist-db/exist/pull/2644.patch')
        encoding = diff.headers.get_charsets()[0]
        patch = PatchSet(diff, encoding=encoding)


if __name__ == '__main__':
    unittest.main()
