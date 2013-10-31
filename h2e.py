# -*- coding: utf-8 -*-
import argparse
import binascii
import datetime
import hashlib
import os
import re
import requests
import urllib
from evernote.api.client import EvernoteClient
from evernote.edam.type import ttypes as Types
from BeautifulSoup import BeautifulSoup
try:
    from ConfigParser import SafeConfigParser
except ImportError:
    from configparser import SafeConfigParser

HATEBU_URL = 'http://b.hatena.ne.jp/%(username)s/atomfeed?date=%(date)s'
READABILITY_PARSER_API = (
    'https://readability.com/api/content/v1/parser?url=%(url)s&token=%(token)s'
)
ENML_ENABLED_TAGS = (
    'a', 'abbr', 'acronym', 'address', 'area', 'b', 'bdo', 'big', 'blockquote',
    'br', 'caption', 'center', 'cite', 'code', 'col', 'colgroup', 'dd', 'del',
    'dfn', 'div', 'dl', 'dt', 'em', 'font', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'hr', 'i', 'img', 'ins', 'kbd', 'li', 'map', 'ol', 'p', 'pre', 'q', 's',
    'samp', 'small', 'span', 'strike', 'strong', 'sub', 'sup', 'table',
    'tbody', 'td', 'tfoot', 'th', 'thead', 'title', 'tr', 'tt', 'u', 'ul',
    'var', 'xmp'
)
ENML_DISABLED_TAGS_REGEX = re.compile(
    r'<(/?)(?!(%s)(\s.*?)?>)\w+(\s.*?)?>' % '|'.join(ENML_ENABLED_TAGS))
ENML_DISABLED_ATTRIBUTES = (
    'rel', 'class', 'id', 'on\w*?', 'frame', 'rules', 'alt', 'datetime'
)
# 主に連携サービスのToken情報などを格納しているグローバル変数
global_config = {}


def fetch_entries(username, date):
    """ 指定日付のはてブフィードを取得
    """
    url = HATEBU_URL % {'username': username, 'date': date}
    entries = []

    def get_entries(url):
        print 'Fetch: ', url
        res = requests.get(url)
        soup = BeautifulSoup(res.text)
        for entry in soup.findAll('entry'):
            entries.append({
                'title': entry.find('title').text,
                'summary': entry.find('summary').text or u'',
                'url': entry.find('link', rel='related').get('href'),
                'tags': [t.text for t in entry.findAll('dc:subject')],
            })
        next_link = soup.find('link', rel='next')
        if next_link is not None:
            get_entries(next_link.get('href'))

    get_entries(url)
    return entries


def to_enml(content, url=''):
    """ HTMLをENML形式に変換
    """
    enml = re.sub(r'<img(.*?)>', r'<img\1 />', content)
    # 許容されていない属性を削除する
    for attr in ENML_DISABLED_ATTRIBUTES:
        enml = re.sub(r'(<\w+.*?)( %s=".*?")(.*?>)' % attr, r'\1\3', enml)
    # href の中身が空や相対パスだと怒られるので変換
    enml = re.sub(r'(<a.*?)(href="")(.*?>)', r'\1href="#"\3', enml)
    if url:
        pattrn = (
            r'\1href="%s\3"\4'
            % re.search(r'https?://.*?(/|$)', url).group()
        )
    else:
        pattrn = r'\1href="./"\4'
    enml = re.sub(r'(<a.*?)(href="(/.*?)")(.*?>)', pattrn, enml)
    # preにstyleを追加
    enml = re.sub(
        r'(<pre.*?>)',
        r'<pre style="background-color:#EEE;padding:10px;">',
        enml)
    # 許容されていない要素をdivに変換
    return re.sub(ENML_DISABLED_TAGS_REGEX, r'<\1div>', enml)


def img_to_resource(note):
    """ 記事中の画像をResourceに変換してNoteに埋め込む
    """
    images = {}
    for img in re.finditer(r'<img.*?src="(.+?)".*?/>', note.content):
        src = img.group(1)
        try:
            res = urllib.urlopen(src)
            binary = res.read()
        except Exception:
            # なんらかの取得エラーが発生したら普通のimgタグのまま残しておく
            continue
        content_type = res.headers.get('content-type', '').split(';')[0]
        if content_type.find('image/') != 0:
            continue
        md5 = hashlib.md5()
        md5.update(binary)
        binary_hash = md5.digest()
        data = Types.Data()
        data.size = len(binary)
        data.bodyHash = binary_hash
        data.body = binary
        resource = Types.Resource()
        resource.mime = content_type
        resource.data = data
        # width/height情報を引き継ぐ
        match = re.search(r'width="(\d+)"', img.group(0))
        if match:
            resource.width = int(match.group(1))
        match = re.search(r'height="(\d+)"', img.group(0))
        if match:
            resource.height = int(match.group(1))
        images[img.group(0)] = resource
    # imgタグをen-mediaタグに変換
    for k, v in images.items():
        hash_hex = binascii.hexlify(v.data.bodyHash)
        note.content = note.content.replace(
            k,
            '<en-media type="%s" hash="%s" width="%s" height="%s"></en-media>'
            % (v.mime, hash_hex, v.width or '', v.height or ''))
    note.resources = images.values()
    return note


def create_note(entry):
    """ ブックマーク情報からEvernoteのNoteを作成
    """
    client = EvernoteClient(
        token=global_config['evernote']['token'], sandbox=False)
    note_store = client.get_note_store()
    note = Types.Note()
    note.title = entry['title']
    note.title = note.title.replace(unichr(int('2028', 16)), ' ')
    note.title = note.title.replace(unichr(int('2029', 16)), ' ')
    note.title = note.title.encode('utf-8')
    content = (
        u'<?xml version="1.0" encoding="UTF-8"?>'
        u'<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
    )
    content += u'<en-note>'
    if entry['summary']:
        content += u'%s<hr />' % entry['summary']
    content += to_enml(entry['content'], url=entry['url'])
    content += u'</en-note>'
    soup = BeautifulSoup(content)
    note.content = str(soup)
    attrs = Types.NoteAttributes(sourceURL=entry['url'])
    note.attributes = attrs
    note.tagNames = [e.encode('utf-8') for e in entry['tags']]
    note = img_to_resource(note)
    note_store.createNote(note)
    return note


def fetch_readability(url):
    """ Readability Parser API から整形したHTMLを取得
    """
    res = requests.get(
        READABILITY_PARSER_API % {
            'url': url,
            'token': global_config['readability']['token']
        })
    res_json = res.json()
    if res_json.get('content'):
        body = to_unicode(res_json.get('content'))
        return body
    # Readabilityでparseできない場合はその旨を本文に表記する
    return u'<b>記事をパースできませんでした</b>'


def to_unicode(content):
    """ JSONのマルチバイト文字列をunicodeに変換
    """
    num = len(content)
    words = ''
    i = 0
    while i < num:
        if content[i] == '&':
            if content[i:i + 3] == '&#x':
                s_hex = ''
                for j, c in enumerate(content[i + 3:], 4):
                    if c == ';':
                        break
                    s_hex += c
                words += unichr(int(s_hex, 16))
                i += j
                continue
        words += content[i]
        i += 1
    return words


def parse_config(filename):
    """ 設定ファイル読み込み
    """
    fp = os.path.expanduser('~/.h2e')
    parser = SafeConfigParser()
    parser.read(fp)
    global_config.update({
        'evernote': {'token': parser.get('evernote', 'token')},
        'readability': {'token': parser.get('readability', 'token')},
    })


def command():
    """ コマンド実行
    """
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    parser = argparse.ArgumentParser(
        description=u'はてブエントリの記事本文をEvernoteに保存します')
    parser.add_argument('hatenaid', help=u'対象はてブのはてなユーザ名')
    parser.add_argument(
        '--date', default=yesterday.strftime('%Y%m%d'),
        help=(
            u'はてブの収集対象日、YYYYMMDD形式、デフォルト: 前日(%s)'
            % yesterday.strftime('%Y%m%d')
        ))
    parser.add_argument(
        '--config', default='~/.h2e',
        help=u'設定ファイルのパス、デフォルト: ~/.h2e'
        )
    ns = parser.parse_args()
    parse_config(ns.config)
    # 収集処理実行
    entries = fetch_entries(ns.hatenaid, ns.date)
    # 新着順になっているので順番を逆に
    entries.reverse()
    for i, entry in enumerate(entries):
        entry['content'] = fetch_readability(entry['url'])
        print u'Fetch:', entry['title'], entry['url']
        create_note(entry)


if __name__ == '__main__':
    command()
