from unittest import TestCase

from github import Github
from loguru import logger

import util
from crawlermy import fast_query, is_android_repo, parse_exception, last_commits, have_close_trigger, \
    commit_diff_prepare, moss_compare, form_query, add_pos


class Test(TestCase):

    def test_query(self):
        # From open issue, generate  fast query
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        repo = g.get_repo("nextcloud/android")
        iss_ob = repo.get_issue(number=5709)
        cur_q = fast_query(iss_ob.title, iss_ob.body)
        logger.debug(cur_q)

    def test_or(self):
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        only_android = False
        repo = "spring-projects/spring-boot"
        print(is_android_repo(g, repo))
        print(only_android ^ is_android_repo(g, repo))

    def test_parse_exception(self):
        body = """
Caused by: android.os.TransactionTooLargeException: data parcel size 552920 bytes
	at android.os.BinderProxy.transactNative(Native Method)
	at android.os.BinderProxy.transact(Binder.java:758)
	at android.app.IActivityManager$Stub$Proxy.activityStopped(IActivityManager.java:4736)
	at android.app.ActivityThread$StopInfo.run(ActivityThread.java:4049)
	... 7 more
"""
        exception_name, exception_info = parse_exception(body)
        assert exception_name == 'android.os.TransactionTooLargeException'
        assert exception_info == 'data parcel size 552920 bytes'

        body = """
Caused by: java.util.ConcurrentModificationException
        at java.util.LinkedList$ListItr.checkForComodification(LinkedList.java:967)
        at java.util.LinkedList$ListItr.next(LinkedList.java:889)
        at com.ichi2.async.CollectionTask.cancelAllTasks(CollectionTask.java:235)
        at com.ichi2.anki.DeckPicker.onPause(DeckPicker.java:867)
        at android.app.Activity.performPause(Activity.java:7663)
"""
        exception_name, exception_info = parse_exception(body)
        assert exception_name == 'java.util.ConcurrentModificationException'
        assert exception_info == ''

    def test_parse_exception2(self):
        body1 = """
java.lang.RuntimeException: Unable to pause activity {com.ichi2.anki/com.ichi2.anki.DeckPicker}: java.util.ConcurrentModificationException
    at android.app.ActivityThread.performPauseActivityIfNeeded(ActivityThread.java:4742)
    at android.app.ActivityThread.performPauseActivity(ActivityThread.java:4691)
    at android.app.ActivityThread.handlePauseActivity(ActivityThread.java:4626)
    at android.app.servertransaction.PauseActivityItem.execute(PauseActivityItem.java:45)
    at android.app.servertransaction.TransactionExecutor.executeLifecycleState(TransactionExecutor.java:145)
    at android.app.servertransaction.TransactionExecutor.execute(TransactionExecutor.java:70)
    at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2199)
    at android.os.Handler.dispatchMessage(Handler.java:112)
    at android.os.Looper.loop(Looper.java:216)
    at android.app.ActivityThread.main(ActivityThread.java:7625)
    at java.lang.reflect.Method.invoke(Native Method)
    at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:524)
    at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:987)
"""
        body2 = """
Caused by: java.util.ConcurrentModificationException
    at java.util.LinkedList$ListItr.checkForComodification(LinkedList.java:967)
    at java.util.LinkedList$ListItr.next(LinkedList.java:889)
    at com.ichi2.async.CollectionTask.cancelAllTasks(CollectionTask.java:235)
    at com.ichi2.anki.DeckPicker.onPause(DeckPicker.java:867)
    at android.app.Activity.performPause(Activity.java:7663)
    at android.app.Instrumentation.callActivityOnPause(Instrumentation.java:1536)
    at android.app.ActivityThread.performPauseActivityIfNeeded(ActivityThread.java:4726)
    at android.app.ActivityThread.performPauseActivity(ActivityThread.java:4691) 
    at android.app.ActivityThread.handlePauseActivity(ActivityThread.java:4626) 
    at android.app.servertransaction.PauseActivityItem.execute(PauseActivityItem.java:45) 
    at android.app.servertransaction.TransactionExecutor.executeLifecycleState(TransactionExecutor.java:145) 
    at android.app.servertransaction.TransactionExecutor.execute(TransactionExecutor.java:70) 
    at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2199) 
    at android.os.Handler.dispatchMessage(Handler.java:112) 
    at android.os.Looper.loop(Looper.java:216) 
    at android.app.ActivityThread.main(ActivityThread.java:7625) 
    at java.lang.reflect.Method.invoke(Native Method) 
    at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:524) 
    at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:987) 
"""
        exception_name, exception_info = parse_exception(body1)
        assert exception_name == 'java.lang.RuntimeException'
        assert exception_info == 'Unable to pause activity {com.ichi2.anki/com.ichi2.anki.DeckPicker}'
        # 测试回退逻辑

        exception_name, exception_info = parse_exception(body2)
        assert exception_name == 'java.util.ConcurrentModificationException'
        assert exception_info == ''

        exception_name, exception_info = parse_exception(f"{body1}\n{body2}")
        assert exception_name == 'java.util.ConcurrentModificationException'
        assert exception_info == ''

    def test_parse_exception3(self):
        body = """
!MESSAGE An internal error occurred during: "transformCheckstyle".
!STACK 0
java.lang.NoClassDefFoundError: org/eclipse/jdt/internal/ui/preferences/PreferencesAccess
at net.sf.eclipsecs.core.transformer.FormatterConfigWriter.writeCleanupSettings(FormatterConfigWriter.java:95)
at net.sf.eclipsecs.core.transformer.FormatterConfigWriter.writeSettings(FormatterConfigWriter.java:89)
at net.sf.eclipsecs.core.transformer.FormatterConfigWriter.<init>(FormatterConfigWriter.java:81)
at net.sf.eclipsecs.core.transformer.CheckstyleTransformer.transformRules(CheckstyleTransformer.java:124)
at net.sf.eclipsecs.core.jobs.TransformCheckstyleRulesJob.runInWorkspace(TransformCheckstyleRulesJob.java:117)
at org.eclipse.core.internal.resources.InternalWorkspaceJob.run(InternalWorkspaceJob.java:42)
at org.eclipse.core.internal.jobs.Worker.run(Worker.java:63)
"""
        exception_name, exception_info = parse_exception(body)
        assert exception_name == 'java.lang.NoClassDefFoundError'
        assert exception_info == 'org/eclipse/jdt/internal/ui/preferences/PreferencesAccess'

    def test_once(self):
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        # issob = util.get_issue(g, 'https://github.com/json-path/JsonPath/issues/549')
        # issob = util.get_issue(g, 'https://github.com/deathmarine/Luyten/issues/253')
        issob = util.get_issue(g, 'https://github.com/arthur-star/test/issues/2')
        curr_q = fast_query(issob.title, issob.body)
        try_pair = [
            (True, False, 'body'),  # stacktrace in body
            (False, True, 'title'),  # condition in title
            (False, False, 'title'),  # title in title
            (False, False, 'other')  # title (no field constraint)
        ]
        for _fi, pair in enumerate(try_pair):
            trace, condition, pos = pair
            query_list = form_query(curr_q, None, trace=trace, condition=condition)
            query_chars = " ".join(query_list)
            query_chars = add_pos(query_chars, pos)
            logger.debug(f"query_chars, {query_chars}")

    def test_github_search(self):
        # using token
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)

        ilinks = g.search_issues(query='google action page', state='closed', language='java', type='issue')
        for i in range(10):
            issue = ilinks[i]  # 解包的时候才进行网络请求
            print(issue.html_url)
        # 空格分隔关键词是正确的，和html一致
        # https://developer.github.com/v3/search/#constructing-a-search-query

    def test_check_body(self):
        body = '''fixes  : #1891 
### Description 
This PR wraps up the loose ends around supporting multiple joins, leaving as an extension #5062. A vast majority of this PR is just `multi-joins.json` which has somewhat extensive coverage on multi-joins - though a lot of it just depends on the correctness of joins which are covered in `joins.json`.
'''
        print(have_close_trigger(body, 1891))
        print(have_close_trigger(body, 1892))

    def test_last_commits(self):
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)
        issue = util.get_issue(g, 'https://github.com/confluentinc/ksql/issues/5062')
        result = last_commits(g, issue)
        print(result)

    def test_diff(self):
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)

        issue = util.get_issue(g, 'https://github.com/owlcs/owlapi/issues/936')
        result = last_commits(g, issue)
        print(result)

    def test_moss(self):
        # 'https://github.com/foo/bar/commit/${SHA}.patch'
        from persontoken import MY_TOKEN
        g = Github(MY_TOKEN)

        ss = util.SS(port=7890)

        repo = g.get_repo("soachishti/moss.py")
        issue = repo.get_issue(31)
        # 'https://github.com/soachishti/moss.py/pull/31'
        # issue.fullname
        # issue.pull_request.patch_url

        local_prefix, ex_dir = commit_diff_prepare(
            'https://github.com/userx/moss.py/commit/451ad107134e9e05894f7a80ed1a6e447913f99b.patch',
            'soachishti/moss.py')
        result = moss_compare(local_prefix, ex_dir)
        print(result)

    def test_exception_extract(self):
        body1 = """
        java.lang.RuntimeException: Unable to pause activity {com.ichi2.anki/com.ichi2.anki.DeckPicker}: java.util.ConcurrentModificationException
            at android.app.ActivityThread.performPauseActivityIfNeeded(ActivityThread.java:4742)
            at android.app.ActivityThread.performPauseActivity(ActivityThread.java:4691)
            at android.app.ActivityThread.handlePauseActivity(ActivityThread.java:4626)
            at android.app.servertransaction.PauseActivityItem.execute(PauseActivityItem.java:45)
            at android.app.servertransaction.TransactionExecutor.executeLifecycleState(TransactionExecutor.java:145)
            at android.app.servertransaction.TransactionExecutor.execute(TransactionExecutor.java:70)
            at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2199)
            at android.os.Handler.dispatchMessage(Handler.java:112)
            at android.os.Looper.loop(Looper.java:216)
            at android.app.ActivityThread.main(ActivityThread.java:7625)
            at java.lang.reflect.Method.invoke(Native Method)
            at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:524)
            at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:987)
        """
        body2 = """
        Caused by: java.util.ConcurrentModificationException
            at java.util.LinkedList$ListItr.checkForComodification(LinkedList.java:967)
            at java.util.LinkedList$ListItr.next(LinkedList.java:889)
            at com.ichi2.async.CollectionTask.cancelAllTasks(CollectionTask.java:235)
            at com.ichi2.anki.DeckPicker.onPause(DeckPicker.java:867)
            at android.app.Activity.performPause(Activity.java:7663)
            at android.app.Instrumentation.callActivityOnPause(Instrumentation.java:1536)
            at android.app.ActivityThread.performPauseActivityIfNeeded(ActivityThread.java:4726)
            at android.app.ActivityThread.performPauseActivity(ActivityThread.java:4691) 
            at android.app.ActivityThread.handlePauseActivity(ActivityThread.java:4626) 
            at android.app.servertransaction.PauseActivityItem.execute(PauseActivityItem.java:45) 
            at android.app.servertransaction.TransactionExecutor.executeLifecycleState(TransactionExecutor.java:145) 
            at android.app.servertransaction.TransactionExecutor.execute(TransactionExecutor.java:70) 
            at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2199) 
            at android.os.Handler.dispatchMessage(Handler.java:112) 
            at android.os.Looper.loop(Looper.java:216) 
            at android.app.ActivityThread.main(ActivityThread.java:7625) 
            at java.lang.reflect.Method.invoke(Native Method) 
            at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:524) 
            at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:987) 
        """
        curr_q = fast_query("", body1 + body2)
        query_list = form_query(curr_q, None, trace=True, condition=False)
        query_chars = " ".join(query_list)
        print(query_chars)
