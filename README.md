## How to run

* before running the file `main_one2.py`, delete `data2.csv`，`hist.txt`，`log/main_one2.log`

* `persontoken.py` replace your GitHub personal token

* configure your proxy ip and port at the file `main_one2.py`: ``ss = SS(ip="127.0.0.1", port=7890)``

1. entrance for crawling new open issue `parse_contribute.py`
   1. Android: use repository list `f-droid/f-droid-github-filter.csv` and the function `download_new_issues` get open issue list
   2. Java, use the function `get_top_java_repo` to get repository list, and manully filter valid repository ( `java_repo_list.csv` ), then use the function `download_new_issues` get open issue list

2. entrance for searching close issue `main_one2.py` by the open issue list