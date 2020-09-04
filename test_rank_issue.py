from unittest import TestCase

from github import Github

from rank_issue import rank_issue, android_plugin, java_plugin, code_sim_wrap
from util import SS
from loguru import logger


class Test(TestCase):
    def test_rank_list(self):
        # open url, open info online, open info offline, close url, close info (rank property)
        # 0       , 1               , 2                , 3        , 4
        a_list = [
            ['1', '2', '3', '4', ["hhhhh"]],
            ['1', '2', '3', '4', ["HAVE-FIX", ]],
            ['1', '2', '3', '4', ["Code-SIM"]],
            ['1', '2', '3', '4', ["HAVE-FIX", "Code-SIM"]]
        ]
        print(rank_issue(a_list))

    def test_android_plugin(self):
        ss = SS(ip="vm.userx.cn", port=7891)
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        result = android_plugin(g, 'https://github.com/owncloud/android/issues/2567')
        logger.debug(result)

    def test_java_plugin(self):
        ss = SS(ip="vm.userx.cn", port=7891)
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        # result = java_plugin(g, 'https://github.com/json-path/JsonPath/issues/549')
        result = java_plugin(g, 'https://github.com/PaulWoitaschek/Voice/issues/980')
        logger.debug(result)

    def test_java_plugin2(self):
        ss = SS(ip="vm.userx.cn", port=7891)
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        open_url = 'https://github.com/lightbend/config/issues/627'
        close_url = 'https://github.com/geotools/geotools/pull/2265'
        plugin = java_plugin

        open_off = plugin(g, open_url)
        logger.debug(f"open {open_url}")
        logger.debug(f"open offline rank, {open_off}=={len(open_off.keys())}")

        logger.debug("---------------------------")
        close_off = plugin(g, close_url)
        logger.debug(f"close {close_url}")
        logger.debug(f"close offline rank, {close_off}=={len(close_off.keys())}")

    def test_code_sim_wrap(self):
        ss = SS(ip="vm.userx.cn", port=7891)
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        open_url = 'https://github.com/lightbend/config/issues/627'
        close_url = 'https://github.com/geotools/geotools/pull/2265'
        flag = code_sim_wrap(g, open_url, close_url)
        logger.debug(flag)
