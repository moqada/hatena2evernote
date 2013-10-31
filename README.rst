hatena2evernote
===============

はてなブックマークに投稿したエントリの記事本文を Evernote に投稿します。

追加したタグやコメントも Evernote に反映されます。

インストール
------------

::

   git clone https://github.com/moqada/hatena2evernote
   cd hatena2evernote
   pip install -r requrements.txt

必要条件
--------

- Python 2.7 以上
- Evernote アカウント
- Readability アカウント

使い方
------

virtualenvなどの環境に依存ライブラリをインストールして、 `h2e.py` を適当に叩くだけです。

使い始める前に Evernote と Readability のトークンを取得して、
ホームディレクトリなどに以下のような設定ファイル(.h2e)を作成してください。

.. code-block:: ini

   [evernote]
   ; Evernoteのデベロッパトークン
   ; https://www.evernote.com/api/DeveloperToken.action
   token = <evernote developer token>

   [readability]
   ; Readability Parser APIのトークン
   ; http://www.readability.com/account/api
   token = <readability parser api token>

   
コマンド例
~~~~~~~~~~

id:moqada の前日分のはてブを投稿します::

   python h2e.py moqada


日付も指定できます::

   python h2e.py moqada --date=20131031


crontab に設定しておくと便利です::

   PYTHONIOENCODING=utf-8
   # 1日1回AM1時に前日分のはてブエントリをEvernoteに投稿する
   0 1 * * * python /path/to/h2e.py moqada
