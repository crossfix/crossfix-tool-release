from unittest import TestCase

from github import Github
from parse_contribute import *
from persontoken import MY_TOKEN
g = Github(MY_TOKEN)


class Test(TestCase):
    def test_is_feature_request(self):
        repo = g.get_repo("files-community/files-uwp")
        issue = repo.get_issue(1556)
        print(is_feature_request(issue))
